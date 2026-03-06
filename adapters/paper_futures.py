import random
import time
from .base import TradingAdapter

class PaperFuturesAdapter(TradingAdapter):
    def __init__(self):
        self.paper_balance = 1000000.0
        self.last_price = 5000.0  # Starting price for our fake ES
        self.last_price_update = time.time()

    def get_wallet_balance(self):
        return self.paper_balance

    def get_current_price(self, symbol):
        """
        Generates a fake, slightly fluctuating price for demonstration purposes.
        """
        now = time.time()
        # Only update the price every few seconds to make it look more real
        if now - self.last_price_update > 3:
            change = random.uniform(-0.25, 0.25) 
            self.last_price += change
            self.last_price_update = now
        return round(self.last_price, 2)

    def get_market_depth(self, symbol):
        """
        Generates a fake order book around the current fake price.
        """
        price = self.get_current_price(symbol)
        bids = []
        asks = []
        for i in range(5):
            # Bids should be slightly lower than the price
            bid_price = price - (i * 0.25) - random.uniform(0.01, 0.05)
            bids.append([round(bid_price, 2), round(random.uniform(1, 10), 2)])
            
            # Asks should be slightly higher than the price
            ask_price = price + (i * 0.25) + random.uniform(0.01, 0.05)
            asks.append([round(ask_price, 2), round(random.uniform(1, 10), 2)])

        return {'bids': bids, 'asks': asks}

    def execute_buy(self, symbol, size, price): # Make sure this says 'size'
        try:
            # Your trade logic here...
            print(f"SIMULATION FUTURES BUY: {size} contracts of {symbol} at {price} USD.")
            return True
        except Exception as e:
            print(f"Error executing trade: {e}")
            return False
        
    def execute_sell(self, symbol, amount):
        price = self.get_current_price(symbol)
        print(f"SIMULATION FUTURES SELL: {amount} contracts of {symbol} at {price} USDT.")
        # No balance change in this simplified futures simulation
        return True
