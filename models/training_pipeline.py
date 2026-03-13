import numpy as np
import pandas as pd
from models.synthetic_gan import generate_synthetic_data
from models.rl_agent import train_midas_agent

def prepare_training_data(num_samples):
    """
    Generates synthetic data from the GAN and enriches it with the 
    required technical indicators to match the RL Environment's observation space.
    """
    print(f"Generating {num_samples} rows of synthetic market data...")
    df = generate_synthetic_data(num_samples)
    
    print("Calculating technical indicators...")
    # 1. Price
    df['price'] = df['close']
    
    # 2. 200-Period EMA
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # True Range (required for ATR and Chop)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 3. 14-Period ATR (Simple Moving Average of True Range)
    df['atr'] = tr.rolling(window=14).mean()
    
    # 4. 14-Period Choppiness Index (Re-implementing logic.py calculation)
    atr_ewm = tr.ewm(span=14, adjust=False).mean()
    atr_sum = atr_ewm.rolling(window=14).sum()
    highest_high = df['high'].rolling(window=14).max()
    lowest_low = df['low'].rolling(window=14).min()
    
    denominator = highest_high - lowest_low
    # Avoid division by zero in ranging markets
    df['chop_index'] = np.where(
        denominator == 0, 
        100.0, 
        100 * np.log10(atr_sum / denominator) / np.log10(14)
    )
    
    # 5. Whale Strength (Randomized but realistic institutional flow)
    df['whale_strength'] = np.random.uniform(0.0, 5.0, size=len(df))
    
    # Filter to required features and drop NaN rows caused by rolling windows
    high_fidelity_df = df[['price', 'ema_200', 'chop_index', 'atr', 'whale_strength']].dropna().reset_index(drop=True)
    return high_fidelity_df

if __name__ == "__main__":
    print("--- Starting Midas Training Pipeline ---")
    training_df = prepare_training_data(20000)
    print(f"High-Fidelity DataFrame prepared. Shape: {training_df.shape}")
    train_midas_agent(training_df, total_timesteps=20000)