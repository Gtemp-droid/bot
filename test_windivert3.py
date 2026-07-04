import pydivert

print("Testing WinDivert context manager...")
try:
    with pydivert.WinDivert("true") as divert:
        print("Handle opened OK")
        # Just receive a single packet with timeout
        import select
        print("WinDivert ready!")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print("Done")
