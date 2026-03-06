import csv
import os
from datetime import datetime

TRADE_HISTORY_FILE = 'trade_history.csv'
HEADERS = ['timestamp', 'symbol', 'action', 'size', 'price', 'pnl', 'reason']

def log_trade(trade_data: dict):
    """
    Appends a trade record to the trade history CSV file.

    Args:
        trade_data (dict): A dictionary containing the trade details.
                           Must include keys from the HEADERS list.
    """
    file_exists = os.path.isfile(TRADE_HISTORY_FILE)

    with open(TRADE_HISTORY_FILE, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=HEADERS)

        if not file_exists:
            writer.writeheader()

        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow(trade_data)
