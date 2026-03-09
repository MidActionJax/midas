import os
from dotenv import load_dotenv

load_dotenv()

TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER_FUTURES')
TRADING_SYMBOL = os.getenv('TRADING_SYMBOL', 'MES')

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

if TRADING_MODE not in ['PAPER_CRYPTO', 'LIVE_CRYPTO', 'PAPER_FUTURES']:
    raise ValueError("TRADING_MODE must be one of 'PAPER_CRYPTO', 'LIVE_CRYPTO', or 'PAPER_FUTURES'")
