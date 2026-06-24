# midas
A futures bot :)

**A multi-agent, ML-powered futures trading terminal for MES and MNQ.**

Midas is a sophisticated, machine-learning-assisted Order Flow trading terminal that transforms a real-time data feed into actionable, high-probability trade signals. It is designed to move beyond simple, rule-based scripting into a multi-agent system where specialized AI "brains" are deployed based on the current market regime.

This document serves as the master guide to the project. It details the architecture, operational procedures, and the development backlog, ensuring you can understand the system's state and your next steps, even after a long break.

---


## ⚙️ System Architecture

Midas is a multi-threaded Flask application that separates the web interface from the background trading engine, preventing the UI from freezing during market analysis.

| Component | Tool | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Flask | Lightweight web server to host the UI and handle API requests. |
| **Concurrency** | Python `threading` | Allows the bot to loop infinitely in the background while the website stays responsive. |
| **Futures Data** | **NinjaTrader 8 + C#** | The `MidasBridge.cs` indicator runs inside NT8, pushing live market data (Trades, L2 DOM, 15m EMA) via a TCP socket to the Python engine. |
| **Frontend** | Bootstrap 5, Chart.js, AJAX | Powers the dark-mode dashboard, charts, and real-time data updates without page reloads. |
| **AI Brains** | `scikit-learn` | `RandomForestClassifier` models are trained on historical data to predict price movements. |
| **State Management** | `core/state_manager.py` | A thread-safe global dictionary that shares information (market data, PnL, signals) between the Flask UI and the background engine. |
| **Trade Execution** | `core/adapters` | An adapter pattern (`NTFuturesAdapter`) translates the engine's generic `buy`/`sell` commands into specific execution orders for NinjaTrader. |

---

## 🧠 The Brains of Midas: A Multi-Agent System

Midas uses a **Strategy Manager** (`core/engine.py`) that analyzes the market's "choppiness" and deploys the appropriate AI agent for the job.

### 1. The Dual-Core Snipers (Long/Short Brains)
*   **Models:** `models/midas_brain.pkl` (Long) & `models/midas_brain_short.pkl` (Short)
*   **Purpose:** These are `RandomForestClassifier` models trained to detect high-momentum breakouts. They are the primary agents when the market is trending (`Choppiness Index < 50`).
*   **Training:** They are trained on features designed to detect liquidity vacuums and order book pressure, such as `Bid_Drop_Velocity`, `Ask_Surge_Velocity`, and `Imbalance_Skew_30s`.

### 2. The Ping-Pong Agent
*   **Model:** `models/midas_brain_pingpong.pkl`
*   **Purpose:** This agent is deployed when the market is sideways and choppy (`Choppiness Index > 50`). It stops looking for breakouts and instead plays "ping-pong," buying the floor and selling the ceiling of the established range.
*   **Training:** It's trained on features like `Distance_from_SMA60` and `Chop_Index` to identify high-probability mean-reversion setups.

### 3. The AI Supervisor (Reinforcement Learning)
*   **Model:** `models/midas_rl_model.zip`
*   **Purpose:** A high-level supervisor (`PPO` model from `stable_baselines3`) that provides a final "go/no-go" recommendation (`HOLD`, `BUY`, `SELL`). It can veto a signal from the other agents if its own analysis of the broader market context (price, EMA, ATR, whale presence) disagrees.

---

## 🚀 Key Features & Logic

*   **The Decision Trace:** To solve the "black box" problem, the engine logs a detailed checklist for every potential signal, showing exactly which filter passed or failed.
    ```
    [SIGNAL GENERATED]: MES @ 5300.00
    [CHECK] Trend Filter: [PASS]
    [CHECK] Volatility Filter: [PASS]
    [CHECK] ML Confidence: [PASS] (82% >= 70%)
    [CHECK] RL Supervisor: [FAIL] (VETO: Recommends HOLD)
    --- FINAL DECISION: [VETOED] ---
    ```
*   **Phase 2 Institutional Guards:** Hard-coded safety rules in `logic.py` that prevent the AI from making common mistakes:
    *   **DOM Imbalance:** Vetoes shorting if buyers globally outnumber sellers 2-to-1 (and vice-versa for longs).
    *   **Macro Misalignment (Rubber Band):** Vetoes counter-trend trades unless the price has stretched dangerously far (`10.0` points) from the 15-minute EMA, indicating an imminent snap-back.
