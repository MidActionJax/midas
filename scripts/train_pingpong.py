import os
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# --- CONFIGURATION ---
# Point this to the folder where your 3 months of 1-second historical CSVs are saved
HISTORICAL_DATA_FOLDER = "E:/NT_lvl_2_data" 
MODEL_OUTPUT_PATH = "./models/midas_brain_pingpong.pkl"

# Parameters
FORWARD_LOOK_WINDOW = 60  # How many seconds to wait for the bounce
MIN_WALL_VOLUME = 25.0    # What we consider a "Macro Wall"
CHOP_THRESHOLD = 50.0     # Regime filter

def process_level2_dump(filepath):
    """
    The Data Alchemist: Converts raw millisecond Level 2 tick data
    into clean 1-second snapshots with AI Indicators.
    """
    print(f"  -> Processing raw ticks into 1-Second AI bars...")
    df = pd.read_csv(filepath)

    # 1. Setup Time Index
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.set_index('Timestamp', inplace=True)

    # 2. Extract Top of Book (Position 0 = Best Bid / Best Ask)
    bids = df[(df['Side'] == 'Bid') & (df['Position'] == 0)]
    asks = df[(df['Side'] == 'Ask') & (df['Position'] == 0)]

    # 3. Resample to 1-second snapshots (take the last known value of that second)
    bids_1s = bids.resample('1S').last()
    asks_1s = asks.resample('1S').last()

    # 4. Merge Bids and Asks into a single timeline
    merged = pd.DataFrame(index=bids_1s.index.union(asks_1s.index)).sort_index()
    merged['best_bid'] = bids_1s['Price']
    merged['bid_vol'] = bids_1s['Volume']
    merged['best_ask'] = asks_1s['Price']
    merged['ask_vol'] = asks_1s['Volume']

    # Forward-fill to carry over resting orders during quiet seconds
    merged.ffill(inplace=True)

    # 5. Calculate Synthetic 'Close' (Mid-Price of the spread)
    merged['close'] = (merged['best_bid'] + merged['best_ask']) / 2.0

    # 6. Calculate Technical Indicators on the fly
    merged['sma_60'] = merged['close'].rolling(60).mean()
    
    merged['rolling_high'] = merged['close'].rolling(14).max()
    merged['rolling_low'] = merged['close'].rolling(14).min()

    merged['tr'] = merged['rolling_high'] - merged['rolling_low']
    merged['atr'] = merged['tr'].rolling(14).mean()

    # Choppiness Index (with zero-division protection)
    atr_sum = merged['atr'] * 14
    denominator = merged['rolling_high'] - merged['rolling_low']
    merged['chop_index'] = np.where(denominator == 0, 50.0, 100 * np.log10(atr_sum / denominator) / np.log10(14))

    # Drop the first 60 seconds (since indicators need time to warm up)
    return merged.dropna()

