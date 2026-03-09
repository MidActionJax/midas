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

## 🟡 Sprint 8: Machine Learning & Historical Intelligence (CURRENT)
**Goal:** Transition from a rule-based script to a predictive "Truth Engine" by training on historical data.
- [ ] **Historical Data Scraper**: Build a utility to download 1 year of 1-minute historical candlestick data for MES and MNQ directly from the IBKR API.
- [ ] **Signal Classifier (ML Filter)**: Use scikit-learn to train a model that assigns a "Success Probability" to every signal based on time, volatility, and Nasdaq correlation.
- [ ] **Backtesting "Time Machine"**: Create a simulation script to run the Midas Logic against historical data to verify PnL before risking real capital.
- [ ] **Intelligence Integration**: Update logic.py to allow the ML model to "Veto" any trade where the historical success probability is below 60%.

---

## 🟣 Sprint 9: Real-Time Sync & Live Controls
**Goal**: Connect the dashboard to your actual financial data and enable "One-Click" mode switching.
- [ ] **Live Balance & PnL Sync**: Update paper_futures.py to pull your actual Net Liquidation Value and 24-hour PnL directly from your Interactive Brokers account.
- [ ] **The "Master Switch"**: Add a toggle on the dashboard to switch between "Paper" and "Live" modes without manually editing config.py.
- [ ] **Performance Audit HUD**: Add a visual "Daily Scorecard" specifically tracking wins, losses, and profit for the current 24-hour window.
- [ ] **Execution Logger**: Expand the dashboard to show the last 10 trades with specific details on why they were closed (e.g., Hit Take Profit vs. Stop Loss).
- [ ] **Account-Aware Position Sizing**: Logic that checks your actual IBKR balance. If you have $50, it strictly buys 1 contract; as your balance grows, it scales up automatically.

---

## 🟣 Sprint 10: The "Midas" Terminal Overhaul
**Goal**: Transform the current "mad ugly" interface into a professional, high-fidelity trading desk.
- [ ] **Dark Mode Cyber-Aesthetic**: Redesign the UI with a sleek, dark "Cybersecurity" theme that matches your Shrood branding.
- [ ] **Interactive Equity Curve**: Integrate Chart.js to plot a live line graph of your account balance growth over time.
- [ ] **Correlation Heatmap**: Add a visual "Sync Meter" showing exactly how closely the S&P and Nasdaq have been correlated over the last hour.