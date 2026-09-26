# OverLex

Instant on-screen EN→RU translation. Point at a word, or drag over a sentence — works over
games, browsers, any application, no copy-paste needed.

## Download

| Platform | Link |
|---|---|
| Windows 10/11 | [OverLex-Setup.exe](../../releases/latest) |
| macOS 12+ (Apple Silicon) | [OverLex.dmg](../../releases/latest) |

The installer isn't code-signed (that costs money this hobby project doesn't spend), so Windows
SmartScreen and macOS Gatekeeper will warn on first run — click through (**More info → Run
anyway** / **Open Anyway** in System Settings → Privacy & Security). Verify the download against
the release's `SHA256SUMS.txt` if you want assurance it wasn't tampered with.

## Usage

| Action | Result |
|---|---|
| **Windows:** `Ctrl` + Middle Click a word | Translate that word |
| **macOS:** `Option` + Click a word | Translate that word |
| **macOS:** `Ctrl` + `Option` + `Space` | Translate the word under the cursor, no click needed |
| Same click, but **hold and drag** before releasing | Select a region — translates everything inside it as one sentence |
| `Esc` while dragging | Cancel the selection |
| Click the popup | Dismiss it |
| Tray icon | Pause, launch-at-login, or quit |

If a translation ever just shows the original text back unchanged, check `overlex.log`
(`%LOCALAPPDATA%\OverLex\` on Windows, `~/Library/Application Support/OverLex/` on macOS) — it
logs exactly which translation attempt failed and why.

## Building from source

```bash
pip install -r requirements.txt
python overlex.py          # run
build_win.bat               # or: bash build_mac.sh — produces the installer/DMG
```

macOS needs Xcode Command Line Tools (`xcode-select --install`) and Accessibility permission
(System Settings → Privacy & Security → Accessibility). Build/CI details, the Inno Setup script,
and macOS notarization secrets are in `installer/`, `.github/workflows/release.yml`, and
`build_mac.sh` respectively.

## License

Public domain — do whatever you want with it, no warranty. See [LICENSE](LICENSE) (Unlicense).
