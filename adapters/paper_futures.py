import math
import asyncio
from ib_insync import IB, ContFuture, util

class PaperFuturesAdapter:
    def __init__(self):
        """
        Initializes the Paper Trading Adapter for Interactive Brokers Futures.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.ib = IB()
        try:
            print("Connecting to Interactive Brokers TWS/Gateway...")
            self.ib.connect('127.0.0.1', 7497, clientId=1)
            print("Successfully connected to IB.")

            # Tell IB to use the free delayed data feed
            self.ib.reqMarketDataType(3)

            # Define the S&P 500 E-mini continuous futures contract
            self.contract = ContFuture('MES', 'CME')
            
            # Qualify the contract to make sure it's recognized by IB
            print("Qualifying contract...")
            self.ib.qualifyContracts(self.contract)
            print("Contract qualified.")

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
        Note: The 'symbol' parameter is for interface consistency but the contract is fixed.
        """
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        if not self.ib or not self.ib.isConnected():
            print("Not connected to IB.")
            return None
        
        try:
            ticker = self.ib.reqMktData(self.contract, '', False, False)
            self.ib.sleep(1) 

            if ticker and (ticker.last or ticker.close):
                return ticker.last if not math.isnan(ticker.last) else ticker.close
            else:
                print("Could not retrieve price data.")
                return None
        except Exception as e:
            print(f"Error fetching price data: {e}")
            return None

    # def get_market_depth(self, symbol):
    #     """
    #     Fetches Level 2 market depth and normalizes it.
    #     """
    #     if not self.ib or not self.ib.isConnected():
    #         print("Not connected to IB.")
    #         return None

    #     try:
    #         ticker = self.ib.reqMktDepth(self.contract, numRows=5, isSmartDepth=False)
    #         self.ib.sleep(1)

    #         bids = [{'price': b.price, 'size': b.size} for b in ticker.domBids]
    #         asks = [{'price': a.price, 'size': a.size} for a in ticker.domAsks]
            
    #         self.ib.cancelMktDepth(self.contract)
    #         return {'bids': bids, 'asks': asks}

    #     except Exception as e:
    #         print(f"Error fetching market depth: {e}")
    #         return None
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
        depth = adapter.get_market_depth('ES')
        if depth:
            print(f"\nMarket Depth for ES:\nBids: {depth['bids']}\nAsks: {depth['asks']}")
        else:
            print("\nFailed to get market depth for ES.")

        # Test fetching the current price
        price = adapter.get_current_price('ES')
        if price:
            print(f"\nCurrent price for ES: {price}")
        else:
            print("\nFailed to get current price for ES.")

        # Test simulated trades
        adapter.execute_buy('ES', 1)
        adapter.execute_sell('ES', 1)

    else:
        print("\nPaperFuturesAdapter failed to initialize.")
