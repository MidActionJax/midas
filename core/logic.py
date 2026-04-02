import time
import statistics
from collections import deque, namedtuple
from datetime import datetime, time as datetime_time
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
MODEL_PATH_LONG = os.path.join(BASE_DIR, 'models', 'midas_brain.pkl')
MODEL_PATH_SHORT = os.path.join(BASE_DIR, 'models', 'midas_brain_short.pkl')
MODEL_PATH_PINGPONG = os.path.join(BASE_DIR, 'models', 'midas_brain_pingpong.pkl')
TRUTH_ENGINE_LONG = None
TRUTH_ENGINE_SHORT = None
TRUTH_ENGINE_PINGPONG = None
MIN_CONFIDENCE_THRESHOLD = 85.0

class DualCoreMemory:
    def __init__(self):
        self.bid_vol_hist = deque(maxlen=6)
        self.ask_vol_hist = deque(maxlen=6)
        self.imbalance_hist = deque(maxlen=30)

dc_memory = DualCoreMemory()

if os.path.exists(MODEL_PATH_LONG):
    try:
        TRUTH_ENGINE_LONG = joblib.load(MODEL_PATH_LONG)
        print(f"INFO: Dual-Core Engine: LONG Brain loaded successfully from {MODEL_PATH_LONG}")
    except Exception as e:
        print(f"ERROR: Could not load LONG Brain: {e}")
else:
    print(f"WARNING: No LONG model file found at {MODEL_PATH_LONG}. Check your folder structure.")

if os.path.exists(MODEL_PATH_SHORT):
    try:
        TRUTH_ENGINE_SHORT = joblib.load(MODEL_PATH_SHORT)
        print(f"INFO: Dual-Core Engine: SHORT Brain loaded successfully from {MODEL_PATH_SHORT}")
    except Exception as e:
        print(f"ERROR: Could not load SHORT Brain: {e}")
else:
    print(f"WARNING: No SHORT model file found at {MODEL_PATH_SHORT}. Check your folder structure.")

if os.path.exists(MODEL_PATH_PINGPONG):
    try:
        TRUTH_ENGINE_PINGPONG = joblib.load(MODEL_PATH_PINGPONG)
        print(f"INFO: Ping-Pong Brain loaded successfully from {MODEL_PATH_PINGPONG}")
    except Exception as e:
        print(f"ERROR: Could not load Ping-Pong Brain: {e}")
else:
    print(f"WARNING: No Ping-Pong model file found at {MODEL_PATH_PINGPONG}. Check your folder structure.")

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
        from datetime import datetime, timezone, timedelta, time as datetime_time
        from zoneinfo import ZoneInfo
        
        if state_manager.current_market_time:
            # Assume naive Arizona time (MST) and shift to EST
            now_est = (state_manager.current_market_time + timedelta(hours=3)).time()
        else:
            # Fallback to current UTC and convert to EST
            utc_now = datetime.now(timezone.utc)
            est_now = utc_now.astimezone(ZoneInfo('US/Eastern'))
            now_est = est_now.time()

        open_end = datetime_time(10, 30)
        trend_est_end = datetime_time(12, 0)
        lunch_chop_end = datetime_time(14, 0)
        reset_end = datetime_time(15, 0)
        power_hour_end = datetime_time(16, 0)
        halt_end = datetime_time(18, 0)
        asian_end = datetime_time(6, 0)

        if now_est >= power_hour_end and now_est < halt_end:
            return "Market Halt"
        elif now_est >= halt_end or now_est < asian_end:
            return "Overnight"
        elif now_est < datetime_time(9, 30):
            return "Pre-Market"
        elif now_est < open_end:
            return "The Open"
        elif now_est < trend_est_end:
            return "Trend Est."
        elif now_est < lunch_chop_end:
            return "Lunch Chop"
        elif now_est < reset_end:
            return "The Reset"
        elif now_est < power_hour_end:
            return "Power Hour"
        else:
            return "Unknown"
    except Exception as e:
        print(f"Error getting market session: {e}")
        return "Unknown"

