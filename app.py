from flask import Flask, render_template, jsonify, redirect, url_for, request
import core.engine
from core import state
import core.logger
import config
import time

app = Flask(__name__)

# To prevent caching of the status endpoint
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
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
    status_data = {
        'active': False,
        'price': "N/A",
        'balance': "N/A",
        'symbol': config.TRADING_SYMBOL,
        'market_depth': None,
        'pending_signals': [],
        'realized_pnl': state.state_manager.get_realized_pnl(),
        'open_positions': len(state.state_manager.get_active_positions()),
        'kill_switch_active': state.state_manager.is_kill_switch_active
    }
    
    # Check if the engine thread exists and is running
    if core.engine.engine_thread and core.engine.engine_thread.is_alive():
        status_data['active'] = True
        
        # Get data from the central state manager
        market_data = state.state_manager.get_market_data(config.TRADING_SYMBOL)
        pending_signals = state.state_manager.get_pending_signals()

        # Get Price and Balance from the Adapter
        if core.engine.engine_thread.adapter:
             try:
                # 1. Get Price
                price = core.engine.engine_thread.adapter.get_current_price(config.TRADING_SYMBOL)
                status_data['price'] = price
                
                # 2. Get Balance (NEW ADDITION)
                balance = core.engine.engine_thread.adapter.get_wallet_balance()
                status_data['balance'] = balance
                
             except Exception as e:
                print(f"Error fetching data: {e}")
                status_data['price'] = "Error"
        else:
            status_data['price'] = "Initializing..."

        status_data['market_depth'] = market_data
        status_data['pending_signals'] = pending_signals

    return jsonify(status_data)

@app.route('/switch_mode', methods=['POST'])
def switch_mode():
    data = request.get_json()
    new_mode = data.get('mode')
    
    if new_mode == 'PAPER_FUTURES':
        config.TRADING_MODE = 'PAPER_FUTURES'
        config.TRADING_SYMBOL = 'ES'
    else:
        config.TRADING_MODE = 'PAPER_CRYPTO'
        config.TRADING_SYMBOL = 'BTC/USDT'
        
    print(f"!!! SYSTEM MODE SWITCHED TO: {config.TRADING_MODE} ({config.TRADING_SYMBOL}) !!!")
    return jsonify({'status': 'success', 'mode': config.TRADING_MODE, 'symbol': config.TRADING_SYMBOL})

@app.route('/approve_signal/<float:signal_id>', methods=['POST'])
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')