import pandas as pd
import os
import numpy as np

# Define file paths
# Assuming the script is in the 'scripts' directory, and data is in the root.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(PROJECT_ROOT, 'trade_history.csv')
TRAINING_FILE = os.path.join(PROJECT_ROOT, 'training_data.csv')

def prepare_data():
    """
    Reads the trade history, cleans it, and saves a version for model training.
    """
    if not os.path.exists(HISTORY_FILE):
        print(f"Error: Trade history file not found at {HISTORY_FILE}")
        return

    print(f"Reading data from {HISTORY_FILE}...")
    df = pd.read_csv(HISTORY_FILE)

    # 1. Drop incomplete trades (where outcome_label is empty)
    # Replace empty strings with NaN to use dropna
    df['outcome_label'].replace('', np.nan, inplace=True)
    df.dropna(subset=['outcome_label'], inplace=True)
    
    # 2. Convert 'trend_dir' to numerical values
    # The logger saves 'UP' or 'DOWN'. We'll map this to 1 and 0.
    # The GCA says BULLISH/BEARISH but the log contains UP/DOWN
    if 'trend_dir' in df.columns:
        df['trend_dir_numerical'] = df['trend_dir'].apply(lambda x: 1 if x == 'UP' else 0)
    else:
        print("Warning: 'trend_dir' column not found.")

    # 3. Save the cleaned data
    try:
        df.to_csv(TRAINING_FILE, index=False)
        print(f"Successfully cleaned data and saved to {TRAINING_FILE}")
        print(f"Total rows processed: {len(df)}")
    except Exception as e:
        print(f"Error saving training data: {e}")

if __name__ == '__main__':
    prepare_data()
