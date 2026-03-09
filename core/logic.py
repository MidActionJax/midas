import time
import statistics
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9
    from backports.zoneinfo import ZoneInfo

from core.logger import log_signal
from config import TRADING_SYMBOL
from core.midas_model import MidasBrain

# Initialize the MidasBrain globally
brain = MidasBrain()
MIN_CONFIDENCE_THRESHOLD = 60


def get_market_session():
    """
    Determines the current market session based on EST.
    """
    try:
        est = ZoneInfo('US/Eastern')
        now_est = datetime.now(est).time()

        # Define session times
        ny_open_start = time(9, 30)
        ny_open_end = time(10, 30)
        overlap_start = time(8, 0)
        overlap_end = time(12, 0)

        if ny_open_start <= now_est < ny_open_end:
            return "New York Open"
        elif overlap_start <= now_est < overlap_end:
            return "London/NY Overlap"
        else:
            return "Other"
    except Exception:
        return "Unknown"

def calculate_whale_strength(iceberg_size, order_book):
    """
    Calculates the strength of an iceberg order relative to the rest of the book.
    """
    if not order_book or ('bids' not in order_book and 'asks' not in order_book):
        return 0.0

    all_sizes = [size for _, size in order_book.get('bids', [])] + \
                [size for _, size in order_book.get('asks', [])]

    if not all_sizes:
        return 0.0

    all_sizes.sort(reverse=True)
    top_5_sizes = all_sizes[:5]

    if not top_5_sizes:
        return 0.0

    avg_top_5_size = statistics.mean(top_5_sizes)

    if avg_top_5_size == 0:
        return 0.0

    strength = iceberg_size / avg_top_5_size
    return strength


def get_current_atr(price_history, period=14):
    """
    Calculates the Average True Range (ATR) as a measure of volatility.
    Uses a simplified True Range calculation based on price history.
    """
    if len(price_history) < period + 1:
        return 0.0  # Not enough data

    # Simplified True Range: absolute change between close prices
    true_ranges = [abs(price_history[i] - price_history[i-1]) for i in range(1, len(price_history))]
    
    if not true_ranges:
        return 0.0

    # ATR is the average of the true ranges over the specified period
    atr = statistics.mean(true_ranges[-period:])
    return atr


def calculate_ema(prices, period=200):
    """
    Calculates the Exponential Moving Average (EMA) for a list of prices.
    """
    if len(prices) < period:
        return None  # Not enough data
    
    # Use simple moving average for the first EMA value
    sma = sum(prices[:period]) / period
    ema = sma
    
    # Multiplier for weighting the EMA
    multiplier = 2 / (period + 1)
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
        
    return ema

def calculate_position_size(balance, price, price_history, risk_pct=0.01):
    """
    Calculates a dynamic position size based on account balance and market volatility (ATR).
    """
    if len(price_history) < 15: # Need at least 14 periods + one more for calculation
        return round( (balance * risk_pct) / price, 2) # Fallback to simple % of balance if not enough data

    # 1. Calculate True Range (simplified as absolute change between close prices)
    true_ranges = [abs(price_history[i] - price_history[i-1]) for i in range(1, len(price_history))]
    
    # 2. Calculate ATR over the last 14 periods
    if not true_ranges:
        return 0.01 # Should not happen with the length check, but as a safeguard.

    atr = statistics.mean(true_ranges[-14:])
    
    if atr == 0:
        return 0.01 # Avoid division by zero, return a minimum size

    # 3. Calculate Position Size in terms of the asset
    dollar_risk = balance * risk_pct
    position_size_asset = dollar_risk / atr

    # SURGICAL FIX: Check the current symbol to determine rounding
    from config import TRADING_SYMBOL
    
    if TRADING_SYMBOL == 'ES':
        # 1. Conservative Cap: Don't trade more notional value than your total balance
        # (Real futures use margin, but for Paper Trading, this keeps it sane)
        max_contracts = int(balance / price) 
        
        # 2. Final Size: Take the smaller of your risk calculation OR your account cap
        final_size = min(max_contracts, int(position_size_asset))
        
        # DEBUG PRINT TO VERIFY SPRINT 4 MATH
        print(f"--- POSITION MATH: Asset={TRADING_SYMBOL} | Final Size={final_size} | Risk={risk_pct*100}% ---")
        return max(1, final_size)
    else:
        # Crypto can handle decimals
        # DEBUG PRINT TO VERIFY SPRINT 4 MATH
        print(f"--- POSITION MATH: Asset={TRADING_SYMBOL} | Raw Size={position_size_asset:.4f} | Risk={risk_pct*100}% ---")
        return round(position_size_asset, 2)


