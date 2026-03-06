# Project Midas: Internal API Routes

This documents the Flask endpoints used by the frontend JavaScript to communicate with the Python backend.

## GET `/status`
* **Purpose:** The main polling endpoint. The dashboard calls this every 1000ms.
* **Returns (JSON):**
  * `active` (boolean): Is the background engine currently running?
  * `price` (float/string): Latest asset price.
  * `balance` (float): Current wallet balance (real or paper).
  * `symbol` (string): Active trading pair (e.g., 'BTC/USDT').
  * `market_depth` (dict): Top Bids and Asks arrays.
  * `pending_signals` (list): Array of active anomaly dictionaries waiting for approval.

## GET `/start_bot` | `/stop_bot`
* **Purpose:** Hardware-level control to spawn or kill the `core.engine` background thread.
* **Returns:** HTTP 302 Redirect to `/` (Home).

## POST `/approve_signal/<signal_id>`
* **Purpose:** Instructs the active Adapter to execute a market order based on the signal's parameters.
* **Returns (JSON):** `{'status': 'success/error', 'message': '...'}`. 
* **Side Effect:** Removes the signal from `pending_signals` and pushes it to Trade History.

## POST `/reject_signal/<signal_id>`
* **Purpose:** Dismisses a false-positive signal without executing a trade.
* **Returns (JSON):** `{'status': 'success', 'message': '...'}`.
* **Side Effect:** Clears the signal from the queue to declutter the UI.