def get_dynamic_thresholds():
    """
    Dynamic Session Profiler: Returns the minimum ML confidence required 
    based on the time of day to ensure 'High-Probability Sniper' trading.
    Maps PST timeblocks to EST.
    """
    try:
        from datetime import datetime, timezone, timedelta, time as datetime_time
        est = ZoneInfo('US/Eastern')
        
        if state_manager.current_market_time:
            # Assume naive Arizona time (MST) and shift to EST
            now_est = (state_manager.current_market_time + timedelta(hours=3)).time()
        else:
            utc_now = datetime.now(timezone.utc)
            now_est = datetime.now(est).time()

        open_end = datetime_time(10, 30)
        trend_est_end = datetime_time(12, 0)
        lunch_chop_end = datetime_time(14, 0)
        reset_end = datetime_time(15, 0)
        power_hour_end = datetime_time(16, 0)
        
        # MARKET HALT: 16:00 to 18:00 EST (1:00 PM - 3:00 PM MST)
        halt_end = datetime_time(18, 0)
        # ASIAN SESSION: 18:00 to 06:00 EST (3:00 PM - 4:00 AM MST)
        asian_end = datetime_time(6, 0)

        if now_est >= power_hour_end and now_est < halt_end:
            return {'min_confidence': 100.0, 'halt': True, 'min_atr': 2.0, 'strategy': 'NONE'}
        elif now_est >= halt_end or now_est < asian_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 0.20, 'strategy': 'MEAN_REVERSION'}

        if now_est < datetime_time(9, 30):
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'}
        elif now_est < open_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'} #change back to 95
        elif now_est < trend_est_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'}
        elif now_est < lunch_chop_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'} #change back to 95
        elif now_est < reset_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'}
        elif now_est < power_hour_end:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 1.50, 'strategy': 'ALL'}
        else:
            return {'min_confidence': 85.0, 'halt': False, 'min_atr': 2.0, 'strategy': 'ALL'}  # After hours
    except Exception as e:
        return {'min_confidence': 75.0, 'halt': False, 'min_atr': 2.0, 'strategy': 'ALL'}

def is_volatility_safe(current_atr, session_min_atr=2.0):
    """
    Checks if the market volatility is within a safe range.
    """
    if current_atr >= session_min_atr:
        return True
    return False

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


def get_current_atr(price_history, period=120):
    """
    Calculates a Micro-ATR by slicing the history into 30-second mini-bars,
    finding the range of each block, and averaging them. 
    This accurately filters out dead chop while catching real momentum.
    """
    if len(price_history) < period:
        return 0.0  # Not enough data

    recent_prices = price_history[-period:]
    block_size = 30
    ranges = []

    # Slice the data into 30-second chunks
    for i in range(0, len(recent_prices), block_size):
        block = recent_prices[i:i+block_size]
        if len(block) == block_size:
            block_range = max(block) - min(block)
            ranges.append(block_range)

    if not ranges:
        return 0.0

    # Return the Average True Range of those 30-second blocks
    return sum(ranges) / len(ranges)

def get_dynamic_wall_threshold(order_book, multiplier=4.0, absolute_min=25.0):
    """
    Calculates what a 'Massive Wall' is right now based on current DOM averages.
    It requires a wall to be 'multiplier' times larger than the average resting order,
    with a hard floor of 'absolute_min' to ignore pure noise.
    """
    if not order_book: 
        return absolute_min
        
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])
    all_vols = [float(size) for _, size in bids] + [float(size) for _, size in asks]
    
    if not all_vols: 
        return absolute_min
    
    # Only average the top 20 levels of the book to get the immediate liquidity zone
    top_vols = sorted(all_vols, reverse=True)[:20]
    avg_vol = sum(top_vols) / len(top_vols)
    
    return max(absolute_min, avg_vol * multiplier)

