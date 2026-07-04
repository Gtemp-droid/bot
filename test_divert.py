import pydivert
try:
    d = pydivert.WinDivert("true")
    print("WinDivert handle opened OK")
    d.close()
except Exception as e:
    print(f"WinDivert error: {e}")
