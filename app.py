from flask import Flask, render_template, jsonify, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import os
import core.engine
from core import state
import core.logger
from core.logic import brain, get_market_session
import config
import time
import pandas as pd
import numpy as np
import threading
from models.rl_agent import retrain_agent

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
    """
    Calculates performance metrics.
    - Live PnL and Win Rate are from the current session's state.
    - Historical averages (Avg Win/Loss) are from the CSV file.
    """
    # --- Live Session Data ---
    live_pnl = 0
    win_rate = 0
    if state.state_manager.session_start_balance > 0:
        live_pnl = state.state_manager.account_balance - state.state_manager.session_start_balance
    
    if state.state_manager.live_trades > 0:
        win_rate = (state.state_manager.live_wins / state.state_manager.live_trades) * 100

    # --- Historical Data ---
    avg_win = 0
    avg_loss = 0
    total_trades = 0
    try:
        if os.path.exists('trade_history.csv') and os.stat('trade_history.csv').st_size > 0:
            df = pd.read_csv('trade_history.csv')
            required_columns = ['outcome_label', 'final_pnl']
            if all(col in df.columns for col in required_columns):
                closed_trades = df.dropna(subset=['outcome_label'])
                if not closed_trades.empty:
                    wins = closed_trades[closed_trades['outcome_label'] == 'WIN']
                    losses = closed_trades[closed_trades['outcome_label'] == 'LOSS']
                    avg_win = wins['final_pnl'].mean() if not wins.empty else 0
                    avg_loss = losses['final_pnl'].mean() if not losses.empty else 0
                    total_trades = int(len(closed_trades))
    except Exception:
        pass # Silently fail to keep dashboard running

    return {
        'win_rate': round(float(win_rate), 2),
        'total_pnl': round(float(live_pnl), 2),
        'avg_win': round(float(avg_win), 2),
        'avg_loss': round(float(avg_loss), 2),
        'total_trades': total_trades
    }

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
    
    # Get new HUD data from state
    account_balance = state.state_manager.account_balance
    daily_pnl = state.state_manager.daily_pnl
    market_session = get_market_session()
    master_mode = state.state_manager.master_trading_mode
    sizing_mode = state.state_manager.sizing_mode

    # Generate Execution Log
    execution_log = []
    try:
        if os.path.exists('trade_history.csv'):
            log_df = pd.read_csv('trade_history.csv').tail(10)
            log_df = log_df.replace({np.nan: None}) # Replace NaN with None for JSON
            for _, row in log_df.iterrows():
                decision = row.get('user_decision', 'N/A')
                status = 'Vetoed' if decision == 'REJECTED' else 'Pending'
                if decision == 'APPROVED':
                    status = 'Simulated' if master_mode == 'PAPER' else 'Executed'

                execution_log.append({
                    'timestamp': row.get('timestamp_id'),
                    'symbol': row.get('symbol'),
                    'type': row.get('type'),
                    'price': row.get('price'),
                    'ml_confidence': row.get('ml_confidence'),
                    'status': status
                })
    except Exception as e:
        print(f"Error generating execution log: {e}")

    # Calculate Correlation Score
    correlation_score = 0.0
    try:
        mes_hist = state.state_manager.price_history.get('MES', [])[-50:]
        mnq_hist = state.state_manager.price_history.get('MNQ', [])[-50:]
        if len(mes_hist) >= 20 and len(mnq_hist) >= 20:
            min_len = min(len(mes_hist), len(mnq_hist))
            df_corr = pd.DataFrame({'MES': mes_hist[-min_len:], 'MNQ': mnq_hist[-min_len:]})
            corr_val = df_corr['MES'].corr(df_corr['MNQ'])
            if pd.notna(corr_val):
                correlation_score = float(corr_val)
    except Exception as e:
        print(f"Error calculating correlation: {e}")

    status_data = {
        'active': False,
        'price': "N/A",
        'symbol': config.TRADING_SYMBOL,
        'market_depth': None,
        'pending_signals': [],
        'realized_pnl': state.state_manager.get_realized_pnl(),
        'open_positions': len(state.state_manager.get_active_positions()),
        'kill_switch_active': state.state_manager.is_kill_switch_active,
        
        # Get full whale patterns for the frontend
        'active_whales': [
            whale for whale in state.state_manager.get_detected_whales() 
            if whale.get('whale_id') in state.state_manager.get_active_dominant_whales()
        ],
        
        'nasdaq_status': 'UNKNOWN',
        'nasdaq_ema': None,
        'performance': performance_stats,
        # HUD Data
        'account_balance': account_balance,
        'daily_pnl': daily_pnl,
        'market_session': market_session,
        # Master Switch & Log
        'master_trading_mode': master_mode,
        'sizing_mode': sizing_mode,
        'execution_log': execution_log,
        'dev_mode': state.state_manager.dev_mode,
        'chop_index': state.state_manager.current_chop_index,
        'correlation_score': correlation_score
    }
    
    if core.engine.engine_thread and core.engine.engine_thread.is_alive():
        status_data['active'] = True
        
        market_data = state.state_manager.get_market_data(config.TRADING_SYMBOL)
        pending_signals = state.state_manager.get_pending_signals()

        if core.engine.engine_thread.adapter:
             try:
                price = core.engine.engine_thread.adapter.get_current_price(config.TRADING_SYMBOL)
                status_data['price'] = price
                
             except Exception as e:
                print(f"Error fetching data: {e}")
                status_data['price'] = "Error"
        else:
            status_data['price'] = "Initializing..."

        status_data['market_depth'] = market_data
        status_data['pending_signals'] = pending_signals

        # Add Nasdaq trend data if available
        # Add Nasdaq trend data if available
        if config.TRADING_MODE in ['PAPER_FUTURES', 'NT_FUTURES']:
            if core.engine.engine_thread and core.engine.engine_thread.adapter:
                features = core.engine.engine_thread.adapter.current_features
                mnq_ema = features.get('ema_200_val')
                
                # --- NEW FEEDBACK LOGIC ---
                if mnq_ema and state.state_manager.price_history.get('MNQ'):
                    current_mnq_price = state.state_manager.price_history['MNQ'][-1]
                    status_data['nasdaq_ema'] = mnq_ema
                    status_data['nasdaq_status'] = "BULLISH" if current_mnq_price > mnq_ema else "BEARISH"
                else:
                    # Tells the dashboard we are collecting the 200 bars
                    status_data['nasdaq_status'] = "CALCULATING..."
                    status_data['nasdaq_ema'] = 0.0

    return jsonify(status_data)

