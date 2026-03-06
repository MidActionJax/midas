# Project Midas: System Architecture

## 1. Overview
Project Midas is built on a decoupled, Multi-Threaded micro-architecture. It separates the web server (Frontend UI) from the heavy continuous calculations (Backend Engine) to ensure the dashboard never freezes while the bot processes split-second market data.

## 2. The Core Components
The system is divided into four primary domains:

* **The Web Server (`app.py`):** A lightweight Flask application. Its only job is to serve the HTML/JS dashboard and provide API routes for the frontend to click buttons and fetch status updates.
* **The Engine (`core/engine.py`):** An infinite `threading.Thread` background loop. It wakes up every second, fetches the latest Order Book data, runs the mathematical strategy, and generates signals.
* **The State Manager (`core/state.py`):** The "Shared Memory." Because Flask and the Engine run on separate threads, they cannot easily share variables. The State Manager holds the `pending_signals`, `market_depth`, and `realized_pnl` using thread-safe locks so both sides can read/write without corrupting data.
* **The Adapters (`adapters/`):** The execution layer utilizing the Adapter Design Pattern. 

## 3. The Adapter Pattern
To allow seamless switching between simulation and live trading without rewriting the core strategy, all exchange interactions pass through an adapter.
* `TradingAdapter` (Base Interface): Dictates that all adapters MUST have `get_current_price()`, `execute_buy()`, etc.
* `PaperCryptoAdapter`: Uses `ccxt.binanceus()` for real-time data but executes trades against a localized fake balance variable.
* *(Future)* `LiveCryptoAdapter`: Will sign actual API requests to execute with real capital.

## 4. Data Flow (The "Grey Box" Loop)
1. Engine requests Level 2 Data via Adapter.
2. Engine calculates Order Flow and detects an Iceberg.
3. Engine pushes a `BUY_SIGNAL` to the State Manager.
4. Flask Dashboard polls `/status` via AJAX and reads the State Manager.
5. UI renders the Approval Card.
6. User clicks [Approve] -> Flask calls Adapter `execute_buy()`.