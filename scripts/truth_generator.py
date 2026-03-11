import pandas as pd
import numpy as np

# Load the Golden Dataset
df = pd.read_csv('data/golden_training_data.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Parameters from your Midas logic
PROFIT_TARGET = 10.0   # Points ($50 for MES)
STOP_LOSS = 4.0        # Points ($20 for MES)
LOOKAHEAD_WINDOW = 60  # Check the next 60 minutes for a result

def label_minute(index, df):
    # Only label if we have enough future data to check
    if index >= len(df) - LOOKAHEAD_WINDOW:
        return 0
        
    entry_price = df.iloc[index]['close_mes']
    future_data = df.iloc[index+1 : index+1+LOOKAHEAD_WINDOW]
    
    for _, row in future_data.iterrows():
        # Check Stop Loss first (Safety first)
        if row['low_mes'] <= entry_price - STOP_LOSS:
            return 0
        # Check Profit Target
        if row['high_mes'] >= entry_price + PROFIT_TARGET:
            return 1
    return 0

print("🧬 Analyzing 85,000 minutes for the 'Truth'...")
df['label'] = [label_minute(i, df) for i in range(len(df))]

# Add the 200 EMA Trend Key
df['ema_200'] = df['close_mes'].ewm(span=200, adjust=False).mean()
df['above_ema'] = (df['close_mes'] > df['ema_200']).astype(int)

# Add a simple Correlation Key (Are both markets moving the same way?)
df['mes_ret'] = df['close_mes'].pct_change(5)
df['mnq_ret'] = df['close_mnq'].pct_change(5)
df['in_sync'] = ((df['mes_ret'] > 0) == (df['mnq_ret'] > 0)).astype(int)

# Save the training-ready file
df.to_csv('data/labeled_training_data.csv', index=False)
print(f"✅ Done! Found {df['label'].sum()} winning setups.")