import time
import sys
import os
import math
import csv
import numpy as np
import pandas as pd

# Ensure project root is in path so we can import core modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from core.state import state_manager
from core.logic import (
    get_current_atr, update_concrete_state, analyze_stagnation_exit,
    analyze_order_book, get_market_session, calculate_choppiness_index,
    analyze_mean_reversion, update_session_anchors
)
from core.engine import MidasEngine
from adapters.base import TradingAdapter

# ==========================================
# --- MOCK TIME (CPU SPEED EXECUTION) ---
# ==========================================
# We monkeypatch time.time() globally so time-based logic (like Stagnation Decay
# and Concrete wetness timeouts) executes flawlessly at CPU speed without time.sleep.
_mock_time_val = 1600000000.0
def mock_time():
    return _mock_time_val

def advance_time(seconds=1.0):
    global _mock_time_val
    _mock_time_val += seconds

time.time = mock_time


# ==========================================
# --- MOCK ADAPTER ---
# ==========================================
class MockAdapter(TradingAdapter):
    """
    Mimics the real NT socket adapter. It feeds synthetic ticks directly
    into the system instead of connecting to a live socket.
    """
    def __init__(self, ticks):
        self.ticks = ticks
        self.current_tick_idx = 0
        self.wallet_balance = 100000.0
        self.positions = []
        self.prices = {'MES': 0.0, 'MNQ': 0.0}
        
    def get_wallet_balance(self):
        return self.wallet_balance
        
    def get_current_price(self, symbol='MES'):
        return self.prices.get(symbol, 0.0)
        
    def execute_buy(self, symbol, amount, price=None, signal_id=None):
        self.positions.append({'symbol': symbol, 'amount': amount, 'side': 'BUY', 'price': price})
        return True
        
    def execute_sell(self, symbol, amount, price=None, signal_id=None, side='SELL'):
        self.positions.append({'symbol': symbol, 'amount': amount, 'side': side, 'price': price})
        return True
        
    def get_market_depth(self, symbol):
        price = self.get_current_price(symbol)
        # Simple synthetic Level 2 depth
        return {'bids': [[price - 0.25, 10]], 'asks': [[price + 0.25, 10]]}
        
    def get_open_positions(self):
        return state_manager.get_active_positions()
        
    def step(self):
        self.current_tick_idx += 1


# ==========================================
# --- SYNTHETIC DATA GENERATORS ---
# ==========================================
def generate_chop_data():
    """Scenario 1: 500 ticks oscillating in a tight 3-point range."""
    ticks = []
    base_price = 5000.0
    for i in range(500):
        price = base_price + (i % 3) - 1.0  # Swings between 4999.0 and 5001.0
        ticks.append({'price': price, 'volume': 10, 'timestamp': i})
    return ticks

def generate_elevator_flush():
    """Scenario 2: 200 ticks simulating a sudden 40-point drop with high volume."""
    ticks = []
    price = 5000.0
    for i in range(200):
        price -= 0.2  # Drops continuously (40 points total)
        ticks.append({'price': price, 'volume': 150, 'timestamp': i})
    return ticks

def generate_stagnation():
    """Scenario 3: 50 ticks moving into profit, then 300 flat ticks to trigger decay."""
    ticks = []
    price = 5000.0
    # Move 5 points into profit
    for i in range(50):
        price += 0.1
        ticks.append({'price': price, 'volume': 20, 'timestamp': i})
    # Go completely flat
    for i in range(300):
        ticks.append({'price': price, 'volume': 2, 'timestamp': 50 + i})
    return ticks

def generate_whipsaw():
    """Scenario 4: Extremely volatile market expanding ATR rapidly."""
    ticks = []
    for i in range(100):
        price = 5000.0 + (10 if i % 2 == 0 else -10) # +/- 10 point swings
        ticks.append({'price': price, 'volume': 50, 'timestamp': i})
    return ticks

