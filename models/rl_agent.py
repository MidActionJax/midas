import os
import numpy as np
from stable_baselines3 import PPO
from models.rl_environment import MidasTradingEnv

MODEL_PATH = "models/midas_rl_model"

def train_midas_agent(data_df, total_timesteps=10000):
    """
    Trains a new Reinforcement Learning agent from scratch using the provided dataframe.
    """
    print(f"Initializing MidasTradingEnv with {len(data_df)} rows...")
    env = MidasTradingEnv(data_df)
    
    print("Creating PPO Agent...")
    # MlpPolicy creates a standard feed-forward neural network for the agent's brain
    model = PPO("MlpPolicy", env, verbose=1)
    
    print(f"Training agent for {total_timesteps} timesteps...")
    model.learn(total_timesteps=total_timesteps)
    
    os.makedirs("models", exist_ok=True)
    model.save(MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}.zip")

def retrain_agent(new_data_df, total_timesteps=5000):
    """
    Loads an existing agent and continues training it on fresh market data (Self-Correction).
    """
    if not os.path.exists(f"{MODEL_PATH}.zip"):
        print(f"No existing model found at {MODEL_PATH}.zip. Training from scratch...")
        train_midas_agent(new_data_df, total_timesteps)
        return

    print(f"Loading existing model from {MODEL_PATH}.zip...")
    env = MidasTradingEnv(new_data_df)
    
    # Load the model and bind it to the newly initialized environment
    model = PPO.load(MODEL_PATH, env=env)
    
    print(f"Retraining agent for {total_timesteps} timesteps on fresh data...")
    model.learn(total_timesteps=total_timesteps, reset_num_timesteps=False)
    
    model.save(MODEL_PATH)
    print(f"Updated model saved to {MODEL_PATH}.zip")

def predict_action(obs):
    """
    Given a 5-value observation array, asks the trained RL agent for the best action.
    """
    model = PPO.load(MODEL_PATH)
    # deterministic=True ensures the agent uses its highest probability decision rather than exploring
    action, _states = model.predict(obs, deterministic=True)
    return int(action)