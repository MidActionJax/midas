import os
from dotenv import load_dotenv

load_dotenv()

TRADING_MODE = os.getenv('TRADING_MODE', 'NT_FUTURES')
TRADING_SYMBOL = os.getenv('TRADING_SYMBOL', 'MES')

NT_PORT = 36999

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET = os.getenv('BINANCE_SECRET')

if TRADING_MODE not in ['PAPER_CRYPTO', 'LIVE_CRYPTO', 'PAPER_FUTURES', 'NT_FUTURES']:
    raise ValueError("TRADING_MODE must be one of 'PAPER_CRYPTO', 'LIVE_CRYPTO', 'PAPER_FUTURES', or 'NT_FUTURES'")