def generate_steady_trend_up():
    """Scenario 5: Smoothly trending market upwards."""
    ticks = []
    price = 5000.0
    for i in range(300):
        price += 0.1
        ticks.append({'price': price, 'volume': 10, 'timestamp': i})
    return ticks

def generate_monte_carlo_days(num_days=100):
    """Generates chaotic synthetic ticks using Brownian motion and random Poisson jumps."""
    days = []
    for day in range(num_days):
        ticks = []
        base_price = np.random.uniform(4000.0, 15000.0) # Random starting price
        volatility = np.random.uniform(0.1, 3.0) # Randomly high or low volatility
        drift = np.random.uniform(-0.2, 0.2) # Randomly Bullish, Bearish, or Flat
        
        ticks_per_day = np.random.randint(1000, 5000)
        steps = np.random.normal(loc=drift, scale=volatility, size=ticks_per_day)
        
        # Poisson jumps (Simulating News Events or Liquidity Vacuums)
        num_jumps = np.random.poisson(lam=3) 
        jump_indices = np.random.randint(0, ticks_per_day, size=num_jumps)
        jump_sizes = np.random.normal(loc=0, scale=volatility * 20, size=num_jumps)
        for idx, size in zip(jump_indices, jump_sizes):
            steps[idx] += size
            
        prices = base_price + np.cumsum(steps)
        for i, p in enumerate(prices):
            ticks.append({'price': float(p), 'volume': int(np.random.exponential(50)), 'timestamp': i})
        days.append(ticks)
    return days

