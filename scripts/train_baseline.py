import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def train_model():
    """
    Loads cleaned data, trains a RandomForestClassifier, evaluates it,
    and saves the trained model.
    """
    # --- Define paths ---
    try:
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        TRAINING_DATA_FILE = os.path.join(PROJECT_ROOT, 'training_data.csv')
        MODEL_FILE = os.path.join(PROJECT_ROOT, 'midas_v1.pkl')
    except NameError:
        # Handle case where __file__ is not defined (e.g., in an interactive session)
        PROJECT_ROOT = '.'
        TRAINING_DATA_FILE = 'training_data.csv'
        MODEL_FILE = 'midas_v1.pkl'


    # --- Load Data ---
    if not os.path.exists(TRAINING_DATA_FILE):
        print(f"Error: Training data file not found at {TRAINING_DATA_FILE}")
        print("Please run scripts/prepare_data.py first.")
        return

    print(f"Loading data from {TRAINING_DATA_FILE}...")
    df = pd.read_csv(TRAINING_DATA_FILE)

    # --- Feature Engineering & Selection ---
    if 'outcome_label' not in df.columns:
        print("Error: Target variable 'outcome_label' not found in the data.")
        return
        
    df = df.dropna(subset=['outcome_label'])
    y = df['outcome_label']

    features = [
        'price', 'size', 'ema_200_val', 'atr_volatility', 'whale_strength',
        'type', 'trend_dir_numerical', 'session_context'
    ]
    
    # Check if all features exist
    missing_features = [f for f in features if f not in df.columns]
    if missing_features:
        print(f"Error: The following required features are missing from the data: {missing_features}")
        return

    X = df[features].copy()

    # One-hot encode categorical features
    X = pd.get_dummies(X, columns=['type', 'session_context'], drop_first=True)

    # Simple imputation: fill any remaining NaNs with 0
    X.fillna(0, inplace=True)
    
    if len(X) == 0:
        print("Error: No data available for training after processing. Please check your trade history.")
        return
        
    # Align columns after one-hot encoding for train/test split
    # This avoids errors if one set is missing a category present in the other.
    X_aligned = X.reindex(columns = X.columns, fill_value=0)


    # --- Train/Test Split ---
    # Ensure there's enough data for a split
    if len(df['outcome_label'].unique()) < 2:
        print("Not enough diverse data (need both wins and losses). Keeping existing models.")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X_aligned, y, test_size=0.2, random_state=42, stratify=y
    )

    # --- Model Training ---
    print("Training RandomForestClassifier...")
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    model.fit(X_train, y_train)

    # --- Evaluation ---
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"Model Accuracy: {accuracy:.4f}")

    # --- Save Model ---
    print(f"Saving model to {MODEL_FILE}...")
    joblib.dump(model, MODEL_FILE)
    print("Model saved successfully.")

if __name__ == '__main__':
    train_model()