def extract_ping_pong_setups(df):
    """
    Scans historical data, finds sideways market conditions, 
    and checks if bouncing off the floor/ceiling was a winning or losing trade.
    """
    print("Scraping history for Ping-Pong setups...")
    features = []
    labels = []

    # Ensure required columns exist (Update these if your CSV headers differ)
    required_cols = ['close', 'sma_60', 'chop_index', 'best_bid', 'best_ask', 'bid_vol', 'ask_vol', 'atr']
    for col in required_cols:
        if col not in df.columns:
            print(f"WARNING: Missing column '{col}'. Please map your CSV columns correctly.")
            return pd.DataFrame(), []

    # Iterate through the rows to simulate the passage of time
    for i in range(len(df) - FORWARD_LOOK_WINDOW):
        row = df.iloc[i]

        # Rule 1: We only play Ping-Pong in the Chop
        if row['chop_index'] <= CHOP_THRESHOLD:
            continue

        current_price = row['close']
        sma_60 = row['sma_60']
        
        # In a real environment we use the global Macro Box, here we approximate with Level 1 vol
        floor_dist = current_price - row['best_bid']
        ceil_dist = row['best_ask'] - current_price
        
        setup_type = None

        # Setup A: Bouncing off the Floor
        if floor_dist <= 1.0 and row['bid_vol'] >= MIN_WALL_VOLUME and current_price < sma_60:
            setup_type = 'BUY'
            
        # Setup B: Rejecting off the Ceiling
        elif ceil_dist <= 1.0 and row['ask_vol'] >= MIN_WALL_VOLUME and current_price > sma_60:
            setup_type = 'SELL'

        if setup_type:
            # We found a setup! Now, let's look into the future to grade it.
            future_window = df.iloc[i+1 : i+FORWARD_LOOK_WINDOW]
            
            win = 0 # Default to LOSS
            
            if setup_type == 'BUY':
                # Did it successfully bounce back to the SMA 60?
                if any(future_window['close'] >= sma_60):
                    win = 1
                # Did the floor collapse and stop us out (-1.25 pts)?
                elif any(future_window['close'] <= current_price - 1.25):
                    win = 0 
            
            elif setup_type == 'SELL':
                # Did it successfully reject down to the SMA 60?
                if any(future_window['close'] <= sma_60):
                    win = 1
                # Did the ceiling break and stop us out (+1.25 pts)?
                elif any(future_window['close'] >= current_price + 1.25):
                    win = 0

            # Store the contextual data the AI will use to learn
            feature_row = {
                'Distance_from_SMA60': abs(current_price - sma_60),
                'Floor_Vol': row['bid_vol'],
                'Ceiling_Vol': row['ask_vol'],
                'ATR': row['atr'],
                'Chop_Index': row['chop_index']
            }
            
            features.append(feature_row)
            labels.append(win)

    return pd.DataFrame(features), labels


def train_agent():
    print(f"--- Midas AI Lab: Training Ping-Pong Agent ---")
    
    all_features = pd.DataFrame()
    all_labels = []

    # 1. Scrape all CSVs in the data folder
    if not os.path.exists(HISTORICAL_DATA_FOLDER):
        print(f"Folder not found: {HISTORICAL_DATA_FOLDER}. Create it and add your historical CSVs.")
        return

    for file in os.listdir(HISTORICAL_DATA_FOLDER):
        if file.endswith('.csv'):
            print(f"Reading {file}...")
            filepath = os.path.join(HISTORICAL_DATA_FOLDER, file)
            
            try:
                # 1. Convert Ticks to AI Bars
                processed_df = process_level2_dump(filepath)
                
                # 2. Extract training examples
                features, labels = extract_ping_pong_setups(processed_df)
            except Exception as e:
                print(f"  -> Error processing {file}: {e}")
                continue
            if not features.empty:
                all_features = pd.concat([all_features, features], ignore_index=True)
                all_labels.extend(labels)

    if all_features.empty:
        print("No valid Ping-Pong setups found in data. Check your CSV column names.")
        return

    print(f"\nExtracted {len(all_labels)} viable Ping-Pong setups from history.")
    
    # 2. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(all_features, all_labels, test_size=0.2, random_state=42)

    # 3. Build the Brain (Random Forest)
    # We restrict depth so it doesn't overfit on sideways noise!
    print("Training Random Forest Classifier...")
    model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, class_weight='balanced')
    model.fit(X_train, y_train)

    # 4. Grade the Brain
    predictions = model.predict(X_test)
    print("\n--- PING-PONG AGENT EXAM RESULTS ---")
    print(f"Accuracy: {accuracy_score(y_test, predictions)*100:.2f}%")
    print(classification_report(y_test, predictions))

    # 5. Save the Brain
    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    joblib.dump(model, MODEL_OUTPUT_PATH)
    print(f"\n✅ SUCCESS! Ping-Pong Brain saved to {MODEL_OUTPUT_PATH}")
    print("Midas V2.0 Phase 2 is complete. Restart the engine!")

if __name__ == "__main__":
    train_agent()