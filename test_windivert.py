import pydivert
import sys

# Test 1: Simple true filter
try:
    d = pydivert.WinDivert("true")
    print("Test 1 OK: 'true' filter works")
    d.close()
except Exception as e:
    print(f"Test 1 FAIL: {e}")

# Test 2: TCP filter
try:
    d = pydivert.WinDivert("tcp")
    print("Test 2 OK: 'tcp' filter works")
    d.close()
except Exception as e:
    print(f"Test 2 FAIL: {e}")

# Test 3: Our specific filter
try:
    f = "(tcp.DstAddr == 57.129.113.60 and tcp.DstPort == 5557 and tcp.SrcPort != 61234) or (tcp.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557)"
    d = pydivert.WinDivert(f)
    print(f"Test 3 OK: complex filter works")
    d.close()
except Exception as e:
    print(f"Test 3 FAIL: {e}")

input("Press Enter...")
