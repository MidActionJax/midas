import time
import statistics
from collections import deque, namedtuple
from datetime import datetime
import joblib
import os
import pandas as pd
import numpy as np
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9
    from backports.zoneinfo import ZoneInfo

from core.logger import log_signal
from config import TRADING_SYMBOL, POSITION_MODE
from core.midas_model import MidasBrain
from core.state import state_manager

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


Trade = namedtuple('Trade', ['timestamp', 'size', 'side'])


def generate_whale_id(pattern):
    """Generates a unique ID for a whale pattern."""
    size = pattern['size']
    frequency = pattern['frequency']
    return f"Whale_{size}_{int(frequency)}s"


class TapeScanner:
    """
    Scans the tape for rhythmic institutional footprints, like 'shredder' algorithms.
    """
    def __init__(self, buffer_size=100):
        self.trades = {
            'MES': deque(maxlen=buffer_size),
            'MNQ': deque(maxlen=buffer_size)
        }

    def add_trade(self, symbol, timestamp, size, side):
        """Adds a new trade to the respective symbol's buffer."""
        if symbol in self.trades:
            self.trades[symbol].append(Trade(timestamp, size, side))

    def detect_rhythmic_patterns(self, symbol, min_sequence=3, time_tolerance=0.5):
        """
        Detects rhythmic patterns for a given symbol.
        Looks for a sequence of trades of the same size occurring at regular intervals.
        """
        if symbol not in self.trades or len(self.trades[symbol]) < min_sequence:
            return None

        trades = sorted(list(self.trades[symbol]), key=lambda t: t.timestamp)
        
        # Group trades by size
        trades_by_size = {}
        for trade in trades:
            if trade.size not in trades_by_size:
                trades_by_size[trade.size] = []
            trades_by_size[trade.size].append(trade)

        # Analyze each group for rhythmic patterns
        for size, trade_group in trades_by_size.items():
            # --- ADD THIS CHECK TO FILTER RETAIL NOISE ---
            noise_filter = 1 if state_manager.dev_mode else 10
            if size < noise_filter:
                continue # Ignore anything less than the filter


            if len(trade_group) < min_sequence:
                continue

            # Check for sequences with consistent time intervals and side
            for i in range(len(trade_group) - (min_sequence - 1)):
                base_sequence = trade_group[i:i+min_sequence]
                
                # Check for consistent side
                base_side = base_sequence[0].side
                if not all(t.side == base_side for t in base_sequence):
                    continue

                # Check for rhythmic timing
                intervals = [base_sequence[j+1].timestamp - base_sequence[j].timestamp for j in range(len(base_sequence)-1)]
                if not intervals:
                    continue

                first_interval = intervals[0]
                is_rhythmic = all(abs(interval - first_interval) <= time_tolerance for interval in intervals)

                if is_rhythmic:
                    avg_frequency = statistics.mean(intervals)
                    pattern = {
                        'size': size,
                        'frequency': round(avg_frequency, 2),
                        'side': base_side,
                        'symbol': symbol,
                        'count': len(base_sequence)
                    }
                    
                    # Fingerprint and Store
                    pattern['whale_id'] = generate_whale_id(pattern)
                    # print(f"--- RHYTHMIC PATTERN DETECTED [{symbol}]: {pattern['whale_id']} ---")
                    state_manager.add_detected_whale(pattern)
                    return pattern
        
        return None


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


def calculate_choppiness_index(df, period=14):
    """
    Calculates the Choppiness Index (CHOP).
    Requires a DataFrame with 'high', 'low', and 'close' columns.
    """
    if not all(k in df.columns for k in ['high', 'low', 'close']) or len(df) < period:
        return 50.0 # Default to neutral if not enough data

    # Calculate True Range
    tr1 = pd.DataFrame(df['high'] - df['low'])
    tr2 = pd.DataFrame(abs(df['high'] - df['close'].shift(1)))
    tr3 = pd.DataFrame(abs(df['low'] - df['close'].shift(1)))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate Average True Range (ATR)
    atr = tr.ewm(span=period, adjust=False).mean()

    # Sum of ATR over the period
    atr_sum = atr.rolling(window=period).sum()

    # Highest High and Lowest Low over the period
    highest_high = df['high'].rolling(window=period).max()
    lowest_low = df['low'].rolling(window=period).min()

    # Calculate Choppiness Index
    numerator = atr_sum
    denominator = highest_high - lowest_low
    
    # Avoid division by zero
    chop = np.where(denominator == 0, 100, 100 * np.log10(numerator / denominator) / np.log10(period))
    
    # Return the last value, ensure it's a float
    return float(chop[-1]) if len(chop) > 0 else 50.0


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