def analyze_order_book(symbol, order_book, price_history_map, threshold=0.5):
    """
    Analyzes the order book to find large orders (icebergs), filtered by a trend indicator
    and correlated with a secondary symbol (MNQ).

    Args:
        symbol (str): The primary symbol being analyzed (e.g., 'MES').
        order_book (dict): The order book data with 'bids' and 'asks'.
        price_history_map (dict): A dictionary of price history lists, keyed by symbol.
        threshold (float): The size threshold to detect a large order.

    Returns:
        dict: A signal dictionary if a valid, trend-aligned large order is found, otherwise None.
    """
    if not order_book:
        return None

    # --- Identify Potential Signal ---
    signal = None
    if 'bids' in order_book and order_book['bids']:
        for price, size in order_book['bids']:
            if float(size) > threshold:
                signal = {'type': 'BUY_SIGNAL', 'price': price, 'size': float(size), 'reason': 'Iceberg Detected', 'timestamp': round(time.time(), 4)}
                break
    if not signal and 'asks' in order_book and order_book['asks']:
        for price, size in order_book['asks']:
            if float(size) > threshold:
                signal = {'type': 'SELL_SIGNAL', 'price': price, 'size': float(size), 'reason': 'Iceberg Detected', 'timestamp': round(time.time(), 4)}
                break
    if not signal:
        return None

    # --- Trend & Correlation Filtering ---
    price_history_mes = price_history_map.get('MES', [])
    price_history_mnq = price_history_map.get('MNQ', [])
    if not price_history_mes or not price_history_mnq:
        return None  # Silent during initialization

    current_price_mes = price_history_mes[-1]
    current_price_mnq = price_history_mnq[-1]
    
    ema_mes = calculate_ema(price_history_mes, period=200)
    ema_mnq = calculate_ema(price_history_mnq, period=200)

    from core.state import state_manager
    state_manager.ema_val['MES'] = ema_mes
    state_manager.ema_val['MNQ'] = ema_mnq

    if ema_mes is None or ema_mnq is None:
        print(f"--- TREND CHECK: Warming up... (MES: {len(price_history_mes)}/200, MNQ: {len(price_history_mnq)}/200) ---")
        return None

    trend_mes = "BULLISH" if current_price_mes > ema_mes else "BEARISH"
    trend_mnq = "BULLISH" if current_price_mnq > ema_mnq else "BEARISH"
    print(f"--- TREND CHECK: MES is {trend_mes} | MNQ is {trend_mnq} ---")

    # --- Correlation Logic ---
    correlation_bonus = 0
    if signal['type'] == 'BUY_SIGNAL':
        if trend_mes == "BULLISH" and trend_mnq == "BULLISH":
            correlation_bonus = 10  # Add 10% confidence
            print("--- CORRELATION: MNQ confirms bullish trend. +10% confidence bonus. ---")
        elif trend_mes == "BULLISH" and trend_mnq == "BEARISH":
            correlation_bonus = -25 # Subtract 25% confidence
            print("--- CORRELATION: MNQ contradicts bullish trend. -25% confidence penalty. ---")

    # Only generate signals for the primary execution symbol (MES)
    if symbol != 'MES':
        return None

    # --- Trend Filtering & Logging ---
    if (trend_mes == "BULLISH" and signal['type'] == 'BUY_SIGNAL') or \
       (trend_mes == "BEARISH" and signal['type'] == 'SELL_SIGNAL'):
        
        session_str = get_market_session()
        raw_whale_strength = calculate_whale_strength(signal['size'], order_book)
        scaled_whale_strength = min(raw_whale_strength / 5.0, 1.0) * 100
        session_map = {"London/NY Overlap": 100, "New York Open": 95, "Other": 70, "Unknown": 50}
        session_score = session_map.get(session_str, 60)

        ml_features = {
            'whale_strength': scaled_whale_strength,
            'trend_alignment': 100,
            'session_volume': session_score
        }
        
        confidence_score = brain.get_confidence_score(ml_features)
        
        # Apply correlation bonus/penalty
        final_confidence = confidence_score + correlation_bonus
        signal['confidence_score'] = final_confidence
        
        atr_volatility = get_current_atr(price_history_mes)
        
        signal_data = {
            'symbol': symbol,
            'type': signal['type'],
            'price': signal['price'],
            'size': signal['size'],
            'timestamp': signal['timestamp'],
            'confidence': final_confidence
        }
        context_data = {
            'ema_200': ema_mes,
            'trend': trend_mes,
            'atr': atr_volatility,
            'session_context': session_str,
            'whale_strength': raw_whale_strength,
            'correlation_bonus': correlation_bonus,
            'nasdaq_trend': trend_mnq
        }
        
        if final_confidence < MIN_CONFIDENCE_THRESHOLD:
            print(f"--- VETO: Signal confidence {final_confidence}% too low. Discarding. ---")
            log_signal(signal_data, context_data, 'AUTO_REJECTED')
            return None

        log_signal(signal_data, context_data, 'PENDING')
        
        return signal
    
    print(f"--- FILTERED: {signal['type']} blocked by {trend_mes} trend ---")
    return None