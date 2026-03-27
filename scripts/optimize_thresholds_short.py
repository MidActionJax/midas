import pandas as pd
import joblib
import os
import glob

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_FILE = os.path.join(BASE_DIR, 'models', 'midas_brain_short.pkl')

# Target your historical validation data (adjust the path if necessary)
DATA_DIR = os.path.join(BASE_DIR, 'data', 'lvl_2_clean', 'short')

# --- 1. UPDATE THE FEATURES LIST (Near the top of the file) ---
FEATURES = [
    'Bid_Vol', 'Ask_Vol', 'Imbalance_Skew_30s', 
    'Bid_Drop_Velocity', 'Ask_Surge_Velocity', 
    'Price_Momentum_10s', 'Distance_from_SMA60', 'Volatility_60s'
]
TARGET_COL = 'Target'
ATR_COL = 'Volatility_60s'  # We use Volatility_60s as our historical ATR equivalent

def run_grid_search():
    print("🚀 Starting Midas Grid Search Optimizer...\n")
    
    # 1. Load the Model
    if not os.path.exists(MODEL_FILE):
        print(f"❌ Error: Could not find Truth Engine at {MODEL_FILE}")
        return
        
    print(f"🧠 Loading Truth Engine...")
    model = joblib.load(MODEL_FILE)
    
    # 2. Load the Historical Data
    print(f"📂 Searching for historical testing data in {DATA_DIR}...")
    data_files = glob.glob(os.path.join(DATA_DIR, "Short_ML_Ready*.csv"))
    
    if not data_files:
        print("❌ Error: No ML_Ready data files found. Please ensure your testing data is available.")
        return
        
    # Stitch together all available testing data
    df = pd.concat([pd.read_csv(f) for f in data_files], ignore_index=True)
    
    # --- 2.5 Inject Feature Engineering ---
    # --- 2. UPDATE THE TIME-SERIES MATH (Around line 40) ---
    print("🔧 Reconstructing time-series features (Liquidity Vacuums)...")
    
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
        df.sort_values('Timestamp', inplace=True)
        if 'Hour' not in df.columns:
            df['Hour'] = df['Timestamp'].dt.hour
            
    if 'Mid_Price' not in df.columns:
        df['Mid_Price'] = (df['Best_Bid'] + df['Best_Ask']) / 2
        
    # NEW SHORT FEATURES:
    df['Bid_Drop_Velocity'] = df['Bid_Vol'].diff(5)
    df['Ask_Surge_Velocity'] = df['Ask_Vol'].diff(5)
    df['Price_Momentum_10s'] = df['Mid_Price'].diff(10)
    df['Imbalance_Skew_30s'] = df['Imbalance'].rolling(window=30).mean()
    df['SMA_60'] = df['Mid_Price'].rolling(window=60).mean()
    df['Distance_from_SMA60'] = df['Mid_Price'] - df['SMA_60']
    df['Volatility_60s'] = df['Mid_Price'].rolling(window=60).std()

    if not all(col in df.columns for col in FEATURES + [TARGET_COL]):
        print(f"❌ Error: Missing required features in the dataset. Required: {FEATURES}")
        return
        
    df.dropna(subset=FEATURES + [TARGET_COL], inplace=True)
    print(f"✅ Loaded {len(df):,} valid snapshots of historical data.")
    
    # 3. Batch Prediction (Optimization)
    print("⚡ Running batch predictions on historical data (this is much faster than row-by-row)...")
    # Multiply by 100 to convert to a percentage format (e.g. 85.0%)
    df['ml_confidence'] = model.predict_proba(df[FEATURES])[:, 1] * 100.0

    # 4. Define the Grid
    atr_thresholds = [0.50, 0.75, 1.00, 1.25, 1.50]
    confidence_thresholds = [60.0, 70.0, 80.0, 85.0, 90.0]
    
    results = []

    print("⚙️ Executing Grid Search Simulation...\n")
    
    # 5. The Simulation Loop
    for atr_thresh in atr_thresholds:
        for conf_thresh in confidence_thresholds:
            
            # Filter based on current Grid parameters
            valid_trades = df[(df[ATR_COL] >= atr_thresh) & (df['ml_confidence'] >= conf_thresh)]
            
            total_trades = len(valid_trades)
            
            if total_trades > 0:
                wins = valid_trades[TARGET_COL].sum()
                losses = total_trades - wins
                win_rate = (wins / total_trades) * 100
                
                # Calculate Estimated PnL (+3.0 points for win, -1.0 point for loss)
                est_pnl = (wins * 3.0) + (losses * -1.0)
            else:
                win_rate = 0.0
                est_pnl = 0.0
                
            results.append({
                'atr': atr_thresh, 'conf': conf_thresh, 
                'trades': total_trades, 'win_rate': win_rate, 'pnl': est_pnl
            })

    # 6. The Output (Sorted Leaderboard)
    results.sort(key=lambda x: x['pnl'], reverse=True)
    
    print("🏆 OPTIMIZATION LEADERBOARD 🏆")
    print("-" * 75)
    print(f"{'ATR':<8} | {'Confidence':<12} | {'Total Trades':<14} | {'Win Rate':<10} | {'Est. PnL':<10}")
    print("-" * 75)
    for r in results:
        print(f"{r['atr']:<8.2f} | {r['conf']:<12.1f} | {r['trades']:<14,d} | {r['win_rate']:<8.1f}% | {r['pnl']:<10.1f}")
    print("-" * 75)

if __name__ == '__main__':
    run_grid_search()