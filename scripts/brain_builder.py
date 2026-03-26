import pandas as pd
import glob
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, precision_score
import joblib

print("🔍 Hunting for all ML_Ready files...")
# This finds every single CSV file in the folder that starts with "ML_Ready"
file_list = glob.glob("data/lvl_2_clean/ML_Ready*.csv")
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

# --- PHASE 5: THE MEMORY MATRIX ---
print("🧠 Injecting Memory into the AI (Calculating Velocity, Trend, and Volatility)...")

# 1. Order Book Velocity (How much did the Imbalance change in the last 5 seconds?)
df['Imbalance_Delta_5s'] = df['Imbalance'].diff(5)

# 2. Micro-Trend (30-second average vs 60-second average)
df['SMA_30'] = df['Mid_Price'].rolling(window=30).mean()
df['SMA_60'] = df['Mid_Price'].rolling(window=60).mean()
# If Trend_Alignment is Positive, we are trending UP. If Negative, trending DOWN.
df['Trend_Alignment'] = df['SMA_30'] - df['SMA_60']

# 3. Volatility (How violently is the price whipping around in the last 60 seconds?)
df['Volatility_60s'] = df['Mid_Price'].rolling(window=60).std()

print("🧹 Cleaning up the edges...")
# The first 60 rows of the dataset won't have enough history to calculate a 60-second average.
# They will be blank (NaN). We must drop them so the AI doesn't crash.
df.dropna(inplace=True)

# --- 2. DEFINE THE RULES OF THE GAME ---
# We are PRUNING the dead weight. We removed Minute, Imbalance, and Imbalance_Delta.
features = [
    'Bid_Vol', 'Best_Bid', 'Ask_Vol', 'Best_Ask', 
    'Mid_Price', 'Hour', 'Trend_Alignment', 'Volatility_60s'
]
X = df[features]
y = df['Target']

# --- 3. SPLIT THE DATA ---
print("✂️ Splitting data into Training (80% Study Guide) and Testing (20% Final Exam)...")
split_index = int(len(df) * 0.8)
X_train, X_test = X.iloc[:split_index], X.iloc[split_index:]
y_train, y_test = y.iloc[:split_index], y.iloc[split_index:]

# --- 4. TRAIN THE AI ---
print("⚙️ Unleashing the Random Forest... (The AI is building its checklist now)")
# NOTICE n_jobs=-1: This forces your computer to use EVERY CPU core to train faster!
# We removed class_weight='balanced' to cure its paranoia, and increased max_depth to 20 to let it think deeper!
model = RandomForestClassifier(n_estimators=100, max_depth=20, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

# --- 5. TAKE THE FINAL EXAM (PROBABILITIES) ---
print("📝 Taking the Final Exam... but asking for CONFIDENCE levels this time.")
# Instead of hard 1s and 0s, we ask for the % chance it is a 1
probabilities = model.predict_proba(X_test)[:, 1]

# --- 6. GRADE THE EXAM WITH STRICTER RULES ---
print("\n======================================================")
print("📊 THRESHOLD TESTING")

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

print("💾 Saving the trained Master Brain as 'midas_brain.pkl'...")
joblib.dump(model, "midas_brain.pkl")
print("✅ Done! The Brain is ready.")