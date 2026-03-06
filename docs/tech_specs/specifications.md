# Project Midas Technical Specification

This is a comprehensive technical specification for the "Grey Box" Order Flow Trading System. We are building a Multi-Threaded Flask Application. This means the website (Flask) runs on one processor track to handle your clicks, while the Bot (The Engine) runs on a parallel track to watch the market 24/7 without freezing the website. Here is the blueprint for every single component.

## 1. The High-Level Architecture

Think of this like a car.
* **The Chassis:** Python (holds everything together).
* **The Engine:** The Background Thread (calculates logic).
* **The Transmission:** The "Adapter System" (switches between Paper/Live/Crypto/Futures).
* **The Dashboard:** Flask/HTML (the steering wheel and speedometer).

---

## 2. The Tech Stack (Inventory)

| Component | Tool | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Flask | Lightweight web server to host the UI. |
| **Database** | SQLite (initially) | A simple file-based database to store trade history and pending signals. No server setup required. |
| **Concurrency** | Python threading | Allows the bot to loop infinitely in the background while the website stays responsive. |
| **Crypto Data** | ccxt | Connects to Binance/Bybit for Bitcoin data. |
| **Futures Data** | ib_insync | Connects to Interactive Brokers for S&P 500 data. |
| **Frontend Styling** | Bootstrap 5 | Pre-made CSS so the dashboard looks professional (dark mode) without writing custom CSS. |
| **Real-time UI** | AJAX / JavaScript | Updates the price and logs on the screen without refreshing the page. |

---

## 3. The Backend Infrastructure

The project will be structured into modular "Blocks."

### A. The Folder Structure
We will organize the files so you never get lost.

```text
/trading_bot_project
│
├── app.py                   # The Web Server (Flask Main)
├── config.py                # Settings (API Keys, Risk Limits)
├── database.db              # The Memory (Trade History)
│
├── /core
│   ├── engine.py            # The Background Loop (The "Brain")
│   ├── order_flow.py        # Math logic (Calculates "Icebergs")
│   └── state_manager.py     # Shared variables between Web & Bot
│
├── /adapters                # The "Universal Plugs"
│   ├── base.py              # The Template
│   ├── paper_crypto.py      # Fake Bitcoin Trading
│   ├── live_crypto.py       # Real Bitcoin Trading
│   └── paper_futures.py     # Fake S&P 500 Trading
│
├── /templates               # The HTML UI
│   ├── dashboard.html       # The Cockpit
│   └── layout.html          # Header/Footer
│
└── /static                  # CSS/JS
    ├── styles.css
    └── updater.js           # JavaScript to refresh data
```

### B. The "Adapter Pattern" Logic 
This is how we achieve the versatility you asked for. The Engine (`core/engine.py`) will never know if it is trading real money or fake money. It just sends commands. 

* **The Interface:** `buy(symbol, amount)` 
* **If Mode = Paper:** The adapter writes to a text file log and updates a fake balance variable. 
* **If Mode = Live:** The adapter signs an API request and sends it to the broker. 

---

## 4. The User Interface (UI) Elements 
The Dashboard will be a Single Page Application (SPA) feel. It doesn't reload; it just updates. 

### Zone 1: The Header (Status Bar) 
* **Connection Status:** A glowing Green Dot if the WebSocket is alive. Red if disconnected. 
* **Account Balance:** Shows current Equity (e.g., "$10,540.00"). 
* **Active Mode:** Large text displaying: `PAPER TRADING - BITCOIN` or `LIVE - S&P 500`. 

### Zone 2: The Control Panel (Top Left) 
* **Mode Dropdown:** A standard dropdown menu: 
    * *Select Mode:* * Paper: Crypto (Testnet) 
    * Live: Crypto (Binance) 
    * Paper: Futures (IBKR) 
* **Master Buttons:** * **[ START ENGINE ]** (Green): Launches the background thread. 
    * **[ KILL SWITCH ]** (Red): Immediately stops all loops and cancels open orders. 

### Zone 3: The "Approval Queue" (The Grey Box) 
This is the most important part for you. When the bot detects a bank algorithm, it doesn't buy automatically. It pushes a card to this zone. 

* **The Card:** A box appears saying: 
    > Signal Detected: ICEBERG BUY 
    > Price: $98,500 
    > Confidence: 85% 
* **The Buttons:** * **[ APPROVE ]** -> Sends signal to Adapter -> Executes Trade. 
    * **[ REJECT ]** -> Deletes signal -> Logs "User Rejected". 

### Zone 4: The Visuals (Right Side) 
* **Chart:** An embedded TradingView Widget. It's free, looks pro, and handles the charting for us so we don't have to code it. 
* **Live Log:** A "Terminal" style box that scrolls automatically: 
    ```text
    10:00:01 - Engine Started. 
    10:00:05 - Connected to Binance. 
    10:01:20 - Scanning for Order Flow... 
    ```

---

## 5. The Logic Flow (Step-by-Step Scenario) 
Here is exactly what happens inside the code when you sit down to trade. 

1.  **Initialization:** * You run `python app.py`. 
    * Flask starts. You open `localhost:5000`. 
    * You select "Paper: Crypto" from the dropdown. 
2.  **Activation:** * You click **[ START ENGINE ]**. 
    * Flask fires up a generic Python Thread. 
    * The Thread loads the PaperAdapter. 
3.  **The Loop (The "Brain"):** * The bot connects to the data feed. 
    * It calculates the "Delta" (Buyers vs Sellers). 
    * *Event:* It sees 500 BTC bought at market, but price doesn't move up. 
    * *Logic:* `if delta > 500 and price_change == 0: trigger_signal()` 
4.  **The Hand-off:** * The bot adds the signal to the `GlobalState` dictionary. 
    * The JavaScript on your browser (running every 1 second) asks Flask: "Any new signals?" 
    * Flask says "Yes!" and the Approval Card pops up on your screen. 
5.  **Execution:** * You click **[ APPROVE ]**. 
    * Flask calls `adapter.buy()`. 
    * The Adapter simulates the fill. 
    * The Balance updates on the header.