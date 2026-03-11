import time
import statistics
from datetime import datetime
import joblib
import os
import pandas as pd
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, 'models', 'midas_truth_engine.joblib')
TRUTH_ENGINE = None
MIN_CONFIDENCE_THRESHOLD = 60

if os.path.exists(MODEL_PATH):
    try:
        TRUTH_ENGINE = joblib.load(MODEL_PATH)
        print(f"INFO: Truth Engine loaded successfully from {MODEL_PATH}")
    except Exception as e:
        print(f"ERROR: Could not load Truth Engine: {e}")
else:
    print(f"WARNING: No model file found at {MODEL_PATH}. Check your folder structure.")


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

def is_volatility_safe(atr_mes):
    """
    Checks if the market volatility is within a safe range.
    """
    return 2.0 <= atr_mes <= 15.0

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
    if not order_book:
        return None

    # 1. Identify Potential Signal (Iceberg Detection)
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
    
    if not signal or symbol != 'MES':
        return None

    # 2. Get Market Context
    price_history_mes = price_history_map.get('MES', [])
    price_history_mnq = price_history_map.get('MNQ', [])
    if not price_history_mes or not price_history_mnq:
        return None

    current_price_mes = price_history_mes[-1]
    ema_mes = calculate_ema(price_history_mes, period=5) # Warmup/Testing period
    
    if ema_mes is None:
        return None

    trend_mes = "BULLISH" if current_price_mes > ema_mes else "BEARISH"
    
    # 3. Core Filter: Signal must match Trend
    if (trend_mes == "BULLISH" and signal['type'] == 'BUY_SIGNAL') or \
       (trend_mes == "BEARISH" and signal['type'] == 'SELL_SIGNAL'):
        
        # --- THE 4TH KEY: Volatility Gate ---
        atr_mes = get_current_atr(price_history_mes)
        if not is_volatility_safe(atr_mes):
            print(f"--- VETO: Volatility {atr_mes:.2f} out of range (2.0-15.0). ---")
            return None
        
        # --- THE TRUTH ENGINE: ML Veto ---
        if TRUTH_ENGINE:
            # Gather features for the model
            atr_mnq = get_current_atr(price_history_mnq)
            in_sync = (current_price_mes > ema_mes) == (price_history_mnq[-1] > calculate_ema(price_history_mnq, period=5))
            
            features = pd.DataFrame([{
                'atr_mes': atr_mes,
                'atr_mnq': atr_mnq,
                'above_ema': int(current_price_mes > ema_mes),
                'in_sync': int(in_sync),
                'hour': datetime.now().hour
            }])
            
            # Prediction
            probs = TRUTH_ENGINE.predict_proba(features)[0]
            success_prob = probs[1]
            ml_score_pct = success_prob * 100
            
            if success_prob < 0.60:
                print(f"ML VETO: Confidence too low ({ml_score_pct:.2f}%)")
                return None
            
            signal['ml_confidence'] = f"{ml_score_pct:.2f}%"
            print(f"ML SUCCESS: Approved with {ml_score_pct:.2f}% confidence")

        # 4. Success: Finalize and Log
        session_str = get_market_session()
        raw_whale_strength = calculate_whale_strength(signal['size'], order_book)
        
        context_data = {
            'ema_val': ema_mes,
            'trend': trend_mes,
            'atr': atr_mes,
            'session': session_str,
            'whale_strength': raw_whale_strength
        }
        
        log_signal(signal, context_data, 'PENDING')
        return signal

    print(f"--- FILTERED: {signal['type']} blocked by {trend_mes} trend ---")
    return None