import pandas as pd
import joblib
import matplotlib.pyplot as plt

# --- Configuration ---
STARTING_BALANCE = 1000
WIN_AMOUNT = 50
LOSS_AMOUNT = -20
PROBABILITY_THRESHOLD = 0.60
DATA_FILE = 'data/labeled_training_data.csv'
MODEL_FILE = 'models/midas_truth_engine.joblib'
FEATURES = ['atr_mes', 'atr_mnq', 'above_ema', 'in_sync', 'hour']

def run_backtest():
    """
    Loads historical data and a trained model to simulate trades and evaluate performance.
    """
    print("🚀 Starting the Midas Backtesting Time Machine...")

    # --- Load Resources ---
    try:
        df = pd.read_csv(DATA_FILE)
        model = joblib.load(MODEL_FILE)
    except FileNotFoundError as e:
        print(f"❌ Error: Could not find a required file. Make sure these files exist:\n- {DATA_FILE}\n- {MODEL_FILE}")
        print(f"Details: {e}")
        return

    # --- Prepare Data ---
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df = df.dropna(subset=FEATURES).copy() # Ensure no missing data for features

    # --- 🧠 THE FIX: Batch Prediction ---
    # Instead of predicting row-by-row inside the loop, we predict everything at once.
    # We pass the DataFrame df[FEATURES] so the model sees the correct feature names.
    print(f"🧠 Truth Engine is analyzing {len(df):,} minutes of history...")
    all_probabilities = model.predict_proba(df[FEATURES])[:, 1]
    df['ml_confidence'] = all_probabilities

    # --- Initialize Simulation ---
    balance = STARTING_BALANCE
    total_trades = 0
    wins = 0
    equity_curve = [STARTING_BALANCE]
    
    print(f"📜 Simulating trades with a starting balance of ${balance:,.2f}...")

    # --- Main Simulation Loop ---
    # This loop is now lightning fast because we are just doing simple math, not ML calls.
    for index, row in df.iterrows():
        # Check if the model's confidence from our batch prediction is above our threshold
        if row['ml_confidence'] > PROBABILITY_THRESHOLD:
            # --- Execute Trade ---
            total_trades += 1
            
            # Use the 'label' as the ground truth for trade outcome
            if row['label'] == 1:
                balance += WIN_AMOUNT
                wins += 1
            else:
                balance += LOSS_AMOUNT
            
            equity_curve.append(balance)

    # --- Results & Summary ---
    print("\n--- 📈 Backtest Summary ---")
    if total_trades > 0:
        win_rate = (wins / total_trades) * 100
        print(f"Total Trades Executed: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Final Account Balance: ${balance:,.2f}")
        print(f"Total Profit/Loss: ${balance - STARTING_BALANCE:,.2f}")
    else:
        print("No trades were executed based on the specified criteria.")
        print(f"Final Account Balance: ${balance:,.2f}")

    # --- Generate Equity Curve Plot ---
    if len(equity_curve) > 1:
        plt.figure(figsize=(12, 6))
        plt.plot(equity_curve, color='#00ff41', linewidth=2)
        plt.title('Midas Engine: Account Equity Curve')
        plt.xlabel('Trade Number')
        plt.ylabel('Account Balance ($)')
        plt.grid(True, alpha=0.3)
        
        plot_filename = 'equity_curve.png'
        plt.savefig(plot_filename)
        print(f"✅ Equity curve chart saved to {plot_filename}")

if __name__ == "__main__":
    run_backtest()