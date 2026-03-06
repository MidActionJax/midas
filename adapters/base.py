from abc import ABC, abstractmethod

class TradingAdapter(ABC):
    @abstractmethod
    def get_wallet_balance(self):
        pass

    @abstractmethod
    def get_current_price(self, symbol):
        pass

    @abstractmethod
    def execute_buy(self, symbol, amount):
        pass

    @abstractmethod
    def execute_sell(self, symbol, amount):
        pass

    @abstractmethod
    def get_market_depth(self, symbol):
        pass
