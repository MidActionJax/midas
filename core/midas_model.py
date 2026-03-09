import joblib
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

class MidasBrain:
    """
    The MidasBrain is responsible for loading the trained ML model,
    providing confidence scores for trading signals, and retraining the model.
    """
    def __init__(self, model_path='midas_v1.pkl'):
        """
        Initializes the MidasBrain, loading the model if it exists.
        """
        self.model_path = model_path
        self.model = self._load_model()

    def _load_model(self):
        """
        Loads the pickled model file if it exists.
        """
        if os.path.exists(self.model_path):
            print(f"Loading existing model from {self.model_path}")
            return joblib.load(self.model_path)
        else:
            print("No model file found. Falling back to 'Initial Wisdom' formula.")
            return None

    def get_confidence_score(self, features):
        """
        Calculates the confidence score for a given set of features.

        If a trained model is loaded, it uses the model to predict the
        probability. Otherwise, it falls back to a weighted formula.

        Args:
            features (dict): A dictionary of market condition features.
                             Expected keys: 'whale_strength', 'trend_alignment', 'session_volume'.

        Returns:
            int: A confidence score percentage (0-100).
        """
        if self.model:
            # Note: This part will require alignment with the actual features
            # the model was trained on. This is a placeholder for inference.
            # We'll need to transform the input `features` dictionary into
            # the same format the model expects (e.g., a Pandas DataFrame).
            print("Using ML model for confidence score (placeholder).")
            # For now, we'll just return a dummy value if the model exists.
            # Actual prediction logic will be more complex.
            # Example:
            # prepared_features = self._prepare_features_for_model(features)
            # probability = self.model.predict_proba(prepared_features)[0][1] # Prob of class '1'
            # return int(probability * 100)
            return 75 # Placeholder value

        else:
            # Fallback to "Initial Wisdom" formula
            whale_strength = features.get('whale_strength', 0)
            trend_alignment = features.get('trend_alignment', 0)
            session_volume = features.get('session_volume', 0)

            # Applying the weighted formula
            score = (whale_strength * 0.6) + (trend_alignment * 0.2) + (session_volume * 0.2)
            
            # Ensure the score is within the 0-100 range
            return max(0, min(100, int(score)))

    def retrain_model(self):
        """
        Retrains the model using the logic from scripts/train_baseline.py.
        """
        print("Initiating model retraining...")
        try:
            # This logic is adapted directly from scripts/train_baseline.py
            PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            TRAINING_DATA_FILE = os.path.join(PROJECT_ROOT, 'training_data.csv')
            
            if not os.path.exists(TRAINING_DATA_FILE):
                print(f"Error: Training data file not found at {TRAINING_DATA_FILE}")
                return False

            print(f"Loading data from {TRAINING_DATA_FILE}...")
            df = pd.read_csv(TRAINING_DATA_FILE)

            if 'outcome_label' not in df.columns:
                print("Error: Target variable 'outcome_label' not found.")
                return False
                
            df = df.dropna(subset=['outcome_label'])
            y = df['outcome_label']

            features = [
                'price', 'size', 'ema_200_val', 'atr_volatility', 'whale_strength',
                'type', 'trend_dir_numerical', 'session_context'
            ]
            
            missing_features = [f for f in features if f not in df.columns]
            if missing_features:
                print(f"Error: Missing required features: {missing_features}")
                return False

            X = df[features].copy()
            X = pd.get_dummies(X, columns=['type', 'session_context'], drop_first=True)
            X.fillna(0, inplace=True)
            
            if len(X) == 0:
                print("Error: No data for training.")
                return False
            
            if len(df['outcome_label'].unique()) < 2:
                print("Warning: Only one class present. Cannot train.")
                return False

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            print("Training RandomForestClassifier...")
            model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
            model.fit(X_train, y_train)

            y_pred = model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            print(f"Model Accuracy: {accuracy:.4f}")

            print(f"Saving model to {self.model_path}...")
            joblib.dump(model, self.model_path)
            
            # Reload the newly trained model
            self.model = self._load_model()
            print("Model retrained and loaded successfully.")
            return True

        except Exception as e:
            print(f"An error occurred during model retraining: {e}")
            return False

if __name__ == '__main__':
    # Example Usage
    
    # --- Test with no model file (Initial Wisdom) ---
    print("--- Testing Initial Wisdom ---")
    if os.path.exists('midas_v1.pkl'):
        os.remove('midas_v1.pkl') # Ensure no model exists for this test
    
    brain_no_model = MidasBrain()
    mock_features = {'whale_strength': 80, 'trend_alignment': 70, 'session_volume': 90}
    confidence = brain_no_model.get_confidence_score(mock_features)
    print(f"Initial Wisdom Confidence: {confidence}%") # Expected: (80*0.6)+(70*0.2)+(90*0.2) = 48+14+18 = 80
    
    # --- Test retraining ---
    print("Testing Retraining ---")
    # In a real scenario, you'd need training_data.csv to exist
    # For this example, we'll just see if it runs without crashing.
    # We expect it to fail gracefully if the data file is missing.
    brain_no_model.retrain_model()
    
    # --- Test with a loaded model (placeholder) ---
    print("Testing With Model (Post-Retrain) ---")
    if brain_no_model.model:
        confidence_model = brain_no_model.get_confidence_score(mock_features)
        print(f"Model-based Confidence: {confidence_model}%")