def get_macro_box(order_book, current_price):
    """
    Globally tracks the massive Iceberg walls (Floor and Ceiling) on the DOM.
    Any brain (Momentum or Ping-Pong) can call this to see the battlefield.
    """
    if not order_book:
        return current_price, 0.0, current_price, 0.0

    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])

    best_bid = bids[0][0] if bids else current_price
    best_ask = asks[0][0] if asks else current_price

    # Scan the DOM and find the single heaviest volume wall on both sides
    macro_floor_price = max(bids, key=lambda x: float(x[1]))[0] if bids else best_bid
    macro_floor_vol = float(max(bids, key=lambda x: float(x[1]))[1]) if bids else 0.0
    
    macro_ceiling_price = max(asks, key=lambda x: float(x[1]))[0] if asks else best_ask
    macro_ceiling_vol = float(max(asks, key=lambda x: float(x[1]))[1]) if asks else 0.0
    print(f"[🧊 ICEBERG RADAR] Floor: {macro_floor_price} ({macro_floor_vol} contracts) | Ceiling: {macro_ceiling_price} ({macro_ceiling_vol} contracts)")

    return macro_floor_price, macro_floor_vol, macro_ceiling_price, macro_ceiling_vol


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
    
    # Prevent premature NaN evaluation by injecting a safe divisor
    safe_denominator = np.where(denominator == 0, 1e-10, denominator)
    chop = np.where(denominator == 0, 50.0, 100 * np.log10(numerator / safe_denominator) / np.log10(period))
    
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
                signal = {'symbol': symbol, 'type': 'BUY_SIGNAL', 'price': price, 'size': float(size), 'reason': 'Iceberg Detected', 'timestamp': round(time.time(), 4)}
                break
    if not signal and 'asks' in order_book and order_book['asks']:
        for price, size in order_book['asks']:
            if float(size) > threshold:
                signal = {'symbol': symbol, 'type': 'SELL_SIGNAL', 'price': price, 'size': float(size), 'reason': 'Iceberg Detected', 'timestamp': round(time.time(), 4)}
                break
    
    if symbol != 'MES':
        return None

    # --- DEV MODE OVERRIDE ---
    if state_manager.dev_mode:
        if signal:
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
    
    market_trend = trend_mes
    
    # --- THE 4TH KEY: Volatility Gate ---
    atr_mes = get_current_atr(price_history_mes)
    thresholds = get_dynamic_thresholds()
    min_atr = thresholds.get('min_atr', 2.0) if isinstance(thresholds, dict) else 2.0
    
    ml_score_pct = 0.0
    trend_alignment = 0.0
    active_brain = "NONE"

    # --- THE TRUTH ENGINE: Dual-Core ML Veto (MIDAS BRAIN UPGRADE) ---
    if TRUTH_ENGINE_LONG or TRUTH_ENGINE_SHORT:
        # 1. EXTRACT THE RAW ORDER BOOK DATA
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        # If the book is empty, we default to 0 to prevent crashes
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        
        # --- PHASE 2, STEP 2: THE MACRO MAPPER ---
        # Scan the DOM and find the single heaviest volume wall on both sides
        macro_floor_price = max(bids, key=lambda x: float(x[1]))[0] if bids else best_bid
        macro_floor_vol = float(max(bids, key=lambda x: float(x[1]))[1]) if bids else 0.0
        
        macro_ceiling_price = max(asks, key=lambda x: float(x[1]))[0] if asks else best_ask
        macro_ceiling_vol = float(max(asks, key=lambda x: float(x[1]))[1]) if asks else 0.0
        dynamic_wall = get_dynamic_wall_threshold(order_book)
        bid_vol = sum(size for price, size in bids)
        ask_vol = sum(size for price, size in asks)
        
        # Dual-Core Memory Tracking
        imbalance = bid_vol - ask_vol
        dc_memory.bid_vol_hist.append(bid_vol)
        dc_memory.ask_vol_hist.append(ask_vol)
        dc_memory.imbalance_hist.append(imbalance)

        mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else current_price_mes
        
        est = ZoneInfo('US/Eastern')
        if state_manager.current_market_time:
            current_hour = state_manager.current_market_time.hour
        else:
            current_hour = datetime.now(est).hour

        # 2. CALCULATE THE ON-THE-FLY MEMORY MATRIX
        # Ensure we have at least 60 seconds of history, otherwise default to 0
        sma_30 = sum(price_history_mes[-30:]) / 30 if len(price_history_mes) >= 30 else current_price_mes
        sma_60 = sum(price_history_mes[-60:]) / 60 if len(price_history_mes) >= 60 else current_price_mes
        trend_alignment = sma_30 - sma_60
        volatility_60s = statistics.stdev(price_history_mes[-60:]) if len(price_history_mes) >= 60 else 0.0
        
        # Short Specific Features
        bid_drop_velocity = bid_vol - dc_memory.bid_vol_hist[0] if len(dc_memory.bid_vol_hist) == 6 else 0.0
        ask_surge_velocity = ask_vol - dc_memory.ask_vol_hist[0] if len(dc_memory.ask_vol_hist) == 6 else 0.0
        imbalance_skew_30s = sum(dc_memory.imbalance_hist) / len(dc_memory.imbalance_hist) if len(dc_memory.imbalance_hist) > 0 else 0.0
        price_momentum_10s = price_history_mes[-1] - price_history_mes[-11] if len(price_history_mes) >= 11 else 0.0
        distance_from_sma60 = mid_price - sma_60

        # 3. THE SPLIT-BRAIN ROUTER
        if trend_alignment > 0 and TRUTH_ENGINE_LONG:
            active_brain = "LONG"
            features = pd.DataFrame([{
                'Bid_Vol': bid_vol,
                'Best_Bid': best_bid,
                'Ask_Vol': ask_vol,
                'Best_Ask': best_ask,
                'Mid_Price': mid_price,
                'Hour': current_hour,
                'Trend_Alignment': trend_alignment,
                'Volatility_60s': volatility_60s,
                'Session_CVD': state_manager.session_cvd
            }])
            probs = TRUTH_ENGINE_LONG.predict_proba(features)[0]
            success_prob = probs[1]
            ml_score_pct = success_prob * 100

        elif trend_alignment <= 0 and TRUTH_ENGINE_SHORT:
            active_brain = "SHORT"
            features = pd.DataFrame([{
                'Bid_Vol': bid_vol,
                'Ask_Vol': ask_vol,
                'Imbalance_Skew_30s': imbalance_skew_30s,
                'Bid_Drop_Velocity': bid_drop_velocity,
                'Ask_Surge_Velocity': ask_surge_velocity,
                'Price_Momentum_10s': price_momentum_10s,
                'Distance_from_SMA60': distance_from_sma60,
                'Volatility_60s': volatility_60s,
                'Session_CVD': state_manager.session_cvd
            }])
            probs = TRUTH_ENGINE_SHORT.predict_proba(features)[0]
            success_prob = probs[1]
            ml_score_pct = success_prob * 100

        if active_brain != "NONE":
            ema_mes_5 = calculate_ema(price_history_mes, period=5)
            ema_mnq_5 = calculate_ema(price_history_mnq, period=5)
            
            in_sync = False
            if ema_mes_5 and ema_mnq_5:
                 in_sync = (current_price_mes > ema_mes_5) == (price_history_mnq[-1] > ema_mnq_5)
                 
            if in_sync:
                ml_score_pct += 25.0 # Boost base confidence if markets align

            # --- THE 5TH KEY: Institutional Sync ---
            dominant_whales = state_manager.get_active_dominant_whales()
            if dominant_whales:
                all_whales = state_manager.get_detected_whales()
                for whale_id in dominant_whales:
                    # Find the most recent pattern for this whale_id
                    whale_pattern = next((w for w in reversed(all_whales) if w.get('whale_id') == whale_id), None)
                    if whale_pattern:
                        whale_side = whale_pattern.get('side')
                        signal_side = 'BUY' if not signal or signal['type'] == 'BUY_SIGNAL' else 'SELL'
                        
                        if whale_side == signal_side:
                            print(f"--- 5TH KEY: Sync with Dominant Whale {whale_id} detected! Boosting confidence. ---")
                            ml_score_pct += 30.0 # Increased weight for institutional footprint
                            if signal is not None:
                                signal['whale_id'] = whale_id # Tag signal for logging
                            break # Apply boost only once

            ml_score_pct = min(ml_score_pct, 100.0)

            # --- AI SNIPER TRIGGER ---
            # Set asymmetric thresholds: Escalator Up (85%), Elevator Down (84%)
            target_threshold = 85.0 if active_brain == 'LONG' else 84.0
            
            # If the AI is confident, it creates its own signal even if no iceberg exists!
            if ml_score_pct >= target_threshold:
                
                # --- PHASE 2, STEP 3: THE MACRO VETO ---
                distance_to_floor = current_price_mes - macro_floor_price
                distance_to_ceiling = macro_ceiling_price - current_price_mes
                
                # LAYER 1 RULE: Do not shoot into an iceberg wall!
                if active_brain == 'SHORT' and distance_to_floor <= 1.5 and macro_floor_vol >= dynamic_wall:
                    print(f"[🛑 MACRO VETO] SHORT Blocked! Price ({current_price_mes}) is aiming at a {macro_floor_vol}-contract FLOOR wall at {macro_floor_price} (Threshold: {dynamic_wall:.1f}).")
                    # Signal remains None, forcing a HOLD
                elif active_brain == 'LONG' and distance_to_ceiling <= 1.5 and macro_ceiling_vol >= dynamic_wall:
                    print(f"[🛑 MACRO VETO] LONG Blocked! Price ({current_price_mes}) is aiming at a {macro_ceiling_vol}-contract CEILING wall at {macro_ceiling_price} (Threshold: {dynamic_wall:.1f}).")
                    # Signal remains None, forcing a HOLD
                else:
                    # Path is clear! Build the signal.
                    signal_type = 'BUY_SIGNAL' if active_brain == 'LONG' else 'SELL_SIGNAL'
                    signal = {
                        'symbol': symbol,
                        'type': signal_type,
                        'price': best_ask if signal_type == 'BUY_SIGNAL' else best_bid,
                        'size': 1.0,
                        'timestamp': round(time.time(), 4)
                    }
                
                # --- SURGICAL UPDATE: Add Direction & Alert for AI Sniper ---
                signal['reason'] = f'Dual-Core Sniper ({active_brain})'
                if active_brain == "LONG":
                    signal['signal_direction'] = "BUY"
                    print(f"[🚨 LONG SIGNAL FIRED] Dual-Core Sniper triggered by {active_brain} Brain.")
                else: # SHORT
                    signal['signal_direction'] = "SHORT"
                    print(f"[🚨 SHORT SIGNAL FIRED] Dual-Core Sniper triggered by {active_brain} Brain.")
                signal['trend_pass'] = True
                signal['volatility_pass'] = True
                # 🛑 SURGICAL FIX: Spoof the ATR so engine.py can't veto it
                signal['atr'] = 99.0

            if signal:
                signal['ml_confidence'] = f"{ml_score_pct:.2f}%"
                # 🛡️ IMMUNITY: If the Sniper fired, pass the raw score.
                signal['ml_confidence_value'] = ml_score_pct

    print(f"[X-RAY - {active_brain} BRAIN] ATR: {atr_mes:.2f} | ML Confidence: {ml_score_pct:.2f}% | Trend: {trend_alignment:.2f}")

    # If neither the Iceberg nor the AI found a reason to trade, quit.
    if not signal:
        return None

    if 'trend' not in signal:
        signal['trend'] = trend_mes
        
    if 'trend_pass' not in signal:
        signal_direction = 'BUY' if 'BUY' in signal.get('type', '').upper() else 'SELL'
        if signal_direction == 'BUY' and market_trend == 'BULLISH':
            signal['trend_pass'] = True
        elif signal_direction == 'SELL' and market_trend == 'BEARISH':
            signal['trend_pass'] = True
        else:
            signal['trend_pass'] = False
            
    if 'atr' not in signal:
        signal['atr'] = atr_mes
        
    if 'volatility_pass' not in signal:
        signal['volatility_pass'] = is_volatility_safe(atr_mes, min_atr)

    session_str = get_market_session()
    raw_whale_strength = calculate_whale_strength(signal['size'], order_book)
    
    # Use the AI's higher-quality math for the dashboard/logs
    signal['context_data'] = {
        'ema_val': sma_60 if 'sma_60' in locals() else ema_mes,
        'trend': trend_mes,
        'atr': volatility_60s if 'volatility_60s' in locals() else atr_mes,
        'session': session_str,
        'whale_strength': raw_whale_strength
    }
    
    return signal

