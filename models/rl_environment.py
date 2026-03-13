import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd

class MidasTradingEnv(gym.Env):
    """
    A custom OpenAI Gymnasium environment for the Project Midas RL Agent.
    """
    metadata = {'render_modes': ['human']}

    def __init__(self, df: pd.DataFrame):
        super(MidasTradingEnv, self).__init__()
        
        # Market data to simulate over
        self.df = df.reset_index(drop=True)
        self.max_steps = len(self.df) - 1
        
        # Action Space:
        # 0 = Hold (Do nothing / maintain current position)
        # 1 = Buy (Enter Long / Close Short)
        # 2 = Sell (Enter Short / Close Long)
        self.action_space = spaces.Discrete(3)
        
        # Observation Space (Features):
        # 1. Current Price
        # 2. EMA_200
        # 3. Chop Index
        # 4. ATR
        # 5. Whale Strength
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(5,), dtype=np.float32
        )
        
        # Environment State
        self.current_step = 0
        self.position = 0  # 0: Flat, 1: Long, -1: Short
        self.entry_price = 0.0
        self.holding_time = 0
        self.realized_pnl = 0.0
        
        # Reward / Penalty Config
        self.time_penalty = -0.05       # Slight bleed to encourage decisive trades
        self.drawdown_limit = -50.0     # Max floating points allowed against us
        self.loss_penalty_multiplier = 2.0  # Heavier punishment for realizing a loss

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        self.current_step = 0
        self.position = 0
        self.entry_price = 0.0
        self.holding_time = 0
        self.realized_pnl = 0.0
        
        return self._next_observation(), {}

    def _next_observation(self):
        # Fetch the 5 core features for the current step
        obs = np.array([
            self.df.loc[self.current_step, 'price'],
            self.df.loc[self.current_step, 'ema_200'],
            self.df.loc[self.current_step, 'chop_index'],
            self.df.loc[self.current_step, 'atr'],
            self.df.loc[self.current_step, 'whale_strength']
        ], dtype=np.float32)
        return obs

    def step(self, action):
        current_price = self.df.loc[self.current_step, 'price']
        reward = 0.0
        terminated = False
        trade_closed = False
        step_pnl = 0.0

        # Execute actions based on current position
        if action == 1:  # BUY
            if self.position == 0:        # Flat -> Go Long
                self.position = 1
                self.entry_price = current_price
                self.holding_time = 0
            elif self.position == -1:     # Short -> Flat (Close Short position)
                step_pnl = self.entry_price - current_price
                trade_closed = True
                self.position = 0
                
        elif action == 2:  # SELL
            if self.position == 0:        # Flat -> Go Short
                self.position = -1
                self.entry_price = current_price
                self.holding_time = 0
            elif self.position == 1:      # Long -> Flat (Close Long position)
                step_pnl = current_price - self.entry_price
                trade_closed = True
                self.position = 0
                
        elif action == 0:  # HOLD
            if self.position != 0:
                self.holding_time += 1
                reward += self.time_penalty
                
                # Check floating drawdown (Kill Switch logic for RL Agent)
                floating_pnl = (current_price - self.entry_price) if self.position == 1 else (self.entry_price - current_price)
                if floating_pnl <= self.drawdown_limit:
                    step_pnl = floating_pnl
                    trade_closed = True
                    self.position = 0
                    reward -= 100.0  # Massive penalty for blowing past risk limits

        # Realize PnL and Apply Rewards
        if trade_closed:
            self.realized_pnl += step_pnl
            
            if step_pnl > 0:
                reward += step_pnl * 1.0  # Positive reward for points captured
            else:
                reward += step_pnl * self.loss_penalty_multiplier  # Negative penalty for loss
                
            self.holding_time = 0

        # Advance simulation
        self.current_step += 1
        if self.current_step >= self.max_steps:
            terminated = True

        # Gather new state
        obs = self._next_observation()
        info = {
            'step_pnl': step_pnl if trade_closed else 0.0,
            'total_pnl': self.realized_pnl,
            'position': self.position
        }
        
        return obs, reward, terminated, False, info

    def render(self):
        print(f"Step: {self.current_step}/{self.max_steps} | Position: {self.position} | Realized PnL: {self.realized_pnl:.2f}")