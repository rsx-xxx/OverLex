#!/bin/bash
set -e
cd "$(dirname "$0")"

EXCLUDE_MODS=(
  PyQt5.QtWebEngine PyQt5.QtWebEngineWidgets PyQt5.QtWebEngineCore
  PyQt5.QtSql PyQt5.QtMultimedia PyQt5.QtDesigner PyQt5.QtHelp
  PyQt5.QtTest PyQt5.QtXml PyQt5.Qt3DCore PyQt5.QtBluetooth
  PyQt5.QtOpenGL PyQt5.QtSensors PyQt5.QtSerialPort
)

EXCL_FLAGS=""
for m in "${EXCLUDE_MODS[@]}"; do
  EXCL_FLAGS="$EXCL_FLAGS --exclude-module $m"
done

pip install pyinstaller -q

pyinstaller --onedir --noconsole --name OverLex --noconfirm \
  --collect-all PIL --collect-all mss \
  --collect-all pynput --collect-all PyQt5 \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  $EXCL_FLAGS \
  overlex.py

hdiutil create -volname "OverLex" \
  -srcfolder "dist/OverLex" \
  -ov -format UDZO \
  "dist/OverLex.dmg"

SIZE=$(du -sh dist/OverLex.dmg | cut -f1)
echo "[OK] dist/OverLex.dmg ($SIZE)"
