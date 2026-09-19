#!/bin/bash
set -e
cd "$(dirname "$0")"

EXCLUDE_MODS=(
  PySide6.QtWebEngineWidgets PySide6.QtWebEngineCore PySide6.QtWebEngineQuick
  PySide6.QtSql PySide6.QtMultimedia PySide6.QtMultimediaWidgets
  PySide6.QtDesigner PySide6.QtTest PySide6.QtXml PySide6.Qt3DCore
  PySide6.QtBluetooth PySide6.QtOpenGL PySide6.QtOpenGLWidgets
  PySide6.QtSensors PySide6.QtSerialPort PySide6.QtQml PySide6.QtQuick
  PySide6.QtQuickWidgets PySide6.QtPdf PySide6.QtPdfWidgets PySide6.QtCharts
)

EXCL_FLAGS=""
for m in "${EXCLUDE_MODS[@]}"; do
  EXCL_FLAGS="$EXCL_FLAGS --exclude-module $m"
done

HOST_PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$HOST_PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    HOST_PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    HOST_PYTHON_BIN="python"
  else
    echo "[!] python is required"
    exit 1
  fi
fi

cleanup() {
  if [[ -n "${KEYCHAIN_PATH:-}" && -f "$KEYCHAIN_PATH" ]]; then
    security delete-keychain "$KEYCHAIN_PATH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

CODE_SIGN_IDENTITY="${MACOS_CODESIGN_IDENTITY:-}"
if [[ -n "${MACOS_CERTIFICATE_BASE64:-}" ]]; then
  KEYCHAIN_PASSWORD="${MACOS_KEYCHAIN_PASSWORD:-overlex-ci-keychain}"
  CERTIFICATE_PASSWORD="${MACOS_CERTIFICATE_PASSWORD:-}"
  KEYCHAIN_PATH="${RUNNER_TEMP:-/tmp}/overlex-signing.keychain-db"
  CERTIFICATE_PATH="${RUNNER_TEMP:-/tmp}/overlex-signing.p12"

  if ! echo "$MACOS_CERTIFICATE_BASE64" | base64 --decode > "$CERTIFICATE_PATH" 2>/dev/null; then
    echo "$MACOS_CERTIFICATE_BASE64" | base64 -D > "$CERTIFICATE_PATH"
  fi
  security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
  security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
  security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
  security import "$CERTIFICATE_PATH" -P "$CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$KEYCHAIN_PATH"
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
  security list-keychains -d user -s "$KEYCHAIN_PATH" $(security list-keychains -d user | tr -d '"')

  if [[ -z "$CODE_SIGN_IDENTITY" ]]; then
    CODE_SIGN_IDENTITY="$(security find-identity -v -p codesigning "$KEYCHAIN_PATH" | awk -F '"' '/Developer ID Application/ { print $2; exit }')"
  fi
fi

rm -rf build dist
mkdir -p build

BUILD_VENV="${BUILD_VENV:-build/.venv-macos}"
"$HOST_PYTHON_BIN" -m venv "$BUILD_VENV"
PYTHON_BIN="$BUILD_VENV/bin/python"
"$PYTHON_BIN" -m pip install --upgrade pip -q
"$PYTHON_BIN" -m pip install -r requirements.txt pyinstaller -q
swiftc macos_ocr_helper.swift -O -o build/_ocr_helper_bin

ICON_PNG="build/icon_1024.png"
ICONSET="build/OverLex.iconset"
"$PYTHON_BIN" tools/gen_icon.py "$ICON_PNG" 1024
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
  sips -z "$sz" "$sz" "$ICON_PNG" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
  sips -z $((sz*2)) $((sz*2)) "$ICON_PNG" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/icon.icns

OVERLEX_VERSION="${OVERLEX_VERSION:-0.0.0}"
OVERLEX_VERSION="${OVERLEX_VERSION#v}"

"$PYTHON_BIN" -m PyInstaller --onedir --noconsole --name OverLex --noconfirm \
  --icon build/icon.icns \
  --collect-all PIL --collect-all mss \
  --collect-all pynput --collect-all PySide6 \
  --add-binary "build/_ocr_helper_bin:." \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  $EXCL_FLAGS \
  overlex.py

if [[ -d "dist/OverLex.app" ]]; then
  APP_PATH="dist/OverLex.app"
elif [[ -d "dist/OverLex/OverLex.app" ]]; then
  APP_PATH="dist/OverLex/OverLex.app"
else
  echo "[!] PyInstaller did not produce OverLex.app"
  find dist -maxdepth 3 -print
  exit 1
fi

APP_PLIST="$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP_PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$APP_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $OVERLEX_VERSION" "$APP_PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $OVERLEX_VERSION" "$APP_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $OVERLEX_VERSION" "$APP_PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $OVERLEX_VERSION" "$APP_PLIST"

ENTITLEMENTS="build/macos-entitlements.plist"
cat > "$ENTITLEMENTS" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
</dict>
</plist>
PLIST

if [[ -n "$CODE_SIGN_IDENTITY" ]]; then
  echo "[sign] Developer ID: $CODE_SIGN_IDENTITY"
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$CODE_SIGN_IDENTITY" "$APP_PATH"
else
  echo "[sign] ad-hoc signature; GitHub downloads will still require Gatekeeper override"
  CODE_SIGN_IDENTITY="-"
  codesign --force --deep --sign "$CODE_SIGN_IDENTITY" "$APP_PATH"
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"

DMG_ROOT="build/dmg-root"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
cp -R "$APP_PATH" "$DMG_ROOT/OverLex.app"
ln -s /Applications "$DMG_ROOT/Applications"

hdiutil create -volname "OverLex" \
  -srcfolder "$DMG_ROOT" \
  -ov -format UDZO \
  "dist/OverLex.dmg"

if [[ "$CODE_SIGN_IDENTITY" != "-" ]]; then
  codesign --force --timestamp --sign "$CODE_SIGN_IDENTITY" "dist/OverLex.dmg"
  codesign --verify --verbose=2 "dist/OverLex.dmg"
fi

if [[ "$CODE_SIGN_IDENTITY" != "-" && -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
  echo "[notary] submitting dist/OverLex.dmg"
  xcrun notarytool submit "dist/OverLex.dmg" \
    --apple-id "$APPLE_ID" \
    --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --wait
  xcrun stapler staple "dist/OverLex.dmg"
  spctl -a -vvv -t open --context context:primary-signature "dist/OverLex.dmg"
else
  echo "[notary] skipped; set APPLE_ID, APPLE_TEAM_ID and APPLE_APP_PASSWORD to notarize"
fi

shasum -a 256 dist/OverLex.dmg > dist/OverLex.dmg.sha256

SIZE=$(du -sh dist/OverLex.dmg | cut -f1)
echo "[OK] dist/OverLex.dmg ($SIZE)"