def calculate_position_size(price, price_history, risk_pct=0.01):
    """
    Calculates a dynamic position size based on account balance and market volatility (ATR).
    Respects the sizing_mode setting from the state manager.
    """
    # Logic for position mode from state manager
    if state_manager.sizing_mode == 'FIXED':
        return 1

    # AUTO mode logic
    balance = state_manager.account_balance
    if balance <= 0:
        print("WARNING: Account balance is zero or negative. Cannot calculate AUTO position size.")
        return 0 # Return 0 to prevent trades

    # 1 contract per $5,000 of balance
    contracts = int(balance / 5000)
    return contracts


def analyze_order_book(symbol, order_book, price_history_map, adapter=None, threshold=0.5):
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

    # --- DEV MODE OVERRIDE ---
    if state_manager.dev_mode:
        # We bypass the complex ML and trend filters, but DO NOT auto-execute.
        # We tag it as a DEV signal and return it so it hits the Approval Queue.
        signal['confidence_score'] = 99.99 # Fake high confidence for UI
        signal['reason'] = 'DEV Override'
        print("--- DEV MODE: Signal bypasses filters -> Sent to Approval Queue ---")

        # SURGICAL FIX: Log the DEV signal so the CSV knows it exists
        dummy_context = {'ema_val': 0, 'trend': 'DEV', 'atr': 0, 'session': 'DEV', 'whale_strength': 0}
        log_signal(signal, dummy_context, 'PENDING')
        return signal

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

            # --- THE 5TH KEY: Institutional Sync ---
            dominant_whales = state_manager.get_active_dominant_whales()
            if dominant_whales:
                all_whales = state_manager.get_detected_whales()
                for whale_id in dominant_whales:
                    # Find the most recent pattern for this whale_id
                    whale_pattern = next((w for w in reversed(all_whales) if w.get('whale_id') == whale_id), None)
                    if whale_pattern:
                        whale_side = whale_pattern.get('side')
                        signal_side = 'BUY' if signal['type'] == 'BUY_SIGNAL' else 'SELL'
                        
                        if whale_side == signal_side:
                            print(f"--- 5TH KEY: Sync with Dominant Whale {whale_id} detected! Boosting confidence. ---")
                            ml_score_pct = min(ml_score_pct + 15, 100.0) # Add 15%, cap at 100
                            signal['whale_id'] = whale_id # Tag signal for logging
                            break # Apply boost only once

            if ml_score_pct < 60:
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

def analyze_mean_reversion(symbol, order_book, price_history, chop_index):
    """
    Mean Reversion strategy for ranging markets.
    """
    if chop_index <= 61.8 or not order_book or symbol != 'MES':
        return None

    if len(price_history) < 20:
        return None

    recent_prices = price_history[-20:]
    rolling_high = max(recent_prices)
    rolling_low = min(recent_prices)
    price_range = rolling_high - rolling_low

    if price_range == 0:
        return None

    current_price = price_history[-1]
    lower_band = rolling_low + (0.1 * price_range)
    upper_band = rolling_high - (0.1 * price_range)

    signal = None
    threshold = 0.5

    if current_price <= lower_band and 'bids' in order_book and order_book['bids']:
        for price, size in order_book['bids']:
            if float(size) > threshold:
                signal = {
                    'type': 'BUY_SIGNAL',
                    'price': price,
                    'size': float(size),
                    'reason': 'Mean Reversion',
                    'confidence_score': 80.0,
                    'timestamp': round(time.time(), 4)
                }
                break

    if not signal and current_price >= upper_band and 'asks' in order_book and order_book['asks']:
        for price, size in order_book['asks']:
            if float(size) > threshold:
                signal = {
                    'type': 'SELL_SIGNAL',
                    'price': price,
                    'size': float(size),
                    'reason': 'Mean Reversion',
                    'confidence_score': 80.0,
                    'timestamp': round(time.time(), 4)
                }
                break

    return signal

def analyze_breakout(symbol, order_book, price_history, chop_index):
    """
    Breakout strategy for birthing trends.
    """
    if chop_index >= 38.2 or symbol != 'MES':
        return None

    if len(price_history) < 21:
        return None

    # Use previous 20 periods so current price can actually "break out" of the historical range
    recent_prices = price_history[-21:-1]
    rolling_high = max(recent_prices)
    rolling_low = min(recent_prices)

    atr = get_current_atr(price_history, period=14)
    if atr == 0.0:
        return None

    current_price = price_history[-1]
    signal = None

    if current_price > rolling_high + (0.5 * atr):
        signal = {
            'type': 'BUY_SIGNAL',
            'price': current_price,
            'size': 1.0,
            'reason': 'Breakout',
            'confidence_score': 80.0,
            'timestamp': round(time.time(), 4)
        }
    elif current_price < rolling_low - (0.5 * atr):
        signal = {
            'type': 'SELL_SIGNAL',
            'price': current_price,
            'size': 1.0,
            'reason': 'Breakout',
            'confidence_score': 80.0,
            'timestamp': round(time.time(), 4)
        }

    return signal