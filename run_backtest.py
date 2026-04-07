import time
import os
import sys
import csv
import pandas as pd
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from core.state import state_manager
from core.logic import (
    analyze_order_book, 
    get_market_session, 
    calculate_choppiness_index, 
    analyze_mean_reversion,
    update_session_anchors
)
from core.engine import MidasEngine
from adapters.base import TradingAdapter

# ==========================================
# --- MOCK TIME (CPU SPEED EXECUTION) ---
# ==========================================
_mock_time_val = 1600000000.0
def mock_time():
    return _mock_time_val

time.time = mock_time

# ==========================================
# --- MOCK ADAPTER ---
# ==========================================
class MockAdapter(TradingAdapter):
    """Mimics the NinjaTrader socket, running locally inside the backtest loop."""
    def __init__(self):
        self.wallet_balance = 100000.0
        self.prices = {'MES': 0.0, 'MNQ': 0.0}
        
    def get_wallet_balance(self):
        return self.wallet_balance
        
    def get_current_price(self, symbol):
        return self.prices.get(symbol, 0.0)
        
    def execute_buy(self, symbol, amount, price=None, signal_id=None):
        exec_price = price if price else self.get_current_price(symbol)
        print(f"[BACKTEST] BUY {amount} {symbol} @ {exec_price} (Signal: {signal_id})")
        return True
        
    def execute_sell(self, symbol, amount, price=None, signal_id=None, side='SELL'):
        exec_price = price if price else self.get_current_price(symbol)
        print(f"[BACKTEST] {side} {amount} {symbol} @ {exec_price} (Signal: {signal_id})")
        return True
        
    def get_market_depth(self, symbol):
        price = self.get_current_price(symbol)
        # Synthetic Level 2 Depth to bypass IBKR/NT socket requirements
        return {'bids': [[price - 0.25, 50]], 'asks': [[price + 0.25, 50]]}
        
    def get_open_positions(self):
        # engine.py manage_positions uses adapter.get_open_positions() to sync
        return state_manager.get_active_positions()

# ==========================================
# --- DATA INGESTION ---
# ==========================================
def load_tick_data(filepath, symbol):
    """Reads standard NinjaTrader historical tick CSVs (Timestamp, Price, Volume)."""
    print(f"Loading {symbol} ticks from {filepath}...")
    ticks = []
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return ticks
        
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ticks
        
    col_map = {c.lower(): c for c in df.columns}
    time_col = col_map.get('timestamp', col_map.get('time', col_map.get('date')))
    price_col = col_map.get('price', col_map.get('last', col_map.get('close')))
    vol_col = col_map.get('volume', col_map.get('vol'))
    
    if not time_col or not price_col:
        print(f"Missing time or price column in {filepath}. Available: {list(df.columns)}")
        return ticks
        
    df['parsed_time'] = pd.to_datetime(df[time_col], errors='coerce')
    df = df.dropna(subset=['parsed_time', price_col])
    
    for _, row in df.iterrows():
        ticks.append({
            'timestamp_dt': row['parsed_time'],
            'timestamp': row['parsed_time'].timestamp(),
            'price': float(row[price_col]),
            'volume': float(row[vol_col]) if vol_col else 1.0,
            'symbol': symbol
        })
    return ticks

# ==========================================
# --- THE SCORECARD ---
# ==========================================
def print_scorecard():
    csv_path = 'trade_history.csv'
    if not os.path.exists(csv_path):
        print("\n[SCORECARD] No trade_history.csv found. Did the bot take any trades?")
        return
        
    df = pd.read_csv(csv_path)
    
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
# --- THE ENGINE LOOP ---
# ==========================================
def run_historical_batch(mes_csv_path, mnq_csv_path):
    print(f"\n--- [BACKTEST] Processing {mes_csv_path} and {mnq_csv_path} ---")
    
    if os.path.exists('trade_history.csv'):
        os.remove('trade_history.csv')
        print("Cleared previous trade_history.csv")

    mes_ticks = load_tick_data(mes_csv_path, 'MES')
    mnq_ticks = load_tick_data(mnq_csv_path, 'MNQ')
    
    all_ticks = mes_ticks + mnq_ticks
    if not all_ticks:
        print("No ticks loaded. Exiting.")
        return
        
    print("Sorting merged ticks chronologically...")
    all_ticks.sort(key=lambda x: x['timestamp_dt'])
    
    # 1. Reset Global State
    state_manager.reset_for_new_day()
    state_manager.price_history = {'MES': [], 'MNQ': []}
    state_manager.price_bars = {'MES': [], 'MNQ': []}
    state_manager.clear_active_positions()
    
    adapter = MockAdapter()
    engine = MidasEngine(['MES', 'MNQ'])
    engine.adapter = adapter
    
    global _mock_time_val
    _mock_time_val = all_ticks[0]['timestamp']
    
    last_bar_time = {'MES': _mock_time_val, 'MNQ': _mock_time_val}
    price_buffer = {'MES': [], 'MNQ': []}
    
    print(f"Starting chronological tick loop ({len(all_ticks)} ticks)...")
    
    for i, tick in enumerate(all_ticks):
        sym = tick['symbol']
        price = tick['price']
        ts = tick['timestamp']
        
        # 1. Advance mock time at CPU speed
        _mock_time_val = ts
        state_manager.current_market_time = tick['timestamp_dt']
        
        # 2. Maintain CVD and Prices
        last_price = state_manager.price_history[sym][-1] if state_manager.price_history.get(sym) else None
        if last_price is not None:
            state_manager.update_cvd(price, last_price, tick['volume'])
            
        adapter.prices[sym] = price
        state_manager.add_price(sym, price)
        price_buffer[sym].append(price)
        
        if sym == 'MES':
            current_session = get_market_session()
            update_session_anchors(price, current_session)
        
        # 3. MidasEngine Core - Manage Stops & Exits
        engine.manage_positions()
        
        # 4. Build 1-minute bars
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
        
        # 5. MidasEngine Core - Signal Evaluation (Simulating the active heartbeat)
        if sym == 'MES' and len(state_manager.price_history['MES']) > 60:
            chop_index = getattr(state_manager, 'current_chop_index', 50.0)
            market_depth = adapter.get_market_depth('MES')
            
            signal = None
            if chop_index > 50.0:
                signal = analyze_mean_reversion('MES', market_depth, state_manager.price_history['MES'], chop_index)
            else:
                signal = analyze_order_book('MES', market_depth, state_manager.price_history, adapter)
                
            if signal:
                # Auto-Trade Execution Logic
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
                    
                    # Manually log the entry so Engine's `manage_positions()` can log the exit perfectly
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
                                'signal_id': pos['signal_id'],
                                'timestamp_id': ts,
                                'symbol': 'MES',
                                'type': signal['type'],
                                'price': exec_price,
                                'size': dynamic_size,
                                'user_decision': 'APPROVED',
                            })
                    except Exception as e:
                        pass

        if i > 0 and i % 10000 == 0:
            print(f"Processed {i:,}/{len(all_ticks):,} ticks...")
            
    print("\nBacktest data ingestion complete.")
    print_scorecard()

if __name__ == '__main__':
    # Example Usage: Update with your actual CSV file paths
    print("Midas Dual-Asset Headless Backtester")
    print("======================================")
    print("Usage within a script:")
    print("run_historical_batch('data/mes_ticks.csv', 'data/mnq_ticks.csv')")