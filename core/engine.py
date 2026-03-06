import threading
import time
import config
from adapters.paper_crypto import PaperCryptoAdapter
from adapters.paper_futures import PaperFuturesAdapter
from core import state, logic, logger

class MidasEngine(threading.Thread):
    def __init__(self, trading_symbol): # Add trading_symbol here
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.trading_symbol = trading_symbol # Store it for the loop
        self.adapter = None
        self.last_trade_time = 0

    def manage_positions(self):
        """
        Monitors active positions and triggers auto-sell based on PnL rules.
        """
        if not self.adapter:
            return

        positions_to_remove = []
        for position in state.state_manager.get_active_positions():
            try:
                current_price = self.adapter.get_current_price(position['symbol'])
                unrealized_pnl = (current_price - position['entry_price']) * position['size']
                
                reason = None
                if unrealized_pnl >= 50:
                    reason = 'TAKE_PROFIT'
                elif unrealized_pnl <= -20.0:
                    reason = 'STOP_LOSS'

                if reason:
                    print(f"!!! {reason} TRIGGERED: PnL = {unrealized_pnl:.2f} !!!")
                    if self.adapter.execute_sell(position['symbol'], position['size']):
                        state.state_manager.add_pnl(unrealized_pnl)
                        
                        log_data = {
                            'symbol': position['symbol'],
                            'action': 'SELL',
                            'size': position['size'],
                            'price': current_price,
                            'pnl': unrealized_pnl,
                            'reason': reason
                        }
                        logger.log_trade(log_data)
                        
                        positions_to_remove.append(position)
                        self.last_trade_time = time.time()
                    else:
                        print(f"!!! FAILED TO EXECUTE {reason} SELL ORDER !!!")

            except Exception as e:
                print(f"Error managing position {position}: {e}")

        for pos in positions_to_remove:
            state.state_manager.remove_position(pos)


    def run(self):
        print("MidasEngine starting...")
        while not self._stop_event.is_set():
            if state.state_manager.is_kill_switch_active:
                print('!!! CRITICAL: DAILY DRAWDOWN LIMIT REACHED. SHUTTING DOWN !!!')
                self.stop()
                break

            if self.adapter is None:
                if config.TRADING_MODE == 'PAPER_CRYPTO':
                    print("Initializing PaperCryptoAdapter...")
                    self.adapter = PaperCryptoAdapter()
                elif config.TRADING_MODE == 'PAPER_FUTURES': # Add this block
                    print("Initializing PaperFuturesAdapter...")
                    self.adapter = PaperFuturesAdapter()

            if self.adapter:
                try:
                    self.manage_positions()

                    if time.time() - self.last_trade_time < 300: # 5-minute cooldown
                        time.sleep(1)
                        continue

                    market_depth = self.adapter.get_market_depth(config.TRADING_SYMBOL)
                    state.state_manager.set_market_data(config.TRADING_SYMBOL, market_depth)

                    signal = logic.analyze_order_book(market_depth, state.state_manager.price_history)
                    if signal:
                        pending_signals = state.state_manager.get_pending_signals()
                        is_duplicate = False
                        for existing_signal in pending_signals:
                            if existing_signal['price'] == signal['price'] and existing_signal['type'] == signal['type']:
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            state.state_manager.add_pending_signal(signal)
                            print(f"!!! NEW SIGNAL DETECTED: {signal['type']} at {signal['price']} for {signal['size']} !!!")

                    price = self.adapter.get_current_price(config.TRADING_SYMBOL)
                    if price is not None:
                        state.state_manager.add_price(price)
                    unit = "USD" if config.TRADING_SYMBOL == "ES" else "USDT"
                    print(f"HEARTBEAT: Price of {config.TRADING_SYMBOL} is {price} {unit}")

                except Exception as e:
                    print(f"Error in engine loop: {e}")
            
            time.sleep(5)
        
        print("MidasEngine stopped.")

    def stop(self):
        print("Stopping MidasEngine...")
        self._stop_event.set()

engine_thread = None

def start_engine():
    global engine_thread
    # Force a reload/check of the current config state
    import config 
    
    if engine_thread is None or not engine_thread.is_alive():
        print(f"Engine starting in mode: {config.TRADING_MODE} for {config.TRADING_SYMBOL}")
        engine_thread = MidasEngine(config.TRADING_SYMBOL)
        engine_thread.start()

def stop_engine():
    global engine_thread
    if engine_thread and engine_thread.is_alive():
        engine_thread.stop()
        engine_thread.join()
        engine_thread = None
        print("MidasEngine has been stopped.")
