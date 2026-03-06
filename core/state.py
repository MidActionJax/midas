import threading

class StateManager:
    def __init__(self):
        self.market_data = {}
        self.pending_signals = []
        self.trade_history = []
        self._lock = threading.Lock()

    def set_market_data(self, symbol, data):
        """Sets the market data for a given symbol."""
        with self._lock:
            self.market_data[symbol] = data

    def get_market_data(self, symbol=None):
        """Gets the market data for a given symbol, or all market data."""
        with self._lock:
            if symbol:
                return self.market_data.get(symbol)
            return self.market_data

    def add_pending_signal(self, signal):
        """Adds a new signal to the list of pending signals."""
        with self._lock:
            self.pending_signals.append(signal)

    def get_pending_signals(self):
        """Gets all pending signals."""
        with self._lock:
            return self.pending_signals[:]

    def remove_pending_signal(self, signal):
        """Removes a signal from the list of pending signals."""
        with self._lock:
            if signal in self.pending_signals:
                self.pending_signals.remove(signal)

    def add_trade_to_history(self, trade):
        """Adds a completed trade to the trade history."""
        with self._lock:
            self.trade_history.append(trade)

    def get_trade_history(self):
        """Gets the trade history."""
        with self._lock:
            return self.trade_history[:]

# Global state manager instance
state_manager = StateManager()