import socket

def check_bridge(port=36973):
    print(f"📡 Checking MidasBridge on port {port}...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(('127.0.0.1', port))
            print("✅ SUCCESS: Python is talking to NinjaTrader!")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print("Tip: Make sure 'AT Interface' is enabled in NT8 Settings.")

if __name__ == "__main__":
    check_bridge()