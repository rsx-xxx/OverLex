"""python build.py"""
import sys, subprocess, importlib, os
from pathlib import Path

COLLECT_ALL = ["PIL","mss","pynput","requests","PyQt5","winsdk"]
HIDDEN = [
    "pynput.keyboard._win32","pynput.mouse._win32",
    "pynput.keyboard._base","pynput.mouse._base",
    "winreg", "asyncio",
    "winsdk.windows.media.ocr",
    "winsdk.windows.graphics.imaging",
    "winsdk.windows.storage.streams",
]

flags = []
for p in COLLECT_ALL: flags += ["--collect-all", p]
for h in HIDDEN:      flags += ["--hidden-import", h]

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir", "--noconsole", "--name", "TranslAura", "--noconfirm",
    *flags,
    "transloverlay.py",
]
print("[build] запуск PyInstaller…")
r = subprocess.run(cmd, cwd=Path(__file__).parent)
print("\n[OK] dist/TranslAura/TranslAura.exe" if r.returncode==0 else "\n[!] Ошибка")
