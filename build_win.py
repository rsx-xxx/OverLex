"""python build_win.py  — запускать из venv"""
import sys, subprocess, importlib, os
from pathlib import Path

COLLECT = ["PIL","mss","pynput","requests","PyQt5"]
HIDDEN  = ["pynput.keyboard._win32","pynput.mouse._win32",
           "pynput.keyboard._base","pynput.mouse._base","winreg"]

flags = []
for p in COLLECT: flags += ["--collect-all", p]
for h in HIDDEN:  flags += ["--hidden-import", h]

# Включаем PS-скрипт (создаётся при первом запуске overlex.py)
ps = Path(__file__).parent / "_ocr_helper.ps1"
if ps.exists(): flags += ["--add-data", f"{ps};."]

cmd = [sys.executable,"-m","PyInstaller",
       "--onedir","--noconsole","--name","OverLex","--noconfirm",
       *flags,"overlex.py"]
r = subprocess.run(cmd, cwd=Path(__file__).parent)
if r.returncode == 0:
    print("\n[OK] dist/OverLex/OverLex.exe")
else:
    sys.exit(r.returncode)
