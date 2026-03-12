import threading
import time
import config
from adapters.paper_crypto import PaperCryptoAdapter
from adapters.paper_futures import PaperFuturesAdapter
from adapters.nt_futures import NTFuturesAdapter # Add this line
from core import state, logic, logger
from core.logic import TapeScanner

class MidasEngine(threading.Thread):
    def __init__(self, symbols):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.symbols = symbols
        self.adapter = None
        self.last_trade_time = 0
        self.scanner = TapeScanner()

    def manage_positions(self):
        """Monitors active positions, updates PnL, and logs closed trades."""
        if not self.adapter:
            return

        try:
            live_positions = self.adapter.get_open_positions()
            tracked_positions = state.state_manager.get_active_positions()

            live_map = { (p.get('symbol'), p.get('type')): p for p in live_positions }
            
            # Use a copy for safe iteration while removing
            for pos in list(tracked_positions):
                pos_type = 'LONG' if 'BUY' in pos.get('type', 'BUY_SIGNAL') else 'SHORT'
                key = (pos.get('symbol'), pos_type)

                if key in live_map:
                    # Position is still open, update its PnL in our state.
                    # This requires a new method in StateManager or re-adding the position.
                    # For simplicity, we'll just add the PNL to the dictionary that we will process later.
                    live_pnl = live_map[key].get('pnl', 0.0)
                    pos['unrealized_pnl'] = live_pnl
                else:
                    # --- DEV MODE STABILITY ---
                    if state.state_manager.dev_mode:
                        entry_time = pos.get('signal_timestamp', 0)
                        if time.time() - entry_time < 30:
                            print(f"--- DEV MODE: Delaying exit detection for {pos['symbol']} ---")
                            continue # Skip exit logic for 30 seconds

                    # Position is closed.
                    final_pnl = pos.get('unrealized_pnl', 0.0)
                    reason = "Exit Detected" # We don't know the exact reason (TP/SL) from this logic.

                    # Log the exit to the CSV
                    logger.log_trade_exit(pos['signal_timestamp'], final_pnl, reason)

                    # Update the global realized PnL
                    state.state_manager.add_pnl(final_pnl)

                    # Remove from state manager's active list
                    state.state_manager.remove_position(pos)
                    
                    print(f"--- DETECTED CLOSED POSITION: {pos['symbol']} | PnL: {final_pnl} ---")
                    # Set cooldown to prevent immediate re-entry
                    self.last_trade_time = time.time()
        except Exception as e:
            print(f"Error in manage_positions: {e}")

    def run(self):
        print(f"MidasEngine starting for symbols: {self.symbols}")
        while not self._stop_event.is_set():
            if state.state_manager.is_kill_switch_active:
                print('!!! CRITICAL: DAILY DRAWDOWN LIMIT REACHED. SHUTTING DOWN !!!')
                self.stop()
                break

            if self.adapter is None:
                if config.TRADING_MODE == 'NT_FUTURES':
                    print(f"Initializing NTFuturesAdapter on Account Port: {config.NT_PORT}")
                    self.adapter = NTFuturesAdapter(port=config.NT_PORT)
                    self.adapter.scanner = self.scanner
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
                            signal = logic.analyze_order_book(symbol, market_depth, state.state_manager.price_history, self.adapter)
                            if signal:
                                pending_signals = state.state_manager.get_pending_signals()
                                is_duplicate = any(s['price'] == signal['price'] and s['type'] == signal['type'] for s in pending_signals)
                                
                                if not is_duplicate:
                                    state.state_manager.add_pending_signal(signal)
                                    confidence_score_str = f"{signal.get('confidence_score', 0):.2f}%" if 'confidence_score' in signal else 'N/A (DEV)'
                                    print(f"!!! NEW SIGNAL DETECTED: {signal['type']} at {signal['price']} for {signal['size']} with {confidence_score_str} confidence!!!")

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