@app.route('/switch_mode', methods=['POST'])
def switch_mode():
    data = request.get_json()
    new_mode = data.get('mode')
    
    if new_mode == 'NT_FUTURES':
        config.TRADING_MODE = 'NT_FUTURES'
        config.TRADING_SYMBOL = 'MES'
    elif new_mode == 'PAPER_FUTURES':
        config.TRADING_MODE = 'PAPER_FUTURES'
        config.TRADING_SYMBOL = 'MES'
    else:
        config.TRADING_MODE = 'PAPER_CRYPTO'
        config.TRADING_SYMBOL = 'BTC/USDT'
        
    print(f"!!! SYSTEM MODE SWITCHED TO: {config.TRADING_MODE} ({config.TRADING_SYMBOL}) !!!")
    return jsonify({'status': 'success', 'mode': config.TRADING_MODE, 'symbol': config.TRADING_SYMBOL})

@app.route('/set_master_mode', methods=['POST'])
@login_required
def set_master_mode():
    data = request.get_json()
    new_mode = data.get('mode')
    if new_mode in ['PAPER', 'LIVE']:
        state.state_manager.set_master_trading_mode(new_mode)
        return jsonify({'status': 'success', 'master_mode': new_mode})
    return jsonify({'status': 'error', 'message': 'Invalid mode'}), 400

@app.route('/set_sizing_mode', methods=['POST'])
@login_required
def set_sizing_mode():
    data = request.get_json()
    new_mode = data.get('mode')
    if new_mode in ['FIXED', 'AUTO']:
        state.state_manager.set_sizing_mode(new_mode)
        return jsonify({'status': 'success', 'sizing_mode': new_mode})
    return jsonify({'status': 'error', 'message': 'Invalid sizing mode'}), 400

@app.route('/kill_switch', methods=['POST'])
@login_required
def kill_switch():
    if core.engine.engine_thread and core.engine.engine_thread.is_alive():
        core.engine.engine_thread.flatten_all()
        return jsonify({'status': 'success', 'message': 'Kill switch activated. All positions flattened and trading paused.'})
    return jsonify({'status': 'error', 'message': 'Engine not running.'}), 400

@app.route('/toggle_dev', methods=['POST'])
@login_required
def toggle_dev():
    """Toggles the developer mode."""
    new_mode = state.state_manager.toggle_dev_mode()
    return jsonify({'status': 'success', 'dev_mode': new_mode})