def load_tick_data(filepath, symbol):
    """Reads NinjaTrader txt exports (semicolon delimited, no header)."""
    print(f"Loading {symbol} ticks from {filepath}...")
    ticks = []
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return ticks
        
    try:
        # SURGICAL EDIT 1: Tell pandas to look for semicolons and explicitly name the missing headers
        df = pd.read_csv(filepath, sep=';', header=None, 
                         names=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ticks
        
    # SURGICAL EDIT 2: Teach pandas how to read NinjaTrader's weird date format (yyyyMMdd HHmmss)
    df['parsed_time'] = pd.to_datetime(df['timestamp'], format='%Y%m%d %H%M%S', errors='coerce')
    
    # SURGICAL EDIT 3: Use the 'close' column instead of guessing the price column
    df = df.dropna(subset=['parsed_time', 'close'])
    
    for _, row in df.iterrows():
        ticks.append({
            'timestamp_dt': row['parsed_time'],
            'timestamp': row['parsed_time'].timestamp(),
            'price': float(row['close']),  # Feed the Close price to the engine
            'volume': float(row['volume']),
            'symbol': symbol
        })
    return ticks

def print_scorecard():
    csv_path = 'trade_history.csv'
    if not os.path.exists(csv_path):
        print("\n[SCORECARD] No trade_history.csv found. Did the bot take any trades?")
        return
        
    df = pd.read_csv(csv_path, on_bad_lines='skip')
    
    if 'final_pnl' not in df.columns:
        print("\n[SCORECARD] No completed trades found in log.")
        return
        
    df['final_pnl'] = pd.to_numeric(df['final_pnl'], errors='coerce')
    closed_trades = df.dropna(subset=['final_pnl'])
    
    if closed_trades.empty:
        print("\n[SCORECARD] No closed trades found.")
        return
        
    total_trades = len(closed_trades)
    wins = closed_trades[closed_trades['final_pnl'] > 0]
    losses = closed_trades[closed_trades['final_pnl'] <= 0]
    
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0.0
    gross_profit = wins['final_pnl'].sum() if not wins.empty else 0.0
    gross_loss = losses['final_pnl'].sum() if not losses.empty else 0.0
    net_pnl = gross_profit + gross_loss
    
    closed_trades = closed_trades.sort_values(by='timestamp_id')
    cumulative_pnl = closed_trades['final_pnl'].cumsum()
    peak = cumulative_pnl.cummax()
    drawdowns = peak - cumulative_pnl
    max_drawdown = drawdowns.max() if not drawdowns.empty else 0.0
    
    print("\n========================================")
    print("📈 MIDAS BACKTEST SCORECARD")
    print("========================================")
    print(f"Total Trades Executed : {total_trades}")
    print(f"Win Rate              : {win_rate:.2f}%")
    print(f"Gross Profit          : ${gross_profit:.2f}")
    print(f"Gross Loss            : ${gross_loss:.2f}")
    print(f"Net Realized PnL      : ${net_pnl:.2f}")
    print(f"Max Drawdown          : ${max_drawdown:.2f}")
    print("========================================\n")

# ==========================================
# --- TEST RUNNER ENGINE ---
# ==========================================
def run_uat_scenario(name, ticks, test_fn):
    print(f"\n--- [SCENARIO] {name} ---")
    
    # 1. Reset Global State
    state_manager.reset_for_new_day()
    state_manager.price_history = {'MES': [], 'MNQ': []}
    state_manager.price_bars = {'MES': [], 'MNQ': []}
    state_manager.is_concrete_wet = False
    state_manager.last_dry_price = None
    state_manager.fence_shattered = False
    state_manager.stagnation_start_time = None
    state_manager.stagnation_min_price = None
    state_manager.stagnation_max_price = None
    state_manager.clear_active_positions()
    
    # Pre-set daily anchors so 'shatter_macro' and limits can trigger correctly
    state_manager.opening_range_high = 5000.0
    state_manager.opening_range_low = 5000.0
    state_manager.highest_price_seen = 5000.0
    state_manager.lowest_price_seen = 5000.0
    
    # Reset mock time
    global _mock_time_val
    _mock_time_val = 1600000000.0 
    
    # 2. Init Adapter
    adapter = MockAdapter(ticks)
    
    # 3. Execute & Assert
    try:
        test_fn(adapter, ticks)
        print(f"✅ PASS: {name}")
    except AssertionError as e:
        print(f"❌ FAIL: {name} - {e}")
    except Exception as e:
        print(f"⚠️ ERROR: {name} - {e}")
        
def run_monte_carlo_chaos_engine(num_days=100):
    """Feeds 100 random days consecutively to stress-test state memory & limits."""
    print(f"\n--- [SCENARIO] Monte Carlo Chaos Engine ({num_days} Days) ---")
    days_data = generate_monte_carlo_days(num_days)
    
    for day_idx, ticks in enumerate(days_data):
        # 1. Reset Global State
        state_manager.reset_for_new_day()
        state_manager.price_history = {'MES': [], 'MNQ': []}
        state_manager.price_bars = {'MES': [], 'MNQ': []}
        state_manager.is_concrete_wet = False
        state_manager.last_dry_price = None
        state_manager.fence_shattered = False
        state_manager.stagnation_start_time = None
        state_manager.stagnation_min_price = None
        state_manager.stagnation_max_price = None
        state_manager.clear_active_positions()
        
        # Pre-set daily anchors
        start_price = ticks[0]['price']
        state_manager.opening_range_high = start_price
        state_manager.opening_range_low = start_price
        state_manager.highest_price_seen = start_price
        state_manager.lowest_price_seen = start_price
        
        # Reset mock time (Advance 1 day forward per loop)
        global _mock_time_val
        _mock_time_val = 1600000000.0 + (day_idx * 86400)
        
        adapter = MockAdapter(ticks)
        
        try:
            core_tick_loop(adapter, ticks)
        except Exception as e:
            print(f"⚠️ CRASH on Chaos Day {day_idx+1}: {e}")
            return
            
    print(f"✅ PASS: Monte Carlo Chaos Engine survived {num_days} days of extreme synthetic data without crashing!")

def run_historical_batch(mes_csv_path, mnq_csv_path):
    """Streams standard NinjaTrader tick data into the engine and prints a scorecard."""
    print(f"\n--- [SCENARIO] Historical Batch Processor: {mes_csv_path} and {mnq_csv_path} ---")
    
    mes_ticks = load_tick_data(mes_csv_path, 'MES')
    mnq_ticks = load_tick_data(mnq_csv_path, 'MNQ')
    ticks = mes_ticks + mnq_ticks
                
    if not ticks:
        print("⚠️ ERROR: No valid ticks extracted from CSVs.")
        return
        
    print("Sorting merged ticks chronologically...")
    ticks.sort(key=lambda x: x['timestamp'])
        
    # Reset Global State
    state_manager.reset_for_new_day()
    state_manager.price_history = {'MES': [], 'MNQ': []}
    state_manager.price_bars = {'MES': [], 'MNQ': []}
    state_manager.clear_active_positions()
    
    adapter = MockAdapter(ticks)
    engine = MidasEngine(['MES', 'MNQ'])
    engine.adapter = adapter
    
    global _mock_time_val
    _mock_time_val = ticks[0]['timestamp']
    
    last_bar_time = {'MES': _mock_time_val, 'MNQ': _mock_time_val}
    price_buffer = {'MES': [], 'MNQ': []}
    
    # Stream rows into the ingestion layer at max CPU speed
    for tick in ticks:
        advance_time(1.0)
        price = tick['price']
        sym = tick.get('symbol', 'MES')
        ts = tick['timestamp']
        
        _mock_time_val = ts
        state_manager.current_market_time = tick.get('timestamp_dt')
        
        last_price = state_manager.price_history[sym][-1] if state_manager.price_history.get(sym) else None
        if last_price is not None:
            state_manager.update_cvd(price, last_price, tick['volume'])
            
        adapter.prices[sym] = price
        state_manager.add_price(sym, price)
        price_buffer[sym].append(price)
        
        if sym == 'MES':
            current_session = get_market_session()
            update_session_anchors(price, current_session)
            
        engine.manage_positions()
        
        # Build 1-minute synthetic bars
        if ts - last_bar_time[sym] >= 60:
            if price_buffer[sym]:
                bar = {
                    'open': price_buffer[sym][0],
                    'high': max(price_buffer[sym]),
                    'low': min(price_buffer[sym]),
                    'close': price_buffer[sym][-1]
                }
                state_manager.price_bars[sym].append(bar)
                state_manager.price_bars[sym] = state_manager.price_bars[sym][-200:]
                
                if len(state_manager.price_bars[sym]) >= 14:
                    df = pd.DataFrame(state_manager.price_bars[sym])
                    state_manager.current_chop_index = calculate_choppiness_index(df)
                    
                price_buffer[sym] = []
                last_bar_time[sym] = ts

        if sym == 'MES' and len(state_manager.price_history['MES']) > 60:
            chop_index = getattr(state_manager, 'current_chop_index', 50.0)
            market_depth = adapter.get_market_depth('MES')
            
            signal = None
            if chop_index > 50.0:
                signal = analyze_mean_reversion('MES', market_depth, state_manager.price_history['MES'], chop_index)
            else:
                signal = analyze_order_book('MES', market_depth, state_manager.price_history, adapter)
                
            if signal:
                exec_price = signal.get('price', price)
                dynamic_size = 1
                
                pos_type = 'BUY' if signal['type'] == 'BUY_SIGNAL' else 'SELL'
                side_to_send = 'SELL' if pos_type == 'SELL' else 'BUY'
                if signal.get('signal_direction') == 'SHORT':
                    side_to_send = 'SHORT'
                    
                active_positions = state_manager.get_active_positions()
                if len(active_positions) == 0:
                    if pos_type == 'BUY':
                        adapter.execute_buy('MES', dynamic_size, exec_price, signal_id=signal.get('id', 'backtest_sig'))
                    else:
                        adapter.execute_sell('MES', dynamic_size, exec_price, signal_id=signal.get('id', 'backtest_sig'), side=side_to_send)
                        
                    pos = {
                        'symbol': 'MES',
                        'entry_price': exec_price,
                        'size': dynamic_size,
                        'type': pos_type,
                        'timestamp': ts,
                        'signal_timestamp': signal.get('timestamp', ts),
                        'signal_id': signal.get('id', 'backtest_sig')
                    }
                    state_manager.add_position(pos)
                    
                    try:
                        with open('trade_history.csv', 'a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=[
                                'timestamp_id', 'symbol', 'type', 'price', 'size',
                                'ema_200_val', 'trend_dir', 'atr_volatility', 'session_context', 'whale_strength',
                                'ml_confidence', 'Whale_ID', 'user_decision', 'final_pnl', 'outcome_label', 'exit_reason',
                                'signal_id'
                            ])
                            if f.tell() == 0:
                                writer.writeheader()
                            writer.writerow({
                                'signal_id': pos.get('signal_id', 'backtest_sig'),
                                'timestamp_id': ts,
                                'symbol': 'MES',
                                'type': signal['type'],
                                'price': exec_price,
                                'size': dynamic_size,
                                'user_decision': 'APPROVED',
                            })
                    except Exception as e:
                        pass
            
        adapter.step()
        
    print_scorecard()
    print("✅ PASS: Historical Batch Completed")


