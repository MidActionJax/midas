from flask import Flask, render_template, jsonify, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import os
import core.engine
from core import state
import core.logger
from core.logic import brain # ADDED
import config
import time
import pandas as pd
import numpy as np

app = Flask(__name__)
load_dotenv()
app.secret_key = os.environ.get('SECRET_KEY')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def get_performance_stats():
    """Reads trade_history.csv and calculates performance metrics safely."""
    try:
        # Check if the file exists and has content
        if not os.path.exists('trade_history.csv') or os.stat('trade_history.csv').st_size == 0:
            return {'win_rate': 0, 'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0, 'total_trades': 0}

        df = pd.read_csv('trade_history.csv')
        
        # Verify the required columns exist before processing
        required_columns = ['outcome_label', 'final_pnl']
        if not all(col in df.columns for col in required_columns):
            return {'win_rate': 0, 'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0, 'total_trades': 0}
        
        # Filter for trades that have a definitive outcome
        closed_trades = df.dropna(subset=['outcome_label'])
        
        if closed_trades.empty:
            return {'win_rate': 0, 'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0, 'total_trades': 0}

        wins = closed_trades[closed_trades['outcome_label'] == 'WIN']
        losses = closed_trades[closed_trades['outcome_label'] == 'LOSS']

        win_rate = (len(wins) / len(closed_trades)) * 100
        total_pnl = closed_trades['final_pnl'].sum()
        
        avg_win = wins['final_pnl'].mean() if not wins.empty else 0
        avg_loss = losses['final_pnl'].mean() if not losses.empty else 0

        return {
            'win_rate': round(float(win_rate), 2),
            'total_pnl': round(float(total_pnl), 2),
            'avg_win': round(float(avg_win), 2),
            'avg_loss': round(float(avg_loss), 2),
            'total_trades': int(len(closed_trades))
        }
    except Exception:
        # Silently fail and return zeros to keep the dashboard running
        return {'win_rate': 0, 'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0, 'total_trades': 0}

# To prevent caching of the status endpoint
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        password = request.form['password']
        if check_password_hash(os.environ.get('DASHBOARD_PASSWORD'), password):
            user = User(1)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid password')
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/start_bot')
def start_bot():
    core.engine.start_engine() # CHANGED
    return redirect(url_for('index'))

@app.route('/stop_bot')
def stop_bot():
    core.engine.stop_engine() # CHANGED
    return redirect(url_for('index'))

@app.route('/status')
def status():
    """Returns the current status of the bot for AJAX updates."""
    performance_stats = get_performance_stats()
    status_data = {
        'active': False,
        'price': "N/A",
        'balance': "N/A",
        'symbol': config.TRADING_SYMBOL,
        'market_depth': None,
        'pending_signals': [],
        'realized_pnl': state.state_manager.get_realized_pnl(),
        'open_positions': len(state.state_manager.get_active_positions()),
        'kill_switch_active': state.state_manager.is_kill_switch_active,
        'nasdaq_status': 'UNKNOWN',
        'nasdaq_ema': None,
        'performance': performance_stats
    }
    
    if core.engine.engine_thread and core.engine.engine_thread.is_alive():
        status_data['active'] = True
        
        market_data = state.state_manager.get_market_data(config.TRADING_SYMBOL)
        pending_signals = state.state_manager.get_pending_signals()

        if core.engine.engine_thread.adapter:
             try:
                price = core.engine.engine_thread.adapter.get_current_price(config.TRADING_SYMBOL)
                status_data['price'] = price
                
                balance = core.engine.engine_thread.adapter.get_wallet_balance()
                status_data['balance'] = balance
                
             except Exception as e:
                print(f"Error fetching data: {e}")
                status_data['price'] = "Error"
        else:
            status_data['price'] = "Initializing..."

        status_data['market_depth'] = market_data
        status_data['pending_signals'] = pending_signals

        # Add Nasdaq trend data if available
        if config.TRADING_MODE == 'PAPER_FUTURES':
            mnq_ema = state.state_manager.ema_val.get('MNQ')
            if mnq_ema and state.state_manager.price_history.get('MNQ'):
                current_mnq_price = state.state_manager.price_history['MNQ'][-1]
                status_data['nasdaq_ema'] = mnq_ema
                status_data['nasdaq_status'] = "BULLISH" if current_mnq_price > mnq_ema else "BEARISH"

    return jsonify(status_data)

@app.route('/switch_mode', methods=['POST'])
def switch_mode():
    data = request.get_json()
    new_mode = data.get('mode')
    
    if new_mode == 'PAPER_FUTURES':
        config.TRADING_MODE = 'PAPER_FUTURES'
        config.TRADING_SYMBOL = 'MES'
    else:
        config.TRADING_MODE = 'PAPER_CRYPTO'
        config.TRADING_SYMBOL = 'BTC/USDT'
        
    print(f"!!! SYSTEM MODE SWITCHED TO: {config.TRADING_MODE} ({config.TRADING_SYMBOL}) !!!")
    return jsonify({'status': 'success', 'mode': config.TRADING_MODE, 'symbol': config.TRADING_SYMBOL})

@app.route('/approve_signal/<float:signal_id>', methods=['POST'])
@login_required
def approve_signal(signal_id):
    # Log the user's decision
    core.logger.update_user_decision(signal_id, 'APPROVED')

    if not core.engine.engine_thread or not core.engine.engine_thread.is_alive() or not core.engine.engine_thread.adapter:
        return jsonify({'status': 'error', 'message': 'Engine not running.'}), 400

    signal_to_execute = None
    for signal in state.state_manager.get_pending_signals():
        if signal['timestamp'] == signal_id:
            signal_to_execute = signal
            break
    
    if not signal_to_execute:
        return jsonify({'status': 'error', 'message': 'Signal not found.'}), 404

    try:
        adapter = core.engine.engine_thread.adapter
        trade_executed = False
        if signal_to_execute['type'] == 'BUY_SIGNAL':
            # Surgical Fix: Use your new dynamic sizing logic
            from core.logic import calculate_position_size
            
            balance = adapter.get_wallet_balance()
            price = adapter.get_current_price(config.TRADING_SYMBOL)
            
            dynamic_size = calculate_position_size(
                balance, 
                price, 
                state.state_manager.price_history
            )
            
            trade_executed = adapter.execute_buy(config.TRADING_SYMBOL, dynamic_size, price)
            
            if trade_executed:
                entry_price = price
                position = {
                    'symbol': config.TRADING_SYMBOL,
                    'entry_price': entry_price,
                    'size': dynamic_size,
                    'timestamp': time.time(),
                    'signal_timestamp': signal_id # Link position to the original signal
                }
                state.state_manager.add_position(position)

        elif signal_to_execute['type'] == 'SELL_SIGNAL':
            trade_executed = adapter.execute_buy(config.TRADING_SYMBOL, dynamic_size, price)

        if trade_executed:
            state.state_manager.remove_pending_signal(signal_to_execute)
            return jsonify({'status': 'success', 'message': f"Trade executed for signal {signal_id}"})
        else:
            return jsonify({'status': 'error', 'message': 'Trade execution failed.'}), 500
            
    except Exception as e:
        print(f"Error executing trade: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/reject_signal/<float:signal_id>', methods=['POST'])
@login_required
def reject_signal(signal_id):
    # Log the user's decision
    core.logger.update_user_decision(signal_id, 'REJECTED')

    signal_to_remove = None
    for signal in state.state_manager.get_pending_signals():
        if signal['timestamp'] == signal_id:
            signal_to_remove = signal
            break
            
    if signal_to_remove:
        state.state_manager.remove_pending_signal(signal_to_remove)
        return jsonify({'status': 'success', 'message': f"Signal {signal_id} rejected."})
    else:
        return jsonify({'status': 'error', 'message': 'Signal not found.'}), 404

@app.route('/retrain')
@login_required
def retrain():
    """Triggers the ML model retraining process."""
    print("--- Received request to retrain model... ---")
    success = brain.retrain_model()
    # TODO: Add flash messaging to tell the user if it succeeded
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

from waitress import serve
if __name__ == '__main__':
    if not os.environ.get('SECRET_KEY') or not os.environ.get('DASHBOARD_PASSWORD'):
        print("FATAL: The SECRET_KEY and DASHBOARD_PASSWORD environment variables must be set.")
    else:
        # Start the Midas Engine in a separate thread
        core.engine.start_engine()
        # Now, run the Flask app with Waitress
        serve(app, host='0.0.0.0', port=5000)