@app.route('/approve_signal/<string:signal_id>', methods=['POST'])
@login_required
def approve_signal(signal_id):
    # Log the user's decision
    core.logger.update_user_decision(signal_id, 'APPROVED')

    if not core.engine.engine_thread or not core.engine.engine_thread.is_alive() or not core.engine.engine_thread.adapter:
        return jsonify({'status': 'error', 'message': 'Engine not running.'}), 400

    signal_to_execute = None
    for signal in state.state_manager.get_pending_signals():
        if str(signal['timestamp']) == signal_id:
            signal_to_execute = signal
            break
    
    if not signal_to_execute:
        return jsonify({'status': 'error', 'message': 'Signal not found.'}), 404

    try:
        # --- Live Win Rate Tracking ---
        state.state_manager.set_signal_approved()
        # --------------------------

        adapter = core.engine.engine_thread.adapter
        trade_executed = False
        
        # Surgical Fix: Use your new dynamic sizing logic
        from core.logic import calculate_position_size
        
        balance = adapter.get_wallet_balance()
        price = adapter.get_current_price(config.TRADING_SYMBOL)
        
        dynamic_size = calculate_position_size(
            price, 
            state.state_manager.price_history
        )

        if signal_to_execute['type'] == 'BUY_SIGNAL':
            trade_executed = adapter.execute_buy(config.TRADING_SYMBOL, dynamic_size, price, signal_id=signal_id)
            
            if trade_executed:
                entry_price = price
                position = {
                    'symbol': config.TRADING_SYMBOL,
                    'entry_price': price,
                    'size': dynamic_size,
                    'type': 'BUY', # Or 'SELL' in the other block
                    # FIX: Start a fresh timer for the Grace Period
                    'timestamp': time.time(), 
                    # Keep the original ID for the CSV Logger
                    'signal_timestamp': float(signal_id)
                }
                state.state_manager.add_position(position)

        elif signal_to_execute['type'] == 'SELL_SIGNAL':
            trade_executed = adapter.execute_sell(config.TRADING_SYMBOL, dynamic_size, signal_id=signal_id)
            
            if trade_executed:
                entry_price = price # Or get it from sell execution if different
                position = {
                    'symbol': config.TRADING_SYMBOL,
                    'entry_price': price,
                    'size': dynamic_size,
                    'type': 'SELL', # Or 'SELL' in the other block
                    # FIX: Start a fresh timer for the Grace Period
                    'timestamp': time.time(), 
                    # Keep the original ID for the CSV Logger
                    'signal_timestamp': float(signal_id)
                }
                state.state_manager.add_position(position)

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

@app.route('/api/equity')
@login_required
def get_equity():
    try:
        if not os.path.exists('trade_history.csv'):
            return jsonify([])
        df = pd.read_csv('trade_history.csv')
        df['final_pnl'] = pd.to_numeric(df['final_pnl'], errors='coerce')
        df = df.dropna(subset=['final_pnl'])
        if df.empty:
            return jsonify([])
        
        df = df.sort_values(by='timestamp_id')
        df['cumulative_pnl'] = df['final_pnl'].cumsum()
        
        equity_data = [{'time': float(row['timestamp_id']) * 1000, 'balance': float(row['cumulative_pnl'])} for _, row in df.iterrows()]
            
        return jsonify(equity_data)
    except Exception as e:
        print(f"Error fetching equity data: {e}")
        return jsonify([])

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def evolution_loop():
    """Background task to retrain the RL agent on real trade data every 24 hours."""
    while True:
        time.sleep(86400)  # 24 hours
        try:
            print("--- INITIATING EVOLUTION LOOP: Retraining RL Agent ---")
            if os.path.exists('trade_history.csv'):
                df = pd.read_csv('trade_history.csv')
                
                # Filter for approved trades with a final outcome
                approved_df = df[(df['user_decision'] == 'APPROVED') & (df['final_pnl'].notna())]
                
                if not approved_df.empty:
                    real_data_df = pd.DataFrame()
                    real_data_df['price'] = pd.to_numeric(approved_df['price'], errors='coerce')
                    real_data_df['ema_200'] = pd.to_numeric(approved_df['ema_200_val'], errors='coerce')
                    real_data_df['chop_index'] = 50.0  # Default value since it's not logged in CSV
                    real_data_df['atr'] = pd.to_numeric(approved_df['atr_volatility'], errors='coerce')
                    real_data_df['whale_strength'] = pd.to_numeric(approved_df['whale_strength'], errors='coerce')
                    
                    real_data_df = real_data_df.dropna().reset_index(drop=True)
                    
                    if not real_data_df.empty:
                        retrain_agent(real_data_df)
                        print("--- EVOLUTION COMPLETE: Midas Brain updated with real-world results ---")
        except Exception as e:
            print(f"Error during evolution loop: {e}")

from waitress import serve
if __name__ == '__main__':
    if not os.environ.get('SECRET_KEY') or not os.environ.get('DASHBOARD_PASSWORD'):
        print("FATAL: The SECRET_KEY and DASHBOARD_PASSWORD environment variables must be set.")
    else:
        # Start the Evolution Loop background task
        threading.Thread(target=evolution_loop, daemon=True).start()
        
        # Start the Midas Engine in a separate thread
        core.engine.start_engine()
        # Now, run the Flask app with Waitress
        serve(app, host='0.0.0.0', port=5000)