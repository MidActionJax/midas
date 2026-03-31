import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, precision_score

# 1. Ensure the models directory exists
if not os.path.exists('models'):
    os.makedirs('models')

# 2. Load the labeled data
df = pd.read_csv('data/labeled_training_data.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['hour'] = df['timestamp'].dt.hour

# 3. Clean up any NaNs (the first few rows usually have empty ATRs)
df = df.dropna(subset=['atr_mes', 'atr_mnq'])

# 4. Select our 4 Keys + Time as features
# We use the 'label' we generated in the previous step as our target
features = ['atr_mes', 'atr_mnq', 'above_ema', 'in_sync', 'hour']
X = df[features]
y = df['label']

if len(y.unique()) < 2:
    print("Not enough diverse data (need both wins and losses). Keeping existing models.")
    import sys
    sys.exit(0)

# 5. Split into Training (80%) and Testing (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 6. Train the Brain (The "Veto" Logic)
print("🧠 Training the Truth Engine... this will take a moment.")
model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
model.fit(X_train, y_train)

# 7. Evaluate: We care most about PRECISION (How often is it right when it says "BUY"?)
y_pred = model.predict(X_test)
precision = precision_score(y_test, y_pred)

print("\n--- MODEL PERFORMANCE ---")
print(f"Confidence Score (Precision): {precision:.2%}")
print("\nFeature Importance (What the bot looks at most):")
for feat, importance in zip(features, model.feature_importances_):
    print(f"- {feat}: {importance:.4f}")

# 8. Save the model so logic.py can use it
joblib.dump(model, 'models/midas_truth_engine.joblib')
print("\n✅ Model saved to models/midas_truth_engine.joblib")