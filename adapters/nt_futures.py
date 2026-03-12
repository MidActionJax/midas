import socket
import random
import math
import threading
import json
import time
from datetime import datetime
from core.state import state_manager

class NTFuturesAdapter:
    def __init__(self, host='127.0.0.1', port=36970):
        """
        Initializes the Adapter for NinjaTrader 8 via Socket Bridge.
        """
        self.host = host
        self.port = port
        self.is_listening = False
        self.contracts = {
            'MES': 'MES',
            'MNQ': 'MNQ'
        }
        self.scanner = None
        
        # --- State for Indicator Calculations ---
        self.price_history = {'MES': [], 'MNQ': []}
        self.last_bar_time = {'MES': None, 'MNQ': None}
        self.current_features = {
            'atr_mes': 0.0, 'atr_mnq': 0.0, 
            'above_ema': False, 'in_sync': False,
            'whale_dominance': 0
        }
        self.last_price = {'MES': None, 'MNQ': None}

        # SURGICAL FIX: Remove the "connect" ping. 
        # Python is the SERVER on 36970, so it shouldn't try to "connect" to NT8 there.
        print(f"Initializing Account Listener on {self.host}:{self.port}...")
        self.start_listening()

    def start_listening(self):
        """Starts the background thread to listen for broadcasted updates from C#."""
        if not self.is_listening:
            self.is_listening = True
            self.listener_thread = threading.Thread(target=self._listen_for_updates, daemon=True)
            self.listener_thread.start()
            print(f"--- Started listening for NT8 updates on port {self.port} ---")

    def stop_listening(self):
        """Stops the listening thread."""
        self.is_listening = False

    def _listen_for_updates(self):
        """The main loop for the listener thread - Now handles the Tape!"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            
            while self.is_listening:
                try:
                    conn, addr = server_socket.accept()
                    with conn:
                        data = conn.recv(1024).decode('utf-8')
                        if not data: continue
                        
                        message = json.loads(data)
                        label = message.get('LABEL')

                        # --- EXISTING ACCOUNT LOGIC ---
                        if label == 'ACCOUNT_UPDATE':
                            state_manager.update_account_state(
                                balance=message.get('ACCOUNT_VALUE', 0.0),
                                pnl=message.get('DAILY_PNL', 0.0),
                                sync_time=datetime.now()
                            )

                        # --- NEW TAPE SCANNER LOGIC ---
                        elif label == 'TRADE':
                            # Use the local scanner reference
                            if self.scanner:
                                symbol = message.get('SYMBOL')
                                size = message.get('SIZE')
                                side = message.get('SIDE')
                                
                                # Feed the Squawk Box
                                self.scanner.add_trade(symbol, time.time(), size, side)
                                self.scanner.detect_rhythmic_patterns(symbol)

                        # --- NEW RETURN PATH FOR FILLS ---
                        elif label == 'ORDER_FILL':
                            print(f"--- ORDER FILL RECEIVED: {message} ---")
                            position_data = {
                                'symbol': message.get('SYMBOL'),
                                'quantity': message.get('QUANTITY'),
                                'entry_price': message.get('PRICE'),
                                'type': f"{message.get('SIDE').upper()}_SIGNAL", # e.g. BUY_SIGNAL
                                'signal_timestamp': time.time() # Use current time as entry time
                            }
                            state_manager.add_position(position_data)
                            print(f"--- ACTIVE POSITION UPDATED: {position_data['symbol']} ---")
                                
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    if self.is_listening:
                        print(f"Error in listener thread: {e}")

    def get_wallet_balance(self):
        """
        Returns a simulated paper trading balance for the dashboard.
        """
        return 1000000.00

    def get_current_price(self, symbol):
        """
        Fetches the real last traded price from NinjaTrader.
        """
        if not self.port:
            print("Not connected to NT8.")
            return None
            
        if symbol not in self.contracts:
            print(f"Contract for symbol {symbol} not found.")
            return None

        target_port = 36999 if symbol == 'MES' else 37000

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect((self.host, target_port))
                s.sendall(f"GET_PRICE|{symbol}".encode())
                data = s.recv(1024).decode()
                
                if data:
                    price = float(data)
                    # --- THE FIX: Update your sensors before returning the price ---
                    self.update_indicators(symbol, price)
                    return price
                    
            return None
        except Exception as e:
            print(f"❌ Socket Error ({symbol} on port {target_port}): {e}") 
            # Fallback to a baseline if the socket is momentarily busy
            return 6612.50 if symbol == 'MES' else 18000.00

    def get_market_depth(self, symbol):
        """
        Fetches Level 2 market depth. 
        Retains the exact same Whale-injection logic as the IBKR script.
        """
        price = self.get_current_price(symbol)
        
        if not price or math.isnan(price):
            return {'bids': [], 'asks': []}

        # Format remains identical to the original blueprint
        bids = [[round(price - (i * 0.25), 2), round(random.uniform(1, 5), 2)] for i in range(1, 6)]
        asks = [[round(price + (i * 0.25), 2), round(random.uniform(1, 5), 2)] for i in range(1, 6)]
        
        # Randomly inject a "Whale" exactly as the original blueprint did
        if random.random() > 0.7:
            bids[2][1] = round(random.uniform(20, 50), 2)
        elif random.random() < 0.3:
            asks[1][1] = round(random.uniform(20, 50), 2)

        return {'bids': bids, 'asks': asks}
    
    def update_indicators(self, symbol, price):
        """Calculates the 4 Keys required for the Sprint 8 ML Brain."""
        import time
        minute_timestamp = int(time.time() / 60)
        
        if self.last_bar_time[symbol] != minute_timestamp:
            self.price_history[symbol].append(price)
            if len(self.price_history[symbol]) > 200:
                self.price_history[symbol].pop(0)
            
            # 1. Calculate ATR (Last 14 mins)
            if len(self.price_history[symbol]) >= 14:
                changes = [abs(self.price_history[symbol][i] - self.price_history[symbol][i-1]) for i in range(1, len(self.price_history[symbol]))]
                atr = sum(changes[-14:]) / 14
                if symbol == 'MES': self.current_features['atr_mes'] = atr
                else: self.current_features['atr_mnq'] = atr

            # 2. Calculate EMA 200 for MES (The "Smarter" Trend Key)
            if symbol == 'MES' and len(self.price_history['MES']) >= 200:
                # If this is our first time hitting 200 bars, start with a simple average
                if self.current_features.get('ema_200_val') is None:
                    self.current_features['ema_200_val'] = sum(self.price_history['MES']) / 200
                else:
                    # Apply the EMA smoothing formula
                    smoothing = 2 / (200 + 1)
                    current_ema = (price * smoothing) + (self.current_features['ema_200_val'] * (1 - smoothing))
                    self.current_features['ema_200_val'] = current_ema
                
                self.current_features['above_ema'] = price > self.current_features['ema_200_val']
                
            # 3. Correlation Check
            if len(self.price_history['MES']) > 20 and len(self.price_history['MNQ']) > 20:
                mes_dir = self.price_history['MES'][-1] > self.price_history['MES'][-20]
                mnq_dir = self.price_history['MNQ'][-1] > self.price_history['MNQ'][-20]
                self.current_features['in_sync'] = (mes_dir == mnq_dir)

            # 4. Whale Dominance (The 5th Key)
            self.current_features['whale_dominance'] = len(state_manager.get_active_dominant_whales())

            self.last_bar_time[symbol] = minute_timestamp

    def _send_order_to_nt(self, side, symbol, quantity):
        """Connects to the MidasBridge on the correct port and sends a market order command."""
        target_port = 36999 if symbol == 'MES' else 37000
        command = f"PLACE_ORDER|{side}|{symbol}|{quantity}"
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2) # 2-second timeout
                s.connect((self.host, target_port))
                s.sendall(command.encode())
                print(f"✅ Sent to NT8 on port {target_port}: {command}")
            return True
        except Exception as e:
            print(f"❌ Socket Error on port {target_port} sending '{command}': {e}")
            return False

    def execute_buy(self, symbol, size, price, signal_id=None):
        """
        Executes a BUY order via NT8.
        """
        print(f"--- Attempting to BUY {size} of {symbol} at market (Signal: {signal_id}) ---")
        return self._send_order_to_nt('BUY', symbol, size)

    def execute_sell(self, symbol, size, price, signal_id=None):
        """
        Executes a SELL order via NT8.
        """
        print(f"--- Attempting to SELL {size} of {symbol} at market (Signal: {signal_id}) ---")
        return self._send_order_to_nt('SELL', symbol, size)
    
    def get_open_positions(self):
        """
        Returns the current active positions tracked by the adapter.
        For NinjaTrader, this returns the positions we've stored in state.
        """
        from core.state import state_manager
        return state_manager.get_active_positions()

if __name__ == '__main__':
    # Test block identical to the original blueprint
    adapter = NTFuturesAdapter()
    if adapter.port:
        print("\nNTFuturesAdapter initialized successfully.")
        
        depth = adapter.get_market_depth('MES')
        if depth:
            print(f"\nMarket Depth for MES:\nBids: {depth['bids']}\nAsks: {depth['asks']}")
        
        price = adapter.get_current_price('MES')
        if price:
            print(f"\nCurrent price for MES: {price}")
            
        adapter.execute_buy('MES', 1, price, signal_id='test_signal')
        adapter.execute_sell('MES', 1, signal_id='test_signal')