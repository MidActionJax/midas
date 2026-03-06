import time

def analyze_order_book(order_book, threshold=0.5):
    """
    Analyzes the order book to find large orders (icebergs).

    Args:
        order_book (dict): The order book data with 'bids' and 'asks'.
        threshold (float): The size threshold to detect a large order.

    Returns:
        dict: A signal dictionary if a large order is found, otherwise None.
    """
    if not order_book:
        return None

    # Check bids for buy signals
    if 'bids' in order_book and order_book['bids']:
        for price, size in order_book['bids']:
            if size > threshold:
                return {
                    'type': 'BUY_SIGNAL',
                    'price': price,
                    'size': size,
                    'reason': 'Iceberg Detected',
                    'timestamp': time.time()
                }

    # Check asks for sell signals
    if 'asks' in order_book and order_book['asks']:
        for price, size in order_book['asks']:
            if size > threshold:
                return {
                    'type': 'SELL_SIGNAL',
                    'price': price,
                    'size': size,
                    'reason': 'Icegerg Detected',
                    'timestamp': time.time()
                }

    return None
