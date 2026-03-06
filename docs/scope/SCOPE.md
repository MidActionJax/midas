# Project Midas: Dashboard UI & Workflow Scope

## 1. The Core Concept: The "Grey Box" Co-Pilot
Project Midas is not a fully automated, blind robot. It is a **"Grey Box" Order Flow Terminal**. 
* **The Strategy:** The system reads the "Tape" (Level 2 Market Depth) to track massive institutional orders. It hunts for "Icebergs"—massive, hidden orders waiting to trap retail traders.
* **The Division of Labor:** The bot does 99% of the heavy lifting (scanning split-second data, running math, detecting patterns). When it finds a setup, it pauses and prompts the human operator for the final execution approval.

## 2. The Dashboard Layout (The "Cockpit")
The web UI is designed as a professional, dark-mode single-page application divided into distinct zones:

### Zone A: The Top Bar (Status Zone)
* **Status LED:** A glowing indicator showing if the engine is scanning (`ONLINE` - Green) or paused (`OFFLINE` - Red).
* **Account Balance:** Currently loaded with $1,000,000 in paper-trading funds.
* **Current Price:** The real-time ticker of the selected asset.

### Zone B: The "Flight Simulator" Switch (Control Panel)
* **Environment Dropdown:** A master switch allowing the user to seamlessly swap environments without changing code (e.g., switching from *Paper Crypto* to *Live S&P 500*).
* **Master Controls:** Large **[START ENGINE]** and **[STOP ENGINE]** execution buttons.

### Zone C: The Commander's Approval Queue
* The interactive heart of the dashboard. When the bot detects an anomaly, a glowing yellow card pops up here.
* **Alert Text:** e.g., *"ICEBERG DETECTED: 2.0 BTC @ $92,000"*.
* **Action Buttons:** Large **[APPROVE]** (fires the trade) and **[REJECT]** (dismisses it) buttons.

### Zone D: X-Ray Vision (Market Depth Tables)

* Two rapidly updating columns tracking the Live Order Book to visually verify the bot's alerts.
* **Left Column (Green):** Bids (Buyers waiting in line).
* **Right Column (Red):** Asks (Sellers waiting in line).

## 3. The Daily Workflow
1. **Boot Up:** Log into the dashboard, select the market, and click **[Start Engine]**.
2. **The Hunt:** Midas silently scans thousands of order book changes per second.
3. **The Alert:** A card pops up in the Approval Queue when an anomaly is caught.
4. **The Decision:** The operator verifies the X-Ray tables and clicks **[APPROVE]**.
5. **The Exit (Auto-Pilot):** Midas takes over, automatically selling when the profit target or stop-loss is hit.

## 4. The "Smart" Evolution (Pending Features)
* **Anti-Spam:** A 5-minute cooldown to prevent signal flooding.
* **Real PnL Tracking:** A "Scoreboard" showing actual realized daily profit.
* **The ML Co-Pilot:** Feeding win/loss history into a Machine Learning model to filter out historically unprofitable setups.