# ==========================================
# --- ASSERTIONS & TEST CASES ---
# ==========================================
def core_tick_loop(adapter, ticks, exit_check_pos=None):
    """Helper function to process a loop of ticks and apply logic.py states at CPU speed."""
    exit_signal = None
    for tick in ticks:
        advance_time(1.0)
        price = tick['price']
        sym = tick.get('symbol', 'MES')
        adapter.prices[sym] = price
        
        state_manager.add_price(sym, price)
        
        # Inject faux 1-minute bars to enable 'shatter_local' checks
        if sym == 'MES' and adapter.current_tick_idx > 0 and adapter.current_tick_idx % 60 == 0:
            state_manager.price_bars['MES'].append({'close': price, 'high': price, 'low': price, 'open': price})

        if sym == 'MES':
            atr = get_current_atr(state_manager.price_history['MES'])
            state_manager.mock_adx = 25.0
            update_concrete_state(price, atr, 'MES')
        
            if exit_check_pos:
                signal = analyze_stagnation_exit('MES', price, exit_check_pos)
                if signal:
                    exit_signal = signal
                
        adapter.step()
    return exit_signal

def test_chop(adapter, ticks):
    core_tick_loop(adapter, ticks)
    assert state_manager.is_concrete_wet == False, f"Concrete should be dry in chop! (Wet={state_manager.is_concrete_wet})"

