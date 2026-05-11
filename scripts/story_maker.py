import pandas as pd
import numpy as np
import time
import glob

master_data = []
for file_name in sorted(glob.glob('*MES_Level2_Dump*.csv')):
    print(f"⏳ Processing {file_name}...")

    print("⏳ Loading raw Level 2 data... (This might take a minute or two)")
    # Load the CSV. We tell pandas what the columns are just to be safe.
    df = pd.read_csv(file_name)

    print("⏱️ Converting timestamps to readable time...")
    # Convert the messy text timestamps into actual math-ready time objects
    # Convert timestamps, but if it hits garbage (errors='coerce'), turn it into a blank 'NaT' (Not a Time)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')

    # Immediately drop any rows that Python blanked out
    df = df.dropna(subset=['Timestamp'])

    df['Timestamp'] = df['Timestamp'].dt.tz_localize('US/Arizona').dt.tz_convert('US/Eastern')

    print("📈 Calculating Institutional Session CVD...")
    df.sort_values('Timestamp', inplace=True)
    df['Price_Change'] = df['Price'].diff()
    df['Tick_CVD'] = 0.0
    df.loc[df['Price_Change'] > 0, 'Tick_CVD'] = df['Volume']
    df.loc[df['Price_Change'] < 0, 'Tick_CVD'] = -df['Volume']

    # Reset if there's a 2-hour gap (new session)
    df['Time_Gap'] = df['Timestamp'].diff().dt.total_seconds()
    df['Session_ID'] = (df['Time_Gap'] > 7200).cumsum()
    df['Session_CVD'] = df.groupby('Session_ID')['Tick_CVD'].cumsum()

    print("️ Compressing chaos into 1-second snapshots...")
    # Set the time as our index so we can group it
    df.set_index('Timestamp', inplace=True)

    # Separate the buyers (Bids) and sellers (Asks)
    # We sum up the total volume sitting on the book for every single second
    bids = df[df['Side'] == 'Bid'].resample('1s').agg({'Volume': 'sum', 'Price': 'max'}).rename(columns={'Volume': 'Bid_Vol', 'Price': 'Best_Bid'})
    asks = df[df['Side'] == 'Ask'].resample('1s').agg({'Volume': 'sum', 'Price': 'min'}).rename(columns={'Volume': 'Ask_Vol', 'Price': 'Best_Ask'})

    # Glue them back together into one clean order book
    book = pd.merge(bids, asks, left_index=True, right_index=True, how='outer').ffill().dropna()

    cvd_1s = df['Session_CVD'].resample('1s').last()
    book = book.join(cvd_1s).ffill()

    print("🧮 Calculating Order Book Imbalance and Time Context...")
    book['Imbalance'] = book['Bid_Vol'] - book['Ask_Vol']
    book['Mid_Price'] = (book['Best_Bid'] + book['Best_Ask']) / 2

    # --- NEW TIME CODE ---
    book['Hour'] = book.index.hour
    book['Minute'] = book.index.minute

    print("🎯 Hunting for the 2-Point Jumps (Creating the Target)...")
    # The "Time Machine" - We look exactly 60 rows (60 seconds) into the future
    book['Future_Price_60s'] = book['Mid_Price'].shift(-60)

    # THE CHECKLIST TARGET:
    # If the future price is 2.0 points (or more) higher than the current price, label it 1 (Success).
    # Otherwise, label it 0 (Noise).
    book['Target'] = np.where(book['Future_Price_60s'] - book['Mid_Price'] >= 2.0, 1, 0)

    # Drop the last 60 seconds of the day because they don't have a future to look at
    book.dropna(inplace=True)
    
    market_hours_book = book.between_time('09:30', '16:00').copy()
    master_data.append(market_hours_book)

book = pd.concat(master_data)

# Let's see what we found!
total_seconds = len(book)
total_jumps = book['Target'].sum()

print("\n======================================================")
print(f"📊 DATA STORY COMPLETE")
print(f"Total 1-Second Snapshots Evaluated: {total_seconds:,}")
print(f"Total 2-Point Jumps Found (The 1s): {total_jumps:,}")
if total_seconds > 0:
    print(f"Percentage of time the market spikes: {(total_jumps/total_seconds)*100:.2f}%")
print("======================================================\n")

print("💾 Saving the AI-ready dataset...")
# Save the new, much smaller, highly targeted dataset
book.to_csv("Master_ML_Ready_Data_Long.csv")
print("✅ Done! We are ready to build the brain.")