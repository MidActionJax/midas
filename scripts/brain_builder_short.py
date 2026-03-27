import pandas as pd
import glob
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, precision_score
import joblib

print("🔍 Hunting for all SHORT ML_Ready files...")
# We changed this to look for your new "Short" files in the current folder
file_list = glob.glob("data/lvl_2_clean/short/Short_ML_Ready*.csv")
print(f"✅ Found {len(file_list)} files. Stitching them together...")

# Zip all 12 files into one giant Master Dataset
df_list = [pd.read_csv(file) for file in file_list]
df = pd.concat(df_list, ignore_index=True)

print(f"🧵 Master Dataset created! Total 1-second snapshots: {len(df):,}")

# --- THE TIME MACHINE FIX ---
print("⏱️ Sorting timeline to prevent Look-Ahead Bias...")
# utc=True fixes the yellow pandas warning!
df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
df.sort_values('Timestamp', inplace=True)

# --- PHASE 5: THE MEMORY MATRIX (LIQUIDITY VACUUM DETECTORS) ---
print("🧠 Injecting Short-Biased Memory into the AI (Detecting Liquidity Vacuums)...")

# 1. The Floor Dropping Out (Bid Velocity)
# If Bid_Drop_Velocity is highly negative, buyers are canceling orders and running away.
df['Bid_Drop_Velocity'] = df['Bid_Vol'].diff(5)

# 2. Seller Panic (Ask Surge Velocity)
# If Ask_Surge_Velocity is highly positive, sellers are rushing in to dump.
df['Ask_Surge_Velocity'] = df['Ask_Vol'].diff(5)

# 3. Price Acceleration (Downward Momentum)
# How fast has the price dropped in the last 10 seconds?
df['Price_Momentum_10s'] = df['Mid_Price'].diff(10)

# 4. Sustained Order Book Skew
# Instead of a 1-second snapshot of imbalance, what is the 30-second sustained pressure?
df['Imbalance_Skew_30s'] = df['Imbalance'].rolling(window=30).mean()

# 5. Trend Exhaustion (Rubber Band Effect)
# Instead of just crossing moving averages, how far has the price stretched away from them?
df['SMA_60'] = df['Mid_Price'].rolling(window=60).mean()
df['Distance_from_SMA60'] = df['Mid_Price'] - df['SMA_60'] # Negative means falling below the trend

# 6. Absolute Volatility
df['Volatility_60s'] = df['Mid_Price'].rolling(window=60).std()

print("🧹 Cleaning up the edges...")
# Drop rows that don't have enough history for the 60-second math
df.dropna(inplace=True)

# --- 2. DEFINE THE RULES OF THE GAME ---
# We are equipping the AI with its new Short-biased radar
features = [
    'Bid_Vol', 'Ask_Vol', 'Imbalance_Skew_30s', 
    'Bid_Drop_Velocity', 'Ask_Surge_Velocity', 
    'Price_Momentum_10s', 'Distance_from_SMA60', 'Volatility_60s'
]
X = df[features]
y = df['Target']

# --- 3. SPLIT THE DATA ---
print("✂️ Splitting data into Training (80% Study Guide) and Testing (20% Final Exam)...")
split_index = int(len(df) * 0.8)
X_train, X_test = X.iloc[:split_index], X.iloc[split_index:]
y_train, y_test = y.iloc[:split_index], y.iloc[split_index:]

# --- 4. TRAIN THE AI ---
print("⚙️ Unleashing the Random Forest... (The SHORT AI is building its checklist now)")

import numpy as np

# 🛑 SURGICAL FIX: The "Anti-Lazy" Multiplier 
# We force the AI to respect Vacuums by making them worth 5x more points on the test.
weights = np.ones(len(y_train))

# Condition 1: A normal successful short (The Wall) gets double weight
weights[y_train == 1] = 2.0 

# Condition 2: A Vacuum short (Price drops, but NO massive seller surge) gets 5x weight
is_vacuum = (y_train == 1) & (X_train['Ask_Surge_Velocity'] <= 0) & (X_train['Price_Momentum_10s'] < 0)
weights[is_vacuum] = 5.0 

# We also increase n_estimators to 150 to give the brain more "trees" to store the new vacuum rules
model = RandomForestClassifier(n_estimators=150, max_depth=20, random_state=42, n_jobs=-1, class_weight='balanced')
model.fit(X_train, y_train, sample_weight=weights)

# --- 5. TAKE THE FINAL EXAM (PROBABILITIES) ---
print("📝 Taking the Final Exam... asking for CONFIDENCE levels on DROPS.")
# Instead of hard 1s and 0s, we ask for the % chance it is a 1
probabilities = model.predict_proba(X_test)[:, 1]

# --- 6. GRADE THE EXAM WITH STRICTER RULES ---
print("\n======================================================")
print("📊 THRESHOLD TESTING (SHORT BRAIN)")

# We will test what happens if we force the bot to be 60%, 70%, and 80% confident
# Testing extreme sniper thresholds
for threshold in [0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
    # Create a new list of predictions based on our strict threshold
    strict_predictions = (probabilities >= threshold).astype(int)
    
    # Calculate the new Precision
    precision = precision_score(y_test, strict_predictions, zero_division=0)
    
    # Count how many trades it actually decided to take
    total_trades_taken = strict_predictions.sum()
    
    print(f"If Bot requires {threshold*100}% Confidence:")
    print(f"   -> Precision (Win Rate): {precision*100:.1f}%")
    print(f"   -> Total Trades Taken: {total_trades_taken:,}")
    print("-" * 40)

print("======================================================\n")

print("💾 Saving the trained SHORT Brain as 'midas_brain_short.pkl'...")
# THIS LINE IS CRITICAL: It saves the new brain under a new name!
joblib.dump(model, "midas_brain_short.pkl")
print("✅ Done! The Short Brain is ready to hunt.")