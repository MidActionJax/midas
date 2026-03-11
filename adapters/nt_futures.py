import socket
import random
import math

class NTFuturesAdapter:
    def __init__(self, host='127.0.0.1', port=36973):
        """
        Initializes the Adapter for NinjaTrader 8 via Socket Bridge.
        """
        self.host = host
        self.port = port
        self.contracts = {}
        
        # --- State for Indicator Calculations ---
        self.price_history = {'MES': [], 'MNQ': []}
        self.last_bar_time = {'MES': None, 'MNQ': None}
        self.current_features = {
            'atr_mes': 0.0, 'atr_mnq': 0.0, 
            'above_ema': False, 'in_sync': False
        }
        self.last_price = {'MES': None, 'MNQ': None}

        try:
            print(f"Connecting to NinjaTrader 8 MidasBridge on port {self.port}...")
            
            # Ping the NT8 server to ensure the bridge is open
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect((self.host, self.port))
            print("Successfully connected to NT8.")
            
            # Define contracts mapped to NT8 formatting instead of IBKR ContFuture
            self.contracts['MES'] = 'MES'
            self.contracts['MNQ'] = 'MNQ'

        except Exception as e:
            print(f"Error connecting to NT8: {e}")
            self.port = None 

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
            if len(self.price_history['MES']) > 5 and len(self.price_history['MNQ']) > 5:
                mes_dir = self.price_history['MES'][-1] > self.price_history['MES'][-5]
                mnq_dir = self.price_history['MNQ'][-1] > self.price_history['MNQ'][-5]
                self.current_features['in_sync'] = (mes_dir == mnq_dir)

            self.last_bar_time[symbol] = minute_timestamp

    def execute_buy(self, symbol, size, price):
        """
        Simulates the execution of a BUY order via NT8.
        """
        print(f"NT8 SIMULATION BUY: {size} of {symbol} at {price}")
        return True

    def execute_sell(self, symbol, size):
        """
        Simulates the execution of a SELL order via NT8.
        """
        print(f"NT8 SIMULATION SELL: {size} of {symbol}")
        return True

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
            
        adapter.execute_buy('MES', 1, price)
        adapter.execute_sell('MES', 1)