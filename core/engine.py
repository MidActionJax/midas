import threading
import time
import config
from adapters.paper_crypto import PaperCryptoAdapter
from adapters.paper_futures import PaperFuturesAdapter
from adapters.nt_futures import NTFuturesAdapter # Add this line
from core import state, logic, logger

class MidasEngine(threading.Thread):
    def __init__(self, symbols):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.symbols = symbols
        self.adapter = None
        self.last_trade_time = 0

    def manage_positions(self):
        """Monitors active positions and triggers auto-sell based on PnL rules."""
        if not self.adapter:
            return
        # ... (rest of the manage_positions method remains the same for now) ...

    def run(self):
        print(f"MidasEngine starting for symbols: {self.symbols}")
        while not self._stop_event.is_set():
            if state.state_manager.is_kill_switch_active:
                print('!!! CRITICAL: DAILY DRAWDOWN LIMIT REACHED. SHUTTING DOWN !!!')
                self.stop()
                break

            if self.adapter is None:
                if config.TRADING_MODE == 'NT_FUTURES':
                    print("Initializing NTFuturesAdapter...")
                    self.adapter = NTFuturesAdapter(port=config.NT_PORT)
                elif config.TRADING_MODE == 'PAPER_FUTURES':
                    print("Initializing PaperFuturesAdapter...")
                    self.adapter = PaperFuturesAdapter()
                elif config.TRADING_MODE == 'PAPER_CRYPTO':
                    print("Initializing PaperCryptoAdapter...")
                    self.adapter = PaperCryptoAdapter()

            if self.adapter:
                try:
                    # --- Manage existing positions first ---
                    self.manage_positions()

                    # --- Cooldown period after a trade ---
                    if time.time() - self.last_trade_time < 300: # 5-minute cooldown
                        time.sleep(1)
                        continue
                    
                    # --- Process each symbol ---
                    for symbol in self.symbols:
                        price = self.adapter.get_current_price(symbol)
                        if price is None:
                            print(f"Could not fetch price for {symbol}. Skipping analysis.")
                            continue
                            
                        print(f"HEARTBEAT: Price of {symbol} is {price}")
                        state.state_manager.add_price(symbol, price)

                        # Only perform deep analysis for the execution symbol (MES)
                        if symbol == 'MES':
                            market_depth = self.adapter.get_market_depth(symbol)
                            state.state_manager.set_market_data(symbol, market_depth)

                            # Pass the entire price history map to the logic function
                            signal = logic.analyze_order_book(symbol, market_depth, state.state_manager.price_history)
                            if signal:
                                pending_signals = state.state_manager.get_pending_signals()
                                is_duplicate = any(s['price'] == signal['price'] and s['type'] == signal['type'] for s in pending_signals)
                                
                                if not is_duplicate:
                                    state.state_manager.add_pending_signal(signal)
                                    print(f"!!! NEW SIGNAL DETECTED: {signal['type']} at {signal['price']} for {signal['size']} with {signal['confidence_score']:.2f}% confidence!!!")

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
    import config 
    
    if engine_thread is None or not engine_thread.is_alive():
        symbols_to_trade = []
        # UPDATE THIS LINE to include NT_FUTURES
        if config.TRADING_MODE in ['PAPER_FUTURES', 'NT_FUTURES']: 
            symbols_to_trade = ['MES', 'MNQ']
            config.TRADING_SYMBOL = 'MES'
        else: # PAPER_CRYPTO or LIVE_CRYPTO
            symbols_to_trade = ['BTC/USDT']
            config.TRADING_SYMBOL = 'BTC/USDT'

        print(f"Engine starting in mode: {config.TRADING_MODE} for {symbols_to_trade}")
        engine_thread = MidasEngine(symbols_to_trade)
        engine_thread.start()

def stop_engine():
    global engine_thread
    if engine_thread and engine_thread.is_alive():
        # Safety Check: Only call disconnect if the adapter actually exists
        if engine_thread.adapter and hasattr(engine_thread.adapter, 'ib'):
            try:
                print("Disconnecting from IB...")
                engine_thread.adapter.ib.disconnect()
            except Exception as e:
                print(f"Error during disconnect: {e}")
        
        engine_thread.stop()
        engine_thread.join()
        engine_thread = None
        state.state_manager.save_price_history()
        print("MidasEngine stopped and price history saved.")
