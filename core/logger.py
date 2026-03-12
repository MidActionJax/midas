import csv
import os
import shutil
from tempfile import NamedTemporaryFile
import time

# Define the absolute path for the CSV file to ensure it's created in the project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CSV_FILE = os.path.join(PROJECT_ROOT, 'trade_history.csv')

CSV_HEADER = [
    'timestamp_id', 'symbol', 'type', 'price', 'size',
    'ema_200_val', 'trend_dir', 'atr_volatility', 'session_context', 'whale_strength',
    'ml_confidence', 'user_decision', 'final_pnl', 'outcome_label', 'exit_reason'
]

def log_signal(signal_data, context_data, status):
    """
    Logs the trading signal data, context, and status to a CSV file.
    It now uses the timestamp from the signal_data.
    """
    file_exists = os.path.isfile(CSV_FILE)

    # Use timestamp from the signal data, ensuring consistency.
    timestamp_id = signal_data.get('timestamp')
    if timestamp_id is None:
        timestamp_id = round(time.time(), 4) # Fallback, though should always be provided.

    row_data = {
        'timestamp_id': timestamp_id,
        'symbol': signal_data.get('symbol'),
        'type': signal_data.get('type'),
        'price': signal_data.get('price'),
        'size': signal_data.get('size'),
        'ema_200_val': context_data.get('ema_200'),
        'trend_dir': context_data.get('trend'),
        'atr_volatility': context_data.get('atr'),
        'session_context': context_data.get('session_context'),
        'whale_strength': context_data.get('whale_strength'),
        'ml_confidence': signal_data.get('confidence'),
        'user_decision': status,
        'final_pnl': '',
        'outcome_label': '',
        'exit_reason': ''
    }

    try:
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if not file_exists or os.path.getsize(CSV_FILE) == 0:
                writer.writeheader()
            writer.writerow(row_data)
    except IOError as e:
        print(f"Error writing to CSV file {CSV_FILE}: {e}")

