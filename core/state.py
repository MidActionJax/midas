import threading
import json
import os
import time

class StateManager:
    """
    Manages the shared state between the Flask web server and the background trading engine.
    Uses a thread-safe lock to prevent race conditions.
    """
    def __init__(self, state_file='ema_state.json'):
        self._lock = threading.Lock()
        self.market_data = {}
        self.pending_signals = []
        self.active_positions = []
        self.realized_pnl = 0.0
        self.trade_history = []
        self.price_history = {'MES': [], 'MNQ': []}
        self.ema_val = {'MES': None, 'MNQ': None}
        self.detected_whales = []
        self.whale_activity = {}
        self.whale_last_seen = {}
        self.active_dominant_whales = []
        self.daily_drawdown_limit = -500.0
        # New account state fields
        self.account_balance = 0.0
        self.daily_pnl = 0.0
        self.last_sync_time = None
        self.master_trading_mode = 'PAPER' # New master switch
        self.sizing_mode = 'FIXED' # New sizing mode
        self.session_start_balance = 0.0
        self.pnl_at_last_approval = None
        self.live_wins = 0
        self.live_trades = 0
        self.dev_mode = False # Add dev_mode
        self.state_file = state_file
        self.load_price_history()

    def toggle_dev_mode(self):
        """Toggles the developer mode."""
        with self._lock:
            self.dev_mode = not self.dev_mode
            print(f"--- Developer Mode set to: {self.dev_mode} ---")
        return self.dev_mode

    @property
    def is_kill_switch_active(self):
        with self._lock:
            return self.realized_pnl <= self.daily_drawdown_limit

    def set_master_trading_mode(self, mode):
        """Sets the master trading mode (PAPER or LIVE)."""
        with self._lock:
            if mode in ['PAPER', 'LIVE']:
                self.master_trading_mode = mode
                print(f"--- Master Trading Mode set to: {mode} ---")

    def set_sizing_mode(self, mode):
        """Sets the position sizing mode (FIXED or AUTO)."""
        with self._lock:
            if mode in ['FIXED', 'AUTO']:
                self.sizing_mode = mode
                print(f"--- Sizing Mode set to: {mode} ---")

    def set_signal_approved(self):
        """Flags that a signal was just approved to track PnL outcome."""
        with self._lock:
            self.pnl_at_last_approval = self.daily_pnl

    def update_account_state(self, balance, pnl, sync_time):
        """Thread-safe method to update account-related state."""
        with self._lock:
            # Set the starting balance for the session on the first update
            if self.session_start_balance == 0.0 and balance > 0:
                self.session_start_balance = balance

            # Check for outcome of a tracked trade
            if self.pnl_at_last_approval is not None:
                if pnl > self.pnl_at_last_approval:
                    self.live_wins += 1
                self.live_trades += 1
                self.pnl_at_last_approval = None # Reset after checking

            self.account_balance = balance
            self.daily_pnl = pnl
            self.last_sync_time = sync_time

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

    def add_detected_whale(self, whale):
        """
        Adds a detected whale pattern, tracks its frequency, and identifies dominant whales.
        """
        with self._lock:
            whale_id = whale.get('whale_id')
            if not whale_id:
                return

            now = time.time()
            last_seen = self.whale_last_seen.get(whale_id, 0)

            if now - last_seen > 10:  # 10-second cooldown
                print(f"--- RHYTHMIC PATTERN DETECTED [{whale.get('symbol')}]: {whale_id} ---")
                self.whale_last_seen[whale_id] = now
            
            self.detected_whales.append(whale)

            if whale_id not in self.whale_activity:
                self.whale_activity[whale_id] = []
            
            # Add current timestamp and prune old ones
            self.whale_activity[whale_id].append(now)
            five_mins_ago = now - 300  # 5 minutes in seconds
            self.whale_activity[whale_id] = [ts for ts in self.whale_activity[whale_id] if ts > five_mins_ago]
            
            # Check for dominance
            if len(self.whale_activity[whale_id]) > 5:
                if whale_id not in self.active_dominant_whales:
                    self.active_dominant_whales.append(whale_id)
                    print(f"--- New Dominant Whale Labeled: {whale_id} ---")

    def get_detected_whales(self):
        with self._lock:
            return list(self.detected_whales)

    def get_active_dominant_whales(self):
        with self._lock:
            return list(self.active_dominant_whales)


    def add_trade_to_history(self, trade):
        with self._lock:
            self.trade_history.append(trade)

    def add_price(self, symbol, price):
        with self._lock:
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(price)
            self.price_history[symbol] = self.price_history[symbol][-200:]

    def save_price_history(self):
        with self._lock:
            with open(self.state_file, 'w') as f:
                json.dump(self.price_history, f)

    def load_price_history(self):
        if not os.path.exists(self.state_file):
            return
        with self._lock:
            with open(self.state_file, 'r') as f:
                self.price_history = json.load(f)
            print(f"--- Loaded price history from {self.state_file} ---")
            for symbol, prices in self.price_history.items():
                print(f"    - {symbol}: {len(prices)} prices")

# Instantiate the global state manager
state_manager = StateManager()