*   **Tiered Ratchet Position Management:** An advanced, dynamic stop-loss system in `engine.py`:
    *   **Gear 1 (Initial):** A standard dynamic stop-loss (`-6.0` points).
    *   **Gear 2 (Auto-Breakeven):** If a trade goes `+3.5` points in profit, the stop moves to `+0.5` points, guaranteeing no loss.
    *   **Gear 3 (The Runner):** If a trade goes `+4.0` points in profit, a dynamic trailing stop activates to lock in gains as the trade runs.
*   **Virtual Squawk Box (5th Key):** The `TapeScanner` class in `logic.py` analyzes the trade feed in real-time to detect rhythmic institutional algorithms (e.g., a "shredder" buying 50 contracts every 3 seconds). If a signal aligns with a detected "Whale" footprint, its confidence score is significantly boosted.

---

## 💻 How to Run the Bot

1.  **Prerequisites:**
    *   NinjaTrader 8 with an active data feed (Live or Replay).
    *   The `MidasBridge.cs` indicator compiled and added to a 1-minute `MES` chart in NT8.
    *   Python 3.9+.
2.  **Installation:**
    ```bash
    # Create a virtual environment
    python -m venv venv
    source venv/bin/activate # or .\venv\Scripts\activate on Windows

    # Install dependencies (assuming a requirements.txt exists)
    pip install -r requirements.txt
    ```
3.  **Configuration:**
    *   Open `config.py`.
    *   Set `TRADING_MODE = 'NT_FUTURES'`. This is the primary mode for live trading and market replay.
    *   Ensure `NT_PORT` matches the port configured in the `MidasBridge.cs` indicator settings in NinjaTrader.
4.  **Execution:**
    *   Start NinjaTrader and ensure the chart with `MidasBridge.cs` is active.
    *   Run the Flask application:
        ```bash
        python app.py
        ```
    *   Open your web browser to `http://127.0.0.1:5000`.
    *   Use the dashboard to start the engine, monitor logs, and manage trades.

---

## 🧠 The MLOps Pipeline: How to Retrain the AI

This is the most critical workflow for long-term success. When you have new market data and want to improve the AI's performance, follow these steps.

### Step 1: Data Harvesting (The C# Vacuum)
*   **Action:** Use NinjaTrader's Market Replay feature.
*   **Process:** Load 1-3 months of `MES` Market Replay data. Attach the `MidasBridge.cs` script to a chart and run the replay at max speed.
*   **Result:** The C# script will dump millions of rows of millisecond-accurate Level 2 order book data into massive `.csv` files in your NinjaTrader documents folder. Move these files to `E:/NT_lvl_2_data` (or update the path in the scripts).

### Step 2: Data Storytelling (Labeling the Targets)
*   **Action:** Run the `story_maker` scripts.
*   **Process:**
    ```bash
    python scripts/story_maker.py       # Hunts for 2-point JUMPS
    python scripts/story_maker_short.py # Hunts for 2-point DROPS
    ```
*   **Result:** These scripts process the raw data and create two new files: `Master_ML_Ready_Data_Long.csv` and `Master_ML_Ready_Data_Short.csv`. They label every second of data as `1` (a successful 2-point move occurred in the next 60s) or `0` (it didn't).

### Step 3: Brain Building (Training the Snipers)
*   **Action:** Run the `brain_builder` scripts.
*   **Process:**
    ```bash
    # (Assuming a brain_builder.py exists for longs)
    python scripts/brain_builder_short.py
    ```
*   **Result:** These scripts train the `RandomForestClassifier` on the labeled "story" data. They will output new, smarter `midas_brain.pkl` and `midas_brain_short.pkl` files.

### Step 4: Ping-Pong Training
*   **Action:** Run the `train_pingpong` script.
*   **Process:**
    ```bash
    python scripts/train_pingpong.py
    ```
*   **Result:** This script specifically looks for choppy, sideways market conditions in the raw data and trains a dedicated agent for those scenarios, saving it as `midas_brain_pingpong.pkl`.

### Step 5: Deployment
*   **Action:** Copy the newly trained `.pkl` files from the `scripts` directory into the `/models` directory, overwriting the old ones.
*   **Process:** Restart the `app.py` engine. The bot will automatically load the new, improved brains.

