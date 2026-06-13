# PyInstaller runtime hook для onnxruntime
# Запускается ДО любых import в замороженном exe
import os, sys

if hasattr(sys, '_MEIPASS'):
    mp = sys._MEIPASS
    dirs = [
        mp,
        os.path.join(mp, 'onnxruntime', 'capi'),
        os.path.join(mp, 'numpy', '.libs'),
    ]
    for d in dirs:
        if os.path.isdir(d):
            try: os.add_dll_directory(d)
            except: pass
    os.environ['PATH'] = mp + os.pathsep + os.environ.get('PATH', '')
