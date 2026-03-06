import threading
import time
import config
from adapters.paper_crypto import PaperCryptoAdapter
from core import state, logic

class MidasEngine(threading.Thread):
    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self.adapter = None
        self.daemon = True  # Allows main thread to exit even if this thread is running

    def run(self):
        print("MidasEngine starting...")
        while not self._stop_event.is_set():
            if self.adapter is None:
                if config.TRADING_MODE == 'PAPER_CRYPTO':
                    print("Initializing PaperCryptoAdapter...")
                    self.adapter = PaperCryptoAdapter()
                # Add other modes here in the future
                # elif config.TRADING_MODE == 'LIVE_CRYPTO':
                #     self.adapter = LiveCryptoAdapter()

            if self.adapter:
                try:
                    # Fetch and store market data
                    market_depth = self.adapter.get_market_depth(config.TRADING_SYMBOL)
                    state.state_manager.set_market_data(config.TRADING_SYMBOL, market_depth)

                    # Analyze for signals
                    signal = logic.analyze_order_book(market_depth)
                    if signal:
                        # Check for duplicate signals before adding
                        pending_signals = state.state_manager.get_pending_signals()
                        is_duplicate = False
                        for existing_signal in pending_signals:
                            if existing_signal['price'] == signal['price'] and existing_signal['type'] == signal['type']:
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            state.state_manager.add_pending_signal(signal)
                            print(f"!!! NEW SIGNAL DETECTED AND STORED: {signal['type']} at {signal['price']} for {signal['size']} !!!")

                    # Heartbeat
                    price = self.adapter.get_current_price(config.TRADING_SYMBOL)
                    print(f"HEARTBEAT: Current price of {config.TRADING_SYMBOL} is {price} USDT")

                except Exception as e:
                    print(f"Error in engine loop: {e}")
            
            time.sleep(5) # Increased sleep time to avoid spamming APIs and to give time for signals to be processed
        
        print("MidasEngine stopped.")

    def stop(self):
        print("Stopping MidasEngine...")
        self._stop_event.set()

engine_thread = None

def start_engine():
    """Starts the MidasEngine thread."""
    global engine_thread
    if engine_thread is None or not engine_thread.is_alive():
        engine_thread = MidasEngine()
        engine_thread.start()
        print("MidasEngine has been started.")

def stop_engine():
    """Stops the MidasEngine thread."""
    global engine_thread
    if engine_thread and engine_thread.is_alive():
        engine_thread.stop()
        engine_thread.join()
        engine_thread = None
        print("MidasEngine has been stopped.")
