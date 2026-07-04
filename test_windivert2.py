import pydivert
import sys

# Test just our specific filter
try:
    f = "(tcp.DstAddr == 57.129.113.60 and tcp.DstPort == 5557 and tcp.SrcPort != 61234) or (tcp.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557)"
    d = pydivert.WinDivert(f)
    print("OK: filter created")
    print("Sending dummy packet...")
    # Don't try to receive, just test creation
    d.close()
    print("OK: closed")
except ImportError as e:
    print(f"ImportError: {e}")
except OSError as e:
    print(f"OSError: {e} ({e.winerror})")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

input("Press Enter...")
