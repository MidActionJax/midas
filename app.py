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
import datetime

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
    live_pnl = state.state_manager.daily_pnl
    
    live_trades = getattr(state.state_manager, 'live_trades', 0)
    live_wins = getattr(state.state_manager, 'live_wins', 0)
    win_rate = (live_wins / live_trades) * 100 if live_trades > 0 else 0

    # --- Historical Data ---
    avg_win = 0
    avg_loss = 0
    total_trades = 0
    realized_pnl = 0
    try:
        if os.path.exists('trade_history.csv') and os.stat('trade_history.csv').st_size > 0:
            df = pd.read_csv('trade_history.csv')
            if 'final_pnl' in df.columns:
                df['final_pnl'] = pd.to_numeric(df['final_pnl'], errors='coerce')
                closed_trades = df[df['final_pnl'].notna()]
                closed_trades = closed_trades[closed_trades['final_pnl'] != 0.0]
                if not closed_trades.empty:
                    wins = closed_trades[closed_trades['final_pnl'] > 0]
                    losses = closed_trades[closed_trades['final_pnl'] <= 0]
                    avg_win = wins['final_pnl'].mean() if not wins.empty else 0
                    avg_loss = losses['final_pnl'].mean() if not losses.empty else 0
                    total_trades = int(len(closed_trades))
                    realized_pnl = closed_trades['final_pnl'].sum()
                    if live_trades == 0:
                        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    except Exception:
        pass # Silently fail to keep dashboard running

    return {
        'win_rate': round(float(win_rate), 2),
        'total_pnl': round(float(live_pnl), 2),
        'avg_win': round(float(avg_win), 2),
        'avg_loss': round(float(avg_loss), 2),
        'realized_pnl': round(float(realized_pnl), 2),
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
                    'symbol': row.get('symbol') or config.TRADING_SYMBOL,
                    'type': row.get('type'),
                    'price': row.get('price'),
                    'ml_confidence': row.get('ml_confidence') or 'N/A',
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
            
            if df_corr['MES'].std() == 0 or df_corr['MNQ'].std() == 0:
                correlation_score = 1.0 # Perfect Sync fallback
            else:
                corr_val = df_corr['MES'].corr(df_corr['MNQ'])
                if pd.notna(corr_val):
                    correlation_score = float(corr_val)
    except Exception as e:
        print(f"Error calculating correlation: {e}")
        
    # --- Generate Equity Curve ---
    pnl_labels = []
    pnl_history = []
    try:
        if os.path.exists('trade_history.csv'):
            df_eq = pd.read_csv('trade_history.csv')
            if 'final_pnl' in df_eq.columns:
                df_eq['final_pnl'] = pd.to_numeric(df_eq['final_pnl'], errors='coerce')
                df_eq = df_eq[df_eq['final_pnl'].notna()]
                df_eq = df_eq[df_eq['final_pnl'] != 0.0]
                if not df_eq.empty:
                    df_eq = df_eq.sort_values(by='timestamp_id', ascending=True)
                    
                    pnl_history = [0.0]
                    pnl_labels = ['Start']
                    
                    running_total = 0.0
                    for _, row in df_eq.iterrows():
                        running_total += float(row['final_pnl'])
                        pnl_history.append(round(running_total, 2))
                        time_str = datetime.datetime.fromtimestamp(float(row['timestamp_id'])).strftime('%H:%M')
                        pnl_labels.append(time_str)
    except Exception as e:
        print(f"Error generating equity curve: {e}")
        
    if not pnl_history or len(pnl_history) <= 1:
        pnl_labels = ['Start', 'Live']
        pnl_history = [0.0, float(state.state_manager.daily_pnl)]
        
    #print(f"DEBUG: Sending {len(pnl_history)} points to Chart.")

    status_data = {
        'active': False,
        'price': "N/A",
        'symbol': config.TRADING_SYMBOL,
        'market_depth': None,
        'pending_signals': [],
        'realized_pnl': performance_stats.get('realized_pnl', 0.0),
        'open_positions': len(state.state_manager.get_active_positions()),
        'kill_switch_active': state.state_manager.is_kill_switch_active,
        
        # Get full whale patterns for the frontend
        'active_whales': [
            whale for whale in state.state_manager.get_detected_whales() 
            if whale.get('whale_id') in state.state_manager.get_active_dominant_whales()
        ],
        
        'nasdaq_status': 'Connected',
        'ema_mnq': 0.0,
        'nasdaq_connected': False,
        'performance': performance_stats,
        
        'win_rate': performance_stats.get('win_rate', 0.0),
        'avg_winner': performance_stats.get('avg_win', 0.0),
        'avg_loser': performance_stats.get('avg_loss', 0.0),

        # HUD Data
        'account_balance': account_balance,
        'daily_pnl': daily_pnl,
        'market_session': market_session,
        # Master Switch & Log
        'master_trading_mode': master_mode,
        'sizing_mode': sizing_mode,
        'execution_log': execution_log,
        'dev_mode': state.state_manager.dev_mode,
        'auto_buy_enabled': state.state_manager.auto_buy_enabled,
        'chop_index': state.state_manager.current_chop_index,
        'correlation_score': correlation_score,
        'pnl_labels': pnl_labels,
        'pnl_history': pnl_history
    }
    
    if core.engine.engine_thread and core.engine.engine_thread.is_alive():
        status_data['active'] = True
        
        market_data = state.state_manager.get_market_data(config.TRADING_SYMBOL)
        pending_signals = state.state_manager.get_pending_signals()

        if core.engine.engine_thread.adapter:
             status_data['nasdaq_connected'] = True
             try:
                price = core.engine.engine_thread.adapter.get_current_price(config.TRADING_SYMBOL)
                status_data['price'] = price
                
             except Exception as e:
                print(f"Error fetching data: {e}")
                status_data['price'] = "Error"
        else:
            status_data['price'] = "Initializing..."

        status_data['market_depth'] = market_data
        
        formatted_pending_signals = []
        for sig in pending_signals:
            formatted_sig = sig.copy()
            formatted_sig['symbol'] = sig.get('symbol', config.TRADING_SYMBOL)
            if 'ml_confidence' not in formatted_sig and 'confidence_score' in formatted_sig:
                formatted_sig['ml_confidence'] = f"{formatted_sig['confidence_score']}%"
            elif 'ml_confidence' not in formatted_sig:
                formatted_sig['ml_confidence'] = "N/A"
            formatted_pending_signals.append(formatted_sig)
            
        status_data['pending_signals'] = formatted_pending_signals

        # Add Nasdaq trend data if available
        if config.TRADING_MODE in ['PAPER_FUTURES', 'NT_FUTURES']:
            if core.engine.engine_thread and core.engine.engine_thread.adapter:
                features = core.engine.engine_thread.adapter.current_features
                mnq_ema = features.get('ema_200_mnq')
                
                # --- NEW FEEDBACK LOGIC ---
                if mnq_ema:
                    status_data['ema_mnq'] = round(mnq_ema, 2)
                    status_data['nasdaq_status'] = "Connected"
                else:
                    status_data['nasdaq_status'] = "Connected"
                    status_data['ema_mnq'] = 0.0

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
        # CRITICAL: Wipe Python memory immediately to prevent phantom exits
        state.state_manager.clear_active_positions()
        return jsonify({'status': 'success', 'message': 'Kill switch activated. All positions flattened and trading paused.'})
    return jsonify({'status': 'error', 'message': 'Engine not running.'}), 400

@app.route('/toggle_dev', methods=['POST'])
@login_required
def toggle_dev():
    """Toggles the developer mode."""
    new_mode = state.state_manager.toggle_dev_mode()
    return jsonify({'status': 'success', 'dev_mode': new_mode})

@app.route('/toggle_auto_buy', methods=['POST'])
@login_required
def toggle_auto_buy():
    """Toggles the auto-buy mode."""
    new_mode = state.state_manager.toggle_auto_buy()
    return jsonify({'status': 'success', 'auto_buy_enabled': new_mode})

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
        
        exec_price = signal_to_execute.get('price', price)

        # --- TASK 1: LIVE POSITION HARD GUARD & REVERSAL LOGIC ---
        current_pos = getattr(state.state_manager, 'live_nt_positions', {}).get(config.TRADING_SYMBOL, 0)

        if signal_to_execute['type'] == 'BUY_SIGNAL':
            if current_pos > 0:
                return jsonify({'status': 'error', 'message': 'Hard Guard: Already Long. Blocked.'}), 400
            elif current_pos < 0:
                print(f"--- REVERSAL: Flattening Short {abs(current_pos)} before Long Entry ---")
                adapter.execute_buy(config.TRADING_SYMBOL, abs(current_pos), exec_price, signal_id='REVERSAL')
                time.sleep(0.5)

            trade_executed = adapter.execute_buy(config.TRADING_SYMBOL, dynamic_size, exec_price, signal_id=signal_id)
            
            if trade_executed:
                position = {
                    'symbol': config.TRADING_SYMBOL,
                    'entry_price': exec_price,
                    'size': dynamic_size,
                    'type': 'BUY', # Or 'SELL' in the other block
                    # FIX: Start a fresh timer for the Grace Period
                    'timestamp': time.time(), 
                    # Keep the original ID for the CSV Logger
                    'signal_timestamp': float(signal_id)
                }
                state.state_manager.add_position(position)

        elif signal_to_execute['type'] == 'SELL_SIGNAL':
            if current_pos < 0:
                return jsonify({'status': 'error', 'message': 'Hard Guard: Already Short. Blocked.'}), 400
            elif current_pos > 0:
                print(f"--- REVERSAL: Flattening Long {current_pos} before Short Entry ---")
                adapter.execute_sell(config.TRADING_SYMBOL, current_pos, exec_price, signal_id='REVERSAL')
                time.sleep(0.5)

            trade_executed = adapter.execute_sell(config.TRADING_SYMBOL, dynamic_size, exec_price, signal_id=signal_id)
            
            if trade_executed:
                position = {
                    'symbol': config.TRADING_SYMBOL,
                    'entry_price': exec_price,
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

@app.route('/api/retrain', methods=['POST'])
@login_required
def api_retrain():
    try:
        # 1. Append trade_history to master dataset
        if os.path.exists('trade_history.csv'):
            df_new = pd.read_csv('trade_history.csv')
            df_new['outcome_label'] = df_new['outcome_label'].replace('', np.nan)
            df_new = df_new.dropna(subset=['outcome_label'])
            
            if 'trend_dir' in df_new.columns:
                df_new['trend_dir_numerical'] = df_new['trend_dir'].apply(lambda x: 1 if x == 'UP' else 0)
                
            master_file = 'training_data.csv'
            if not df_new.empty and not df_new.isna().all().all():
                df_new = df_new.dropna(axis=1, how='all')
                if os.path.exists(master_file):
                    df_master = pd.read_csv(master_file)
                    df_combined = pd.concat([df_master, df_new]).drop_duplicates(subset=['timestamp_id'])
                    df_combined.to_csv(master_file, index=False)
                else:
                    df_new.to_csv(master_file, index=False)

        # 2. Retrain ML Model
        brain.retrain_model()
        
        # 3. Retrain RL Model
        if os.path.exists('trade_history.csv'):
            df = pd.read_csv('trade_history.csv')
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
                    from models.rl_agent import retrain_agent
                    retrain_agent(real_data_df)

        # 4. Reload Models in Engine
        if core.engine.engine_thread:
            core.engine.engine_thread.reload_models()
            
        return jsonify({'status': 'success', 'message': 'Models successfully synced, retrained, and reloaded.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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