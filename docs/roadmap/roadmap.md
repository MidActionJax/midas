# Project Midas: Development Roadmap

## Overview
This roadmap outlines the lifecycle of Project Midas, transitioning it from a basic data-fetching skeleton into a sophisticated, machine-learning-assisted Order Flow trading terminal.

---

## 🟢 Sprint 1: The Foundation (COMPLETED)
**Goal:** Establish the core infrastructure, data feeds, and user interface.
- [x] Set up Python virtual environment and project architecture.
- [x] Build Flask web server and threaded background engine.
- [x] Implement the `Adapter Pattern` for environment switching.
- [x] Connect `ccxt` to fetch live Level 2 Market Depth (Order Book) from crypto exchanges.
- [x] Build the Dark Mode UI with Bootstrap.
- [x] Develop the "Approval Queue" concept (Grey Box execution).
- [x] Execute dummy "Paper" trades updating a localized balance.

---

## 🟢 Sprint 2: The "Smart Trader" Upgrade
**Goal:** Teach the bot how to manage risk, track actual profit, and stop spamming.
- [x] **Take Profit / Stop Loss Logic:** Implement auto-selling. If a trade hits +$50 or -$20, the bot closes the position autonomously.
- [x] **Realized PnL Scoreboard:** Update the UI to show actual daily profit/loss (not just account balance).
- [x] **Anti-Spam Cooldowns:** Add a 5-minute cooldown timer so the bot ignores new Icebergs immediately after a trade.
- [x] **The "Trade Diary" (CSV Logger):** Make the bot save every approved trade (timestamp, price, iceberg size, and eventual profit/loss) to a `history.csv` file. *This is critical for Sprint 5.*

---

## 🟢 Sprint 3: Traditional Markets (The S&P 500)
**Goal:** Expand the bot's reach beyond Crypto into traditional futures.
- [x] **Interactive Brokers Integration:** Install and configure `ib_insync`.
- [x] **The Futures Adapter:** Build `paper_futures.py` and `live_futures.py` to match the existing Adapter interface.
- [x] **Data Normalization:** Ensure the S&P 500 E-mini (ES) order book data formats correctly into the existing UI tables.
- [x] **Contract Rollover Logic:** Add logic to handle futures contract expirations (e.g., switching from the March contract to the June contract).

---

## 🟢 Sprint 4: Advanced Strategy & Risk Filters
**Goal:** Make the bot highly selective about which Icebergs it shows you.
- [x] **Dynamic Sizing:** Stop using a fixed `0.1 BTC` size. Calculate position size based on account percentage and current market volatility (ATR).
- [x] **Trend Filtering:** Integrate basic moving averages. Rule: *Only show BUY signals if the price is above the 200 EMA.*
- [x] **The "Kill Switch":** Implement a Max Daily Drawdown rule. If the bot loses $500 in a day, it auto-locks the dashboard and refuses to trade until tomorrow.

---

## 🟢 Sprint 5: Data Harvesting & Machine Learning Prep
**Goal:** Prepare the system for Artificial Intelligence.
- [x] **Feature Engineering:** Expand the CSV logger to capture "context" (e.g., What time of day was it? Was the overall market trending up or down?).
- [x] **Data Pipeline:** Create a script to clean the `history.csv` data and label trades as `1` (Win) or `0` (Loss).
- [x] **Model Selection:** Set up a local Python ML environment using `scikit-learn` or `XGBoost`.
- [x] **Initial Training:** Train a baseline classification model on the bot's paper-trading history.
- [x] The "Truth Engine" Logger: Build core/logger.py to capture Whale Size, EMA Trend, and ATR Volatility for every signal.
- [x] Objective Labeling: Implement a post-trade "Closing Script" that updates the CSV with the Final PnL result (1 for Win / 0 for Loss).
- [x] Human-vs-Market Audit: Log both the user's decision (Approve/Reject) and the market outcome to help the AI identify when the user is "wrong".
- [x] Model Selection: Set up a local Python environment with scikit-learn or XGBoost to begin analyzing the captured history.csv.

---

## 🟢 Sprint 6: The ML Co-Pilot
**Goal:** Merge the trained ML model with the live trading engine.
- [x] **Model Inference:** Load the trained ML model into `core/logic.py`.
- [x] **The Confidence Score:** Whenever an Iceberg is detected, feed current market conditions into the ML model to get a "Probability of Success" score.
- [x] **UI Update:** Add the `ML Confidence: 85%` badge to the Approval Cards on the dashboard.
- [x] **Auto-Rejection:** Hardcode the engine to silently discard any signal with an ML Confidence below 60%.

---

## 🟢 Sprint 7: Deployment & Hardening
**Goal:** Move the bot off the local laptop and into a secure, 24/7 cloud environment.
- [ ] **Cloud Hosting:** Deploy the system to a Linux VPS (DigitalOcean/AWS/Google Cloud).
- [x] **Web Server Config:** Replace the Flask dev server with Gunicorn and Nginx.
- [x] **Security (Auth):** Add a login screen. The dashboard must be password-protected so no one else can access the URL and click "Approve."
- [x] **Process Management:** Use `systemd` or `pm2` so the bot automatically restarts if the server crashes.

---

## 🟢 Sprint 8: Machine Learning & Historical Intelligence
**Goal:** Transition from a rule-based script to a predictive "Truth Engine" by training on historical data.
- [x] **Historical Data Export**: Use NT8's native Historical Data tool to export 1 year of 1-minute candlestick data for MES and MNQ to CSV files.
- [x] **Data Parser Utility**: Build a Python script to clean and merge the NT8 CSV exports into a format the ML model can understand.
- [x] **Signal Classifier (ML Filter)**: Use scikit-learn to train a model that assigns a "Success Probability" to every signal based on time, volatility, and Nasdaq correlation.
- [x] **Backtesting "Time Machine"**: Create a simulation script to run the Midas Logic against historical data to verify PnL before risking real capital.
- [x] **Intelligence Integration**: Update logic.py to allow the ML model to "Veto" any trade where the historical success probability is below 60%.
- [x] **The 4th Key (Volatility Filter)**: Update logic.py to calculate a "Volatility Zone" using ATR. If ATR is < 2.0 (Dead) or > 15.0 (Chaos), the signal is automatically vetoed.

---

## 🟢 Sprint 9: Real-Time Sync & Live Controls (CURRENT)
**Goal**: Connect the dashboard to your actual financial data and enable "One-Click" mode switching.
- [x] **Live Balance & PnL Sync**: Expand the C# MidasBridge to push your actual NinjaTrader account balance and daily PnL across the socket to the Python adapter.
- [x] **The "Master Switch"**: Add a toggle on the dashboard to seamlessly switch between "Paper" and "Live" (NT_FUTURES) modes without manually editing backend config files.
- [x] **Performance Audit HUD**: Add a visual "Daily Scorecard" specifically tracking wins, losses, and profit for the current 24-hour window.
- [x] **Execution Logger**: Expand the dashboard to show the last 10 trades with specific details on why they were closed (e.g., Hit Take Profit vs. Stop Loss).
- [x] **Account-Aware Position Sizing**: Logic that checks your actual NinjaTrader balance. If you have $50, it strictly buys 1 contract; as your balance grows, it scales up automatically.
- [x] **Hybrid Position Sizing**: Add a UI toggle on the dashboard to switch between "Fixed" (manually locking trade size to 1, 2, etc. contracts) and "Auto" (the engine dynamically scales contract size up or down based on your live NinjaTrader margin balance).

---

## 🟢 Sprint 10: The "Midas" Terminal Overhaul (CURRENT)
**Goal**: Transform the current "mad ugly" interface into a professional, high-fidelity trading desk.
- [x] **Dark Mode Cyber-Aesthetic**: Redesign the UI with a sleek, dark "Cybersecurity" theme that matches your Shrood branding.
- [x] **Interactive Equity Curve**: Integrate Chart.js to plot a live line graph of your account balance growth over time.
- [x] **Correlation Heatmap**: Add a visual "Sync Meter" showing exactly how closely the S&P and Nasdaq have been correlated over the last hour.

--- 









## 🚀 The Real "Endgame" (Expanded)
1. Multi-Strategy Integration (The Diversified Brain)
Right now, Midas is a "one-trick pony" focused on Icebergs. If the market is choppy or there are no big "whales" playing, the bot sits on its hands.

The "Squad" Approach: Instead of one script, you have a "Manager" script that runs multiple independent strategies (Icebergs, Mean Reversion, Breakout).

Market-Adaptive Logic: The bot detects the "regime." If the market is ranging, it shuts off the Trend strategy and dials up the Mean Reversion strategy.

Risk Smoothing: If the Iceberg strategy has a bad day, the Breakout strategy might have a great one, keeping your equity curve moving up smoothly instead of in jagged spikes.

2. Reinforcement Learning (The "Zero-Human" Alpha)
This is where you go from "Software Engineer" to "AI Researcher."

The Simulator: You build a high-fidelity environment where the bot "plays" the market like a video game.

Reward Function: You don't tell it how to trade; you just give it "points" for profit and "penalties" for drawdown.

Discovery: The RL agent might find that buying the "dip" on a specific Tuesday at 10:04 AM when the Nasdaq is down 0.2% has a 70% win rate—a pattern no human would ever think to look for.

