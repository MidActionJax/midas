# Project Midas: Product Scope & Vision Proposal

## 1. Executive Summary
**Project Midas** is a web-based, "Grey Box" Order Flow Trading Terminal. Unlike traditional "black box" trading bots that execute trades blindly, Midas acts as a highly intelligent co-pilot. It scans Level 2 Market Depth at superhuman speeds to detect institutional manipulation—specifically "Iceberg" orders. When it finds a high-probability setup, it prompts the human operator for final execution approval.

## 2. Core Philosophy: The Hybrid "Grey Box" Model
* **The Bot's Job:** Stare at split-second data, calculate order flow anomalies, filter out market noise, and manage open positions (auto-selling for profit/loss).
* **The Human's Job:** Provide the final "sanity check" and click **[APPROVE]** or **[REJECT]** based on the bot's alerts and macro market conditions.
* **The Ultimate Goal:** Transition from a pure rule-based detector to a **Hybrid Machine Learning System**. The bot will learn from human approvals, rejections, and trade outcomes to predict a setup's probability of success before issuing an alert.

## 3. UI/UX Scope
The interface is a professional, dark-mode terminal featuring:
1. **Command Header:** Live status, real-time asset pricing, and a Realized PnL (Profit & Loss) scoreboard.
2. **Environment Selector:** A dropdown to switch between simulation (Paper) and live combat modes across Crypto and Traditional Futures markets.
3. **Approval Queue:** The central hub where AI-generated signal cards await human confirmation.
4. **X-Ray Vision Tables:** Live Bid/Ask depth charts to visually validate institutional volume.

## 4. Functional Scope: The Daily Workflow
1. **Initialization:** The user sets the environment and activates the engine.
2. **Detection:** The background thread processes WebSockets/API feeds to find volume anomalies.
3. **Verification:** A signal is pushed to the UI; the human operator confirms the structural setup.
4. **Execution & Management:** Upon human approval, the bot enters the market and instantly assumes position management, applying hard-coded Stop-Loss and Take-Profit logic to exit the trade autonomously.

## 5. Future Roadmap: The Machine Learning Co-Pilot
* **Phase 1: The Diary:** Midas logs every generated signal, human decision, and eventual trade outcome (Win/Loss) into a structured dataset.
* **Phase 2: The ML Filter:** A Machine Learning classifier (e.g., Random Forest) will analyze this historical diary to assign an **"ML Confidence Score"** to future signals.
* **Phase 3: Autonomous Rejection:** Signals failing to meet a minimum ML Confidence threshold will be silently discarded, drastically reducing false positives and operator fatigue.

## 6. Out of Scope
* Fully automated, unattended "Black Box" entry execution.
* Custom, built-in charting and drawing tools (reliance remains on raw data tables and standard broker integrations).