def update_user_decision(timestamp_id, decision):
    """
    Finds a signal by its timestamp_id in the CSV and updates the user_decision.
    Includes a retry loop to handle potential race conditions with file writing.
    """
    if not os.path.isfile(CSV_FILE):
        print(f"Error: CSV file not found at {CSV_FILE}")
        return

    for attempt in range(3):
        found = False
        tempfile = NamedTemporaryFile(mode='w', delete=False, newline='', encoding='utf-8')
        try:
            with open(CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile, tempfile:
                reader = csv.DictReader(csvfile)
                writer = csv.DictWriter(tempfile, fieldnames=CSV_HEADER)
                writer.writeheader()
                
                for row in reader:
                    # 1. Use .get() to avoid KeyError if the column is named wrong
                    csv_id = row.get('timestamp_id') or row.get('timestamp')
                    
                    if csv_id:
                        try:
                            # 2. Force both to strings of the same precision for a perfect match
                            if str(round(float(csv_id), 4)) == str(round(float(timestamp_id), 4)):
                                row['user_decision'] = decision.upper()
                                found = True
                                print(f"--- MATCH FOUND: {csv_id} updated to {decision} ---")
                        except ValueError:
                            pass # Skip rows with non-numeric IDs
                    
                    # 3. Clean the row before writing (strips out 'action', 'reason', etc.)
                    filtered_row = {k: v for k, v in row.items() if k in CSV_HEADER}
                    writer.writerow(filtered_row)
            
            if found:
                shutil.move(tempfile.name, CSV_FILE)
                return  # Successfully updated, exit function

        except FileNotFoundError:
             # This can happen if the file is created between the os.path.isfile check and the open() call
            print(f"Attempt {attempt + 1}: CSV file not found, retrying...")
        except Exception as e:
            print(f"An error occurred during CSV update on attempt {attempt + 1}: {e}")
        finally:
            # Ensure tempfile is always removed if it still exists
            if os.path.exists(tempfile.name):
                os.remove(tempfile.name)

        if found:
            return # Should have already exited, but as a safeguard

        # If not found, wait before retrying
        time.sleep(0.1)

    # This message is now printed only after all retries have failed
    print(f"Warning: Signal with timestamp_id {timestamp_id} not found for update after multiple attempts.")

def update_outcome(timestamp_id, pnl):
    """
    Finds a signal by its timestamp_id and updates the trade outcome.
    Includes a retry loop to handle potential race conditions with file writing.
    """
    if not os.path.isfile(CSV_FILE):
        print(f"Error: CSV file not found at {CSV_FILE}")
        return

    for attempt in range(3):
        found = False
        tempfile = NamedTemporaryFile(mode='w', delete=False, newline='', encoding='utf-8')
        try:
            with open(CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile, tempfile:
                reader = csv.DictReader(csvfile)
                writer = csv.DictWriter(tempfile, fieldnames=CSV_HEADER)
                writer.writeheader()

                for row in reader:
                    print(f"DEBUG: Checking CSV ID {row['timestamp_id']} against target {timestamp_id}")
                    try:
                        if str(round(float(row['timestamp_id']), 4)) == str(round(float(timestamp_id), 4)):
                            row['final_pnl'] = pnl
                            row['outcome_label'] = 1 if pnl > 0 else 0
                            found = True
                    except (ValueError, KeyError):
                        pass
                    
                    filtered_row = {k: v for k, v in row.items() if k in CSV_HEADER}
                    writer.writerow(filtered_row)
            
            if found:
                shutil.move(tempfile.name, CSV_FILE)
                return # Successfully updated, exit function

        except FileNotFoundError:
            print(f"Attempt {attempt + 1}: CSV file not found, retrying...")
        except Exception as e:
            print(f"An error occurred during CSV outcome update on attempt {attempt + 1}: {e}")
        finally:
            if os.path.exists(tempfile.name):
                os.remove(tempfile.name)
        
        if found:
            return

        time.sleep(0.1)

    print(f"Warning: Signal with timestamp_id {timestamp_id} not found for outcome update after multiple attempts.")

def log_trade_exit(timestamp_id, pnl, reason):
    """
    Finds a trade by its signal timestamp_id and updates its exit information.
    """
    if not os.path.isfile(CSV_FILE):
        print(f"Error: CSV file not found at {CSV_FILE}")
        return

    for attempt in range(3):
        found = False
        tempfile = NamedTemporaryFile(mode='w', delete=False, newline='', encoding='utf-8')
        try:
            with open(CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile, tempfile:
                reader = csv.DictReader(csvfile)
                # Ensure all fields are covered, even if some are empty
                writer = csv.DictWriter(tempfile, fieldnames=CSV_HEADER, extrasaction='ignore')
                writer.writeheader()

                for row in reader:
                    try:
                        # Match by comparing float representations to handle precision issues
                        if 'timestamp_id' in row and row['timestamp_id'] and str(round(float(row['timestamp_id']), 4)) == str(round(float(timestamp_id), 4)):
                            row['final_pnl'] = pnl
                            row['outcome_label'] = 'WIN' if pnl > 0 else 'LOSS'
                            row['exit_reason'] = reason
                            found = True
                    except (ValueError, TypeError):
                        pass # Ignore rows where timestamp_id is not a valid float

                    writer.writerow(row)
            
            if found:
                shutil.move(tempfile.name, CSV_FILE)
                print(f"--- EXIT LOGGED: ID={timestamp_id}, PnL={pnl}, Reason={reason} ---")
                return

        except FileNotFoundError:
            print(f"Attempt {attempt + 1}: CSV file not found during exit logging, retrying...")
        except Exception as e:
            print(f"An error occurred during log_trade_exit on attempt {attempt + 1}: {e}")
        finally:
            if os.path.exists(tempfile.name):
                os.remove(tempfile.name)
        
        if found:
            return

        time.sleep(0.1)

    print(f"Warning: Signal with timestamp_id {timestamp_id} not found for exit logging after multiple attempts.")