Self-Correction: As market conditions change over the years, the RL agent "re-trains" itself to stay ahead of the curve.


High-Fidelity "Synthetic" Training (Intelligence)
A "nuke" doesn't just learn from the past; it learns from every possible future.

GANs (Generative Adversarial Networks): You use AI to create "fake" historical data that is statistically indistinguishable from real markets. You then train your bot on trillions of hours of these "synthetic" market crashes, rallies, and black-swan events.

Stress Mastery: By the time the bot goes live, it has already "lived through" 1,000 versions of the 2008 financial crisis. It becomes unshakeable because nothing the market does is "new" to it.



virtual squack box.. repetitive buying.. 10  50 1000... lable institution etc

🎙️ The "Virtual Squawk Box" Logic
A real squawk box is a person shouting news; a Virtual Squawk Box is an AI that "shouts" when it recognizes a specific big player entering the arena.

Pattern Fingerprinting: Large institutions use execution algorithms (like VWAP or TWAP) that often leave repetitive footprints—for example, a "shredder" that buys exactly 15 contracts every 4.2 seconds.

Institutional Labeling: Your bot doesn't need to know if it's "Goldman Sachs" or "JP Morgan." It just needs to label them "Whale_Alpha" or "Whale_Beta".

The Dominance Factor: Some days, "Whale_Alpha" is in control and pushes the market up all morning. If the bot recognizes Alpha's fingerprint is back on the tape, it can "piggyback" on those trades with massive confidence.

🔑 Does this become the "5th Key"?
I actually think this is better than a standalone key—this is a Predictive Feature for the Reinforcement Learning (RL) brain we discussed earlier.

How we would implement it:

The Tape Scanner: We add a small Python script that looks for "rhythmic" prints (like your 10, 10, 10 or 50, 50, 50 examples).

The Labeler: When the rhythm is detected, the bot flags it: "Institutional Pattern Detected: Type Rhythmic-50."

The Intelligence: We feed that flag into the Truth Engine. The ML model will then learn: "Whenever Rhythmic-50 is buying and we are above the 200 EMA, the trade has a 92% success rate".

---
🗺️ The Level 2 Deep Learning Roadmap
Phase 1: The "C# Vacuum" (Data Harvesting)
We cannot rely on Python to record the Level 2 data; it is too slow, and it will crash your connection.

The Action: We will write a lightweight C# script (a NinjaScript) that lives directly inside NinjaTrader.

The Process: You download 1–3 months of Market Replay data for the MES. You attach this C# script to a chart, set the replay to "Max Speed," and hit play.

The Result: The script acts as a vacuum, bypassing your network port entirely and dumping millions of rows of pristine, millisecond-accurate Level 2 order book updates straight into a massive CSV file on your hard drive.

Phase 2: The "Story Maker" (Data Preparation & Labeling)
An ML model cannot just look at raw numbers and figure out what to do. We have to give it a "Target" so it knows what it is looking for. We don't tell it how to find a trade, we just tell it what a successful trade looks like.

The Action: We write a Python script (using the pandas library) to scan through your giant new CSV file.

The Target: We program it to find every single time the price jumped exactly 2 points within a 60-second window. We label those exact moments in the data as 1 (Success). Everything else is a 0 (Noise).

The Result: A perfectly labeled dataset. We now have the complete Level 2 "story" of what the order book looked like in the minutes immediately preceding a massive price spike.

Phase 3: The "Black Box" (Deep Representation Learning)
This is where we unleash the AI. We stop writing "if/then" rules and hand the keys over to a Deep Learning model (likely an algorithm called XGBoost or a Neural Network).

The Action: We feed the labeled dataset into the model. We tell it: "Here are 5,000 examples of the price jumping 2 points. Look at the Level 2 data leading up to these moments and figure out the pattern yourself."

The Process: The ML will spend hours crunching the numbers. It will build its own internal "checklist." It might discover that a 2-point jump happens when 300 contracts stack on the bid while the ask side empties out—something a human would never catch in real-time.

The Result: A trained model.pkl file. This is the new, hyper-intelligent brain of Midas.

Phase 4: The Simulation & Live Deployment
We do not put real money on this immediately. We have to make sure the model didn't just memorize the past (overfitting).

The Action: We plug the new brain into engine.py.

The Process: We run Midas in PAPER mode on live market data for a week. We let it read the live Level 2 order book and fire its predictions.

The Result: If it consistently hits that 40%+ win rate with strict risk management, we take it off the leash and let it trade real capital.

---
## Backlog!!
- 3 months of data
- Lower thresholds
- check buying/selling?
- Kill switch, close all positions on dashboard
- RuntimeWarning: invalid value encountered in divide
- 1 day. replay? level 2 data. let it discover and train on its own. learn patters on its own. no guidance. 