def analyze_mean_reversion(symbol, order_book, price_history, chop_index):
    """
    The Ping-Pong Agent:
    Buys the Floor and Sells the Ceiling when the market is trapped in chop.
    """
    # Chop Index must be high (sideways market) to play ping-pong
    if chop_index <= 50.0 or not order_book or symbol != 'MES':
        return None

    if len(price_history) < 60:
        return None

    current_price = price_history[-1]
    sma_60 = sum(price_history[-60:]) / 60
    
    # 1. Use the Global Tracker to find the walls
    floor_price, floor_vol, ceiling_price, ceiling_vol = get_macro_box(order_book, current_price)

    dynamic_wall = get_dynamic_wall_threshold(order_book)

    # 2. Calculate distance to the walls
    dist_to_floor = current_price - floor_price
    dist_to_ceiling = ceiling_price - current_price

    ml_confidence = 80.0
    if TRUTH_ENGINE_PINGPONG:
        try:
            features = pd.DataFrame([{
                'Distance_from_SMA60': abs(current_price - sma_60),
                'Floor_Vol': floor_vol,
                'Ceiling_Vol': ceiling_vol,
                'ATR': get_current_atr(price_history),
                'Chop_Index': chop_index
            }])
            probs = TRUTH_ENGINE_PINGPONG.predict_proba(features)[0]
            ml_confidence = probs[1] * 100.0
        except Exception as e:
            print(f"Error calculating Ping-Pong AI confidence: {e}")

    signal = None
    print(f"[X-RAY - PING-PONG] ATR: {get_current_atr(price_history):.2f} | ML Confidence: {ml_confidence:.2f}% | Chop: {chop_index:.2f}")
    
    # PING-PONG RULE 1: If resting on a strong floor, bounce up to the middle (SMA 60)
    if dist_to_floor <= 1.0 and floor_vol >= dynamic_wall and current_price < sma_60:
        print(f"[🏓 PING-PONG] Floor bounce detected at {floor_price}. Aiming for SMA 60 ({sma_60:.2f})")
        signal = {
            'symbol': symbol,
            'type': 'BUY_SIGNAL',
            'price': current_price,
            'size': 1.0,
            'reason': 'Ping-Pong (Floor Bounce)',
            'confidence_score': ml_confidence,
            'ml_confidence_value': ml_confidence,
            'timestamp': round(time.time(), 4),
            'trend_pass': True,        # Bypasses trend filter (chop is sideways)
            'volatility_pass': True,   # Bypasses volatility filter
            'atr': 99.0                # Spoofs ATR so engine doesn't block it
        }
        
    # PING-PONG RULE 2: If hitting a strong ceiling, reject down to the middle (SMA 60)
    elif dist_to_ceiling <= 1.0 and ceiling_vol >= dynamic_wall and current_price > sma_60:
        print(f"[🏓 PING-PONG] Ceiling rejection detected at {ceiling_price}. Aiming for SMA 60 ({sma_60:.2f})")
        signal = {
            'symbol': symbol,
            'type': 'SELL_SIGNAL',
            'signal_direction': 'SHORT',
            'price': current_price,
            'size': 1.0,
            'reason': 'Ping-Pong (Ceiling Reject)',
            'confidence_score': ml_confidence,
            'ml_confidence_value': ml_confidence,
            'timestamp': round(time.time(), 4),
            'trend_pass': True,
            'volatility_pass': True,
            'atr': 99.0
        }
        
    if signal:
        # Add rich context so your CSV logs it perfectly for future ML training
        if ml_confidence >= 80.0:
            signal['ml_confidence_value'] = 100.0  # Spoof the engine so it doesn't Veto
        signal['context_data'] = {
            'ema_val': sma_60,
            'trend': 'SIDEWAYS',
            'atr': get_current_atr(price_history),
            'session': 'Chop Regime',
            'whale_strength': floor_vol if 'BUY' in signal['type'] else ceiling_vol
        }
        
    return signal

def analyze_breakout(symbol, order_book, price_history, chop_index):
    """
    Breakout strategy for birthing trends (Momentum Surfer).
    """
    if chop_index >= 38.2 or symbol != 'MES':
        return None

    if len(price_history) < 15:
        return None

    ema_5 = calculate_ema(price_history, period=5)
    atr = get_current_atr(price_history, period=120)
    
    if ema_5 is None or atr == 0.0:
        return None

    current_price = price_history[-1]
    signal = None

    if current_price > (ema_5 + (1.0 * atr)):
        signal = {
            'symbol': symbol,
            'type': 'BUY_SIGNAL',
            'price': current_price,
            'size': 1.0,
            'reason': 'Momentum Surfer',
            'confidence_score': 80.0,
            'ml_confidence_value': 85.0,
            'timestamp': round(time.time(), 4)
        }
    elif current_price < (ema_5 - (1.0 * atr)):
        signal = {
            'symbol': symbol,
            'type': 'SELL_SIGNAL',
            'price': current_price,
            'size': 1.0,
            'reason': 'Momentum Surfer',
            'confidence_score': 80.0,
            'ml_confidence_value': 85.0,
            'timestamp': round(time.time(), 4)
        }

    return signal


def analyze_stagnation_exit(symbol, current_price, position_data):
    """
    Implements a 'Time-Decay' exit logic. If a position is in profit but 
    stalls and fails to make a new extremum within a dynamic heartbeat threshold,
    it triggers an exit.
    """
    entry_price = position_data.get('entry_price')
    pos_type = position_data.get('type', '').upper()
    
    if not entry_price or not pos_type:
        return None
        
    is_long = 'BUY' in pos_type or 'LONG' in pos_type
    
    # 1. Check Profitability: Only trigger if in profit by > 1.5 points
    profit_points = (current_price - entry_price) if is_long else (entry_price - current_price)
    if profit_points <= 1.5:
        # Reset counters if we fall out of the profit zone or haven't reached it
        position_data['heartbeats_since_new_extremum'] = 0
        position_data['last_extremum_price'] = current_price
        return None

    # 2. Track Extremums
    best_price = position_data.get('last_extremum_price', entry_price)
    made_new_extremum = False
    
    if is_long and current_price > best_price:
        best_price = current_price
        made_new_extremum = True
    elif not is_long and current_price < best_price:
        best_price = current_price
        made_new_extremum = True
        
    position_data['last_extremum_price'] = best_price
    
    # 3. Update Stagnation Timer
    if made_new_extremum:
        position_data['heartbeats_since_new_extremum'] = 0
    else:
        position_data['heartbeats_since_new_extremum'] = position_data.get('heartbeats_since_new_extremum', 0) + 1

    # 4. Dynamic Threshold based on ATR
    price_history = state_manager.price_history.get(symbol, [])
    atr = get_current_atr(price_history) if price_history else 2.0
    
    # Base threshold is 30 heartbeats. Adjust inversely proportional to ATR.
    safe_atr = max(atr, 0.5) # Prevent division by zero
    dynamic_threshold = int(30 * (2.0 / safe_atr))
    dynamic_threshold = max(10, min(dynamic_threshold, 60)) # Clamp bounds between 10 and 60
    
    if position_data.get('heartbeats_since_new_extremum', 0) >= dynamic_threshold:
        print(f"[⏱️ TIME-DECAY EXIT] {symbol} position stagnated for {dynamic_threshold} heartbeats. Best price was {best_price}.")
        return {
            'symbol': symbol,
            'type': 'EXIT_SIGNAL',
            'price': current_price,
            'size': position_data.get('size', 1.0),
            'reason': 'Stagnation Decay',
            'timestamp': round(time.time(), 4)
        }
        
    return None