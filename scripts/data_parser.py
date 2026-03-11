import pandas as pd

def clean_nt8_data(filepath):
    # Load the semicolon-delimited data
    df = pd.read_csv(filepath, sep=';', names=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Convert timestamp to actual datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y%m%d %H%M%S')
    
    # Calculate ATR (Volatility Filter - The 4th Key)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.rolling(window=14).mean()
    
    return df

# 1. Clean both files
print("🧹 Cleaning MES data...")
mes_df = clean_nt8_data('data/MES 03-26.Last.txt')

print("🧹 Cleaning MNQ data...")
mnq_df = clean_nt8_data('data/MNQ 03-26.Last.txt')

# 2. Merge them so the AI can see the S&P and Nasdaq side-by-side
print("🔗 Merging markets...")
merged_df = pd.merge_asof(
    mes_df.sort_values('timestamp'), 
    mnq_df.sort_values('timestamp'), 
    on='timestamp', 
    suffixes=('_mes', '_mnq')
)

# 3. Save the "Golden Dataset"
merged_df.to_csv('data/golden_training_data.csv', index=False)
print("✅ Done! Golden Dataset created with 4th Key (ATR) integrated.") 