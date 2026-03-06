# Project Midas: Strategy & Logic

## 1. Primary Strategy: Order Flow Anomaly Detection
The core strategy relies on reading Level 2 Market Depth to find "Iceberg" orders—disproportionately large limit orders placed by institutional algorithms designed to absorb selling/buying pressure without moving the price.

### Current Detection Parameters (Phase 1)
* **Trigger:** Any single Bid or Ask size in the top 5 levels of the order book that exceeds the normal distribution of retail sizing.
* **Current Threshold:** > `0.5 BTC` (Adjustable in `core/logic.py`).
* **Position Sizing:** Fixed execution of `0.1 BTC` per approved signal to prevent matching institutional sizes with retail capital.

## 2. Risk Management & Execution
* **Cooldown (Anti-Spam):** A hard-coded 300-second (5-minute) blackout period following any executed trade. The bot will ignore all new Icebergs during this time to prevent over-exposure.
* **Take Profit (TP):** *(Pending Implementation)* Fixed exit at `+$50.00` unrealized profit.
* **Stop Loss (SL):** *(Pending Implementation)* Fixed exit at `-$20.00` unrealized loss.

## 3. The Hybrid ML Evolution (Future Scope)
The current static thresholds will eventually be augmented by a Machine Learning confirmation layer.
* **Data Collection:** Every triggered signal, along with macro indicators at that timestamp, is logged.
* **Model:** A Random Forest Classifier trained on the logged diary to predict the win probability of newly detected Icebergs.
* **Execution:** `IF Iceberg > 0.5 BTC AND ML_Confidence > 75% -> Push to Approval Queue.`