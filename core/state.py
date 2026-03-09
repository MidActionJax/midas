import threading

class StateManager:
    """
    Manages the shared state between the Flask web server and the background trading engine.
    Uses a thread-safe lock to prevent race conditions.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.market_data = {}
        self.pending_signals = []
        self.active_positions = []
        self.realized_pnl = 0.0
        self.trade_history = []
        self.price_history = []
        self.daily_drawdown_limit = -500.0

    @property
    def is_kill_switch_active(self):
        with self._lock:
            return self.realized_pnl <= self.daily_drawdown_limit

    def set_market_data(self, symbol, data):
        with self._lock:
            self.market_data[symbol] = data

    def get_market_data(self, symbol):
        with self._lock:
            return self.market_data.get(symbol)

    def add_pending_signal(self, signal):
        with self._lock:
            self.pending_signals.append(signal)

    def get_pending_signals(self):
        with self._lock:
            return list(self.pending_signals)

    def remove_pending_signal(self, signal_to_remove):
        with self._lock:
            # Rebuilding list without the removed signal
            self.pending_signals = [s for s in self.pending_signals if s['timestamp'] != signal_to_remove['timestamp']]

    def add_position(self, pos):
        with self._lock:
            self.active_positions.append(pos)

    def remove_position(self, pos):
        with self._lock:
            if pos in self.active_positions:
                self.active_positions.remove(pos)

    def get_active_positions(self):
        with self._lock:
            return list(self.active_positions)

    def add_pnl(self, amount):
        with self._lock:
            self.realized_pnl += amount
            if self.is_kill_switch_active:
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                print("!!! WARNING: DAILY DRAWDOWN LIMIT HIT - KILL SWITCH ACTIVE !!!")
                print(f"!!! REALIZED PNL: {self.realized_pnl:.2f} / {self.daily_drawdown_limit:.2f} !!!")
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    def get_realized_pnl(self):
        with self._lock:
            return self.realized_pnl

    def add_trade_to_history(self, trade):
        with self._lock:
            self.trade_history.append(trade)

    def add_price(self, price):
        with self._lock:
            self.price_history.append(price)
            self.price_history = self.price_history[-5:]

# Instantiate the global state manager
state_manager = StateManager()