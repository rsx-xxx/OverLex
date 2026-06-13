#!/bin/bash
set -e
cd "$(dirname "$0")"

pip install pyinstaller -q

pyinstaller --onedir --noconsole --name OverLex --noconfirm \
  --collect-all PIL --collect-all mss --collect-all pynput \
  --collect-all requests --collect-all PyQt5 \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  overlex.py

# Создаём DMG
APP="dist/OverLex/OverLex"
if [ -d "$APP.app" ]; then APP="$APP.app"; fi

hdiutil create -volname "OverLex" \
  -srcfolder "dist/OverLex" \
  -ov -format UDZO \
  "dist/OverLex.dmg"

echo "[OK] dist/OverLex.dmg"
