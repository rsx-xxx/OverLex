import os
import sys
# Принудительно добавляем путь к библиотекам, если они в нестандартном месте
os.add_dll_directory(r"C:\Windows\System32")
try:
    import onnxruntime
    print("Import successful!")
except ImportError as e:
    print(f"Failed: {e}")