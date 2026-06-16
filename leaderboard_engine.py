import pandas as pd
import os

def get_leaderboard_stats(csv_path='trade_history.csv'):
    default_stats = {
        'daily_crown': 0.0,
        'weekly_high_score': 0.0,
        'whale_catch': 0.0,
        'iron_streak': 0
    }
    
    if not os.path.exists(csv_path):
        return default_stats
        
    try:
        df = pd.read_csv(csv_path)
        if df.empty or 'final_pnl' not in df.columns or 'timestamp_id' not in df.columns:
            return default_stats
            
        df['final_pnl'] = pd.to_numeric(df['final_pnl'], errors='coerce')
        df = df.dropna(subset=['final_pnl'])
        if df.empty:
            return default_stats
            
        # The Whale Catch
        whale_catch = df['final_pnl'].max()
        
        # The Iron Streak
        current_streak = 0
        max_streak = 0
        if 'outcome_label' in df.columns:
            for outcome in df['outcome_label']:
                if str(outcome).upper() == 'WIN':
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
        
        # Date processing
        df['date'] = pd.to_datetime(df['timestamp_id'], unit='s', errors='coerce').dt.date
        df = df.dropna(subset=['date'])
        if df.empty:
            return default_stats
            
        # The Daily Crown
        daily_pnl = df.groupby('date')['final_pnl'].sum()
        daily_crown = daily_pnl.max()
        
        # The Weekly High Score
        if len(daily_pnl) > 0:
            date_range = pd.date_range(start=daily_pnl.index.min(), end=daily_pnl.index.max())
            daily_pnl_filled = daily_pnl.reindex(date_range.date, fill_value=0)
            weekly_rolling = daily_pnl_filled.rolling(window=5, min_periods=1).sum()
            weekly_high_score = weekly_rolling.max()
        else:
            weekly_high_score = 0.0
        
        return {
            'daily_crown': round(float(daily_crown), 2),
            'weekly_high_score': round(float(weekly_high_score), 2),
            'whale_catch': round(float(whale_catch), 2),
            'iron_streak': int(max_streak)
        }
    except Exception as e:
        print(f"Error calculating leaderboard stats: {e}")
        return default_stats