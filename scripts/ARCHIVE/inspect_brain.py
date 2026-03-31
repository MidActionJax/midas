import joblib
import pandas as pd

print("🧠 Loading the Midas Brain...")
model = joblib.load("midas_brain.pkl")

# The exact features we trained it on
features = [
    'Bid_Vol', 'Best_Bid', 'Ask_Vol', 'Best_Ask', 
    'Imbalance', 'Mid_Price', 'Hour', 'Minute',
    'Imbalance_Delta_5s', 'Trend_Alignment', 'Volatility_60s'
]

print("📊 Extracting the Decision Matrix...")
importances = model.feature_importances_

# Create a clean, sorted report
df = pd.DataFrame({
    'Feature': features,
    'Importance (%)': importances * 100
}).sort_values(by='Importance (%)', ascending=False)

print("\n==================================================")
print("🔍 WHAT IS THE AI THINKING? (Feature Importance)")
print("==================================================")
# We format the numbers to look like clean percentages
print(df.to_string(index=False, float_format=lambda x: f"{x:.2f}%"))
print("==================================================\n")