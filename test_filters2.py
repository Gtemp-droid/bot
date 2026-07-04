import pydivert

filters = [
    "ip.DstAddr == 57.129.113.60 and tcp.DstPort == 5557",
    "ip.DstAddr == 57.129.113.60 and tcp.DstPort == 5557 and tcp.SrcPort != 61234",
    "ip.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557",
    "(ip.DstAddr == 57.129.113.60 and tcp.DstPort == 5557 and tcp.SrcPort != 61234) or (ip.SrcAddr == 127.0.0.1 and tcp.SrcPort == 5557)",
]

for f in filters:
    try:
        with pydivert.WinDivert(f) as d:
            print(f"OK: {f[:70]}")
    except Exception as e:
        print(f"FAIL: {f[:70]} -> {e}")

print("Done")
