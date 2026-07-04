import pydivert

filters = [
    "tcp.DstAddr == 57.129.113.60 and tcp.DstPort == 5557",
    "tcp.DstAddr == 57.129.113.60 and tcp.DstPort == 5557 and tcp.SrcPort != 61234",
    "tcp.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557",
    "(tcp.DstAddr == 57.129.113.60 and tcp.DstPort == 5557) or (tcp.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557)",
]

for f in filters:
    try:
        with pydivert.WinDivert(f) as d:
            print(f"OK: {f[:60]}...")
    except Exception as e:
        print(f"FAIL: {f[:60]}... -> {e}")

print("Done")
