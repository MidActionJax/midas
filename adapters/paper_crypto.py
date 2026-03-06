import ccxt
from .base import TradingAdapter

class PaperCryptoAdapter(TradingAdapter):
    def __init__(self):
        self.paper_balance = 1000000.0  # Initial paper trading balance in USDT
        self.binance = ccxt.binanceus()

    def get_wallet_balance(self):
        return self.paper_balance

    def get_current_price(self, symbol):
        ticker = self.binance.fetch_ticker(symbol)
        return ticker['last']

    def get_market_depth(self, symbol):
        order_book = self.binance.fetch_order_book(symbol, limit=5)
        return {
            'bids': order_book['bids'],
            'asks': order_book['asks']
        }

    def execute_buy(self, symbol, amount):
        price = self.get_current_price(symbol)
        cost = price * amount
        if self.paper_balance >= cost:
            self.paper_balance -= cost
            print(f"SIMULATION BUY: {amount} {symbol.split('/')[0]} at {price} USDT. New balance: {self.paper_balance} USDT")
            return True
        else:
            print("SIMULATION BUY FAILED: Insufficient funds.")
            return False

    def execute_sell(self, symbol, amount):
        price = self.get_current_price(symbol)
        gain = price * amount
        self.paper_balance += gain
        print(f"SIMULATION SELL: {amount} {symbol.split('/')[0]} at {price} USDT. New balance: {self.paper_balance} USDT")
        return True
