# OverLex

**Windows:** `Ctrl + Middle Click`; **macOS:** `Option + Click` or `Ctrl + Option + Space` — instant on-screen EN→RU translation.

Works over games, browsers, any application.

## Download

| Platform | Link |
|---|---|
| Windows 10/11 | [OverLex-Windows.zip](../../releases/latest) |
| macOS 12+ (Apple Silicon) | [OverLex.dmg](../../releases/latest) |

Each release also publishes `SHA256SUMS.txt` — verify a downloaded file against it before running.

## Usage

| Action | Result |
|---|---|
| Windows: `Ctrl` + Middle Click | Translate the word under the cursor |
| macOS: `Option` + Click | Translate the word under the cursor (trackpad) |
| macOS: `Ctrl` + `Option` + `Space` | Translate the word at the current cursor position without clicking |
| Click on the overlay | Dismiss it |
| 5 seconds | Auto-hide |
| Tray icon | Pause / Launch at login / Quit |

## Install from source

```bash
pip install -r requirements.txt
python overlex.py
```

**Windows:** PowerShell is built in, nothing else needed.
**macOS from source:** requires Xcode Command Line Tools (`xcode-select --install`) to compile the Swift OCR helper.
**macOS:** add OverLex under System Settings → Privacy & Security → Accessibility.

## Build

**Windows:**
```bat
build_win.bat
```

**macOS:**
```bash
bash build_mac.sh
```

Both scripts embed an app icon and version metadata (set `OVERLEX_VERSION=1.2.3` to stamp a version;
the release workflow sets it from the pushed git tag automatically).

## Windows SmartScreen

The Windows build is not code-signed (no EV certificate) — SmartScreen may show "Windows protected
your PC" on first run. Click **More info → Run anyway**. Verify the download against
`SHA256SUMS.txt` in the release if you want extra assurance the file wasn't tampered with.

## macOS release signing

A DMG from GitHub Releases should be signed with a Developer ID certificate and notarized by Apple,
otherwise Gatekeeper may block it even after "Open Anyway".

For a notarized release, add these GitHub repository secrets:

| Secret | Value |
|---|---|
| `MACOS_CERTIFICATE_BASE64` | base64 of a `.p12` containing a `Developer ID Application` certificate |
| `MACOS_CERTIFICATE_PASSWORD` | password for the `.p12` |
| `MACOS_CODESIGN_IDENTITY` | optional, e.g. `Developer ID Application: ...` |
| `MACOS_KEYCHAIN_PASSWORD` | any temporary password for the CI keychain |
| `APPLE_ID` | Apple Developer account Apple ID |
| `APPLE_TEAM_ID` | Team ID from Apple Developer |
| `APPLE_APP_PASSWORD` | app-specific password for notarization |

Without these secrets, `build_mac.sh` produces an ad-hoc signature only. That's fine for local
testing, but doesn't fully resolve Gatekeeper blocking for users who downloaded the file from GitHub.
