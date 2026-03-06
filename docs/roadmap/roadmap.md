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

## 🟡 Sprint 3: Traditional Markets (The S&P 500) (CURRENT)
**Goal:** Expand the bot's reach beyond Crypto into traditional futures.
- [ ] **Interactive Brokers Integration:** Install and configure `ib_insync`.
- [ ] **The Futures Adapter:** Build `paper_futures.py` and `live_futures.py` to match the existing Adapter interface.
- [ ] **Data Normalization:** Ensure the S&P 500 E-mini (ES) order book data formats correctly into the existing UI tables.
- [ ] **Contract Rollover Logic:** Add logic to handle futures contract expirations (e.g., switching from the March contract to the June contract).

---

## ⚪ Sprint 4: Advanced Strategy & Risk Filters
**Goal:** Make the bot highly selective about which Icebergs it shows you.
- [ ] **Dynamic Sizing:** Stop using a fixed `0.1 BTC` size. Calculate position size based on account percentage and current market volatility (ATR).
- [ ] **Trend Filtering:** Integrate basic moving averages. Rule: *Only show BUY signals if the price is above the 200 EMA.*
- [ ] **The "Kill Switch":** Implement a Max Daily Drawdown rule. If the bot loses $500 in a day, it auto-locks the dashboard and refuses to trade until tomorrow.

---

## ⚪ Sprint 5: Data Harvesting & Machine Learning Prep
**Goal:** Prepare the system for Artificial Intelligence.
- [ ] **Feature Engineering:** Expand the CSV logger to capture "context" (e.g., What time of day was it? Was the overall market trending up or down?).
- [ ] **Data Pipeline:** Create a script to clean the `history.csv` data and label trades as `1` (Win) or `0` (Loss).
- [ ] **Model Selection:** Set up a local Python ML environment using `scikit-learn` or `XGBoost`.
- [ ] **Initial Training:** Train a baseline classification model on the bot's paper-trading history.

---

## ⚪ Sprint 6: The ML Co-Pilot
**Goal:** Merge the trained ML model with the live trading engine.
- [ ] **Model Inference:** Load the trained ML model into `core/logic.py`.
- [ ] **The Confidence Score:** Whenever an Iceberg is detected, feed current market conditions into the ML model to get a "Probability of Success" score.
- [ ] **UI Update:** Add the `ML Confidence: 85%` badge to the Approval Cards on the dashboard.
- [ ] **Auto-Rejection:** Hardcode the engine to silently discard any signal with an ML Confidence below 60%.

---

## ⚪ Sprint 7: Deployment & Hardening
**Goal:** Move the bot off the local laptop and into a secure, 24/7 cloud environment.
- [ ] **Cloud Hosting:** Deploy the system to a Linux VPS (DigitalOcean/AWS/Google Cloud).
- [ ] **Web Server Config:** Replace the Flask dev server with Gunicorn and Nginx.
- [ ] **Security (Auth):** Add a login screen. The dashboard must be password-protected so no one else can access the URL and click "Approve."
- [ ] **Process Management:** Use `systemd` or `pm2` so the bot automatically restarts if the server crashes.