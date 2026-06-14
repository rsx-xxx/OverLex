"""python build_win.py"""
import sys, subprocess
from pathlib import Path

# Unused Qt modules - removing these cuts bundle size by ~40%
EXCLUDE = [
    "PyQt5.QtWebEngine", "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore",
    "PyQt5.QtSql", "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtLocation",
    "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtTest",
    "PyQt5.QtXml", "PyQt5.QtXmlPatterns", "PyQt5.Qt3DCore",
    "PyQt5.Qt3DRender", "PyQt5.Qt3DInput", "PyQt5.Qt3DAnimation",
    "PyQt5.QtBluetooth", "PyQt5.QtPositioning", "PyQt5.QtSensors",
    "PyQt5.QtSerialPort", "PyQt5.QtOpenGL",
]
COLLECT = ["PIL","mss","pynput","PyQt5"]
HIDDEN  = [
    "pynput.keyboard._win32","pynput.mouse._win32",
    "pynput.keyboard._base","pynput.mouse._base","winreg",
]

flags = []
for p in COLLECT:  flags += ["--collect-all", p]
for h in HIDDEN:   flags += ["--hidden-import", h]
for e in EXCLUDE:  flags += ["--exclude-module", e]

ps = Path(__file__).parent / "_ocr_helper.ps1"
if ps.exists(): flags += ["--add-data", f"{ps};."]

cmd = [sys.executable, "-m", "PyInstaller",
       "--onedir", "--noconsole", "--name", "OverLex", "--noconfirm",
       *flags, "overlex.py"]

print(f"[build] PyInstaller with {len(EXCLUDE)} excluded Qt modules...")
r = subprocess.run(cmd, cwd=Path(__file__).parent)
if r.returncode == 0:
    # Estimate size
    import shutil
    size = sum(f.stat().st_size for f in Path("dist/OverLex").rglob("*") if f.is_file())
    print(f"\n[OK] dist/OverLex/OverLex.exe  ({size//1024//1024} MB)")
else:
    sys.exit(r.returncode)
