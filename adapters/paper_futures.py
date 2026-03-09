import math
import asyncio
import random
from ib_insync import IB, ContFuture, util

class PaperFuturesAdapter:
    def __init__(self):
        """
        Initializes the Paper Trading Adapter for Interactive Brokers Futures.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.ib = IB()
        self.contracts = {}
        try:
            client_id = random.randint(1, 99)
            print(f"Connecting to Interactive Brokers TWS/Gateway with Client ID: {client_id}...")
            
            self.ib.connect('127.0.0.1', 7497, clientId=client_id)
            print("Successfully connected to IB.")

            # Tell IB to use the free delayed data feed
            self.ib.reqMarketDataType(3)

            # Define the S&P 500 E-mini and Nasdaq 100 E-mini continuous futures contracts
            self.contracts['MES'] = ContFuture('MES', 'CME')
            self.contracts['MNQ'] = ContFuture('MNQ', 'CME')
            
            # Qualify the contracts to make sure they're recognized by IB
            print("Qualifying contracts...")
            self.ib.qualifyContracts(*self.contracts.values())
            print("Contracts qualified.")

        except Exception as e:
            print(f"Error connecting to IB or qualifying contract: {e}")
            self.ib = None 

    def get_wallet_balance(self):
        """
        Returns a simulated paper trading balance for the dashboard.
        """
        return 1000000.00

    def get_current_price(self, symbol):
        """
        Fetches the last traded price for the qualified contract.
        """
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        if not self.ib or not self.ib.isConnected():
            print("Not connected to IB.")
            return None
        
        if symbol not in self.contracts:
            print(f"Contract for symbol {symbol} not found.")
            return None

        try:
            contract = self.contracts[symbol]
            ticker = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(1) 

            if ticker and (ticker.last or ticker.close):
                return ticker.last if not math.isnan(ticker.last) else ticker.close
            else:
                print(f"Could not retrieve price data for {symbol}.")
                return None
        except Exception as e:
            print(f"Error fetching price data for {symbol}: {e}")
            return None

    def get_market_depth(self, symbol):
        """
        Fetches Level 2 market depth.
        (Simulated for Free Trial accounts since IBKR blocks Level 2 data)
        """
        import random
        price = self.get_current_price(symbol)
        
        if not price or math.isnan(price):
            return {'bids': [], 'asks': []}

        # Change the format from {'price': p, 'size': s} to [p, s]
        bids = [[round(price - (i * 0.25), 2), round(random.uniform(1, 5), 2)] for i in range(1, 6)]
        asks = [[round(price + (i * 0.25), 2), round(random.uniform(1, 5), 2)] for i in range(1, 6)]
        
        # Randomly inject a "Whale"
        if random.random() > 0.7:
            bids[2][1] = round(random.uniform(20, 50), 2)
        elif random.random() < 0.3:
            asks[1][1] = round(random.uniform(20, 50), 2)

        return {'bids': bids, 'asks': asks}

    def execute_buy(self, symbol, size, price):
        """
        Simulates the execution of a BUY order.
        """
        print(f"SIMULATION FUTURES BUY: {size} of {symbol}")
        return True

    def execute_sell(self, symbol, size):
        """
        Simulates the execution of a SELL order.
        """
        print(f"SIMULATION FUTURES SELL: {size} of {symbol}")
        return True

    def __del__(self):
        """
        Destructor to ensure disconnection from IB.
        """
        if self.ib and self.ib.isConnected():
            print("Disconnecting from IB...")
            self.ib.disconnect()

# Example of how to run this for testing:
if __name__ == '__main__':
    util.patchAsyncio()
    
    adapter = PaperFuturesAdapter()
    if adapter.ib:
        print("\nPaperFuturesAdapter initialized successfully.")
        
        # Test fetching market depth
        depth = adapter.get_market_depth('MES')
        if depth:
            print(f"\nMarket Depth for MES:\nBids: {depth['bids']}\nAsks: {depth['asks']}")
        else:
            print("\nFailed to get market depth for MES.")

        # Test fetching the current price
        price = adapter.get_current_price('MES')
        if price:
            print(f"\nCurrent price for MES: {price}")
        else:
            print("\nFailed to get current price for MES.")
            
        # Test fetching the current price
        price_mnq = adapter.get_current_price('MNQ')
        if price_mnq:
            print(f"\nCurrent price for MNQ: {price_mnq}")
        else:
            print("\nFailed to get current price for MNQ.")

        # Test simulated trades
        adapter.execute_buy('MES', 1, price)
        adapter.execute_sell('MES', 1)

    else:
        print("\nPaperFuturesAdapter failed to initialize.")