def test_elevator_flush(adapter, ticks):
    core_tick_loop(adapter, ticks)
    assert state_manager.is_concrete_wet == True, "Concrete should be wet after a massive 40-point drop!"
    assert state_manager.fence_shattered == True, "Fence should be shattered after an elevator flush!"

def test_stagnation(adapter, ticks):
    # Mock a position that entered at 5000
    pos = {'entry_price': 5000.0, 'type': 'BUY', 'symbol': 'MES', 'size': 1}
    exit_signal = core_tick_loop(adapter, ticks, exit_check_pos=pos)
        
    assert exit_signal is not None, "Stagnation exit never triggered despite 300 flat ticks!"
    assert exit_signal['reason'] == 'Stagnation Decay', f"Expected 'Stagnation Decay', got {exit_signal['reason']}"

if __name__ == '__main__':
    print("🚀 Starting Midas Headless UAT Suite...")
    
    run_uat_scenario("Chop Data (Tight Range)", generate_chop_data(), test_chop)
    run_uat_scenario("Elevator Flush (40pt Drop)", generate_elevator_flush(), test_elevator_flush)
    run_uat_scenario("Stagnation (Time Decay)", generate_stagnation(), test_stagnation)
    
    run_monte_carlo_chaos_engine(num_days=100)
    run_historical_batch("data/mes_ticks.txt", "data/mnq_ticks.txt") # Example, modify path to your CSV exports
    
    print("\n🏁 All Scenarios Executed.")