import threading

class StateManager:
    def __init__(self):
        self.market_data = {}
        self.pending_signals = []
        self.trade_history = []
        self.active_positions = []
        self.realized_pnl = 0.0
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

    def add_position(self, pos):
        with self._lock:
            self.active_positions.append(pos)

    def remove_position(self, pos):
        with self._lock:
            if pos in self.active_positions:
                self.active_positions.remove(pos)

    def get_active_positions(self):
        with self._lock:
            return self.active_positions.copy()

    def add_pnl(self, amount):
        with self._lock:
            self.realized_pnl += amount

    def get_realized_pnl(self):
        with self._lock:
            return self.realized_pnl

# Global state manager instance
state_manager = StateManager()
