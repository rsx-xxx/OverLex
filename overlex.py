#!/usr/bin/env python3
"""
OverLex - Screen Translation Overlay
Ctrl + Middle Click (Win) / Option + Click (mac) -> instant EN->RU word translation.
Same gesture, but drag before releasing -> select a region, OCR the whole thing,
translate it as one block of text.
Windows: PowerShell / Windows.Media.Ocr
macOS:   Swift / Vision.framework
"""
import os, sys, re, ssl, time, threading, signal, io, platform, tempfile
from pathlib import Path
from collections import OrderedDict
import httpx

import mss
from PIL import Image, ImageEnhance
from pynput import mouse as pmouse, keyboard as pkeyboard

_IS_WIN = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"

_exe_dir = Path(sys.executable if getattr(sys,"frozen",False) else __file__).parent

def _writable_data_dir() -> Path:
    """Log file and the generated Windows OCR helper script need a location the
    process can always write to - a Program Files install only grants that to a
    per-user data dir, not to the install directory itself."""
    if not getattr(sys, "frozen", False):
        return _exe_dir
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) if _IS_WIN \
        else Path.home() / "Library" / "Application Support"
    d = base / "OverLex"
    d.mkdir(parents=True, exist_ok=True)
    return d

_data_dir = _writable_data_dir()
_LOG = open(_data_dir / "overlex.log", "w", buffering=1, encoding="utf-8")
def _log(*a):
    s = " ".join(str(x) for x in a); print(s); _LOG.write(s+"\n")

_log(f"[OverLex] start | {platform.system()} {platform.release()}")

CAPTURE_W, CAPTURE_H = 900, 180
OCR_SCALE  = 2
OCR_UPSCALE_MAX_SIDE = 500  # skip the 2x upscale/enhance pass above this size - already legible, and it's pure wasted CPU on big sentence-mode regions
HIDE_MS    = 5000
SRC, DST   = "en", "ru"
HIT_PAD    = 20
CACHE_MAX  = 500
APP_NAME   = "OverLex"
_TR_URL    = "https://translate.googleapis.com/translate_a/single"
# One keep-alive HTTP/2 connection reused for every translate call instead of a fresh
# TCP+TLS handshake per word - the handshake was the dominant cost for short requests.
# verify= is explicit (not httpx's default) because httpx otherwise trusts only its
# bundled certifi CA list, not the OS certificate store - unlike the old urllib-based
# code, it would silently fail TLS verification behind any TLS-inspecting corporate
# proxy/VPN/antivirus whose root cert Windows already trusts.
_http = httpx.Client(http2=True, timeout=4.0, headers={"User-Agent": "Mozilla/5.0"},
                     verify=ssl.create_default_context())

# == OCR ======================================================================

_PS_BODY = r"""
param([string]$imgPath)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing
$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IBuffer,Windows.Foundation,ContentType=WindowsRuntime]

# PowerShell's own dispatch never gives .NET reflection metadata for a WinRT
# instance-method result (always plain System.__ComObject, zero interfaces) - only
# plain IDispatch-style property/method access works, not generic interface members
# like IAsyncOperation<T>.GetResults(). And Add-Type -TypeDefinition can't reference
# raw .winmd files (its legacy CodeDom compiler doesn't understand metadata-only
# assemblies). So compile with the real Roslyn csc.exe directly - which does support
# .winmd references, same as any classic desktop project calling WinRT APIs - and
# load the resulting DLL, which carries proper static typing throughout.
function Resolve-RefAssembly($simpleName) {
    $loaded = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.GetName().Name -eq $simpleName } | Select-Object -First 1
    if ($loaded) { return $loaded.Location }
    return ([System.Reflection.Assembly]::Load($simpleName)).Location
}
$winmdDir = "$env:WINDIR\System32\WinMetadata"
$mscorlibDll = ([object].Assembly.Location)
$systemRuntimeDll = Resolve-RefAssembly "System.Runtime"
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { $csc = "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe" }

$dllPath = Join-Path $env:TEMP "OverLexOcrHelper.dll"
if (-not (Test-Path $dllPath)) {
    # Poll Status/GetResults directly instead of using AsTask<T>: AsTask comes from
    # System.Runtime.WindowsRuntime.dll, which carries its own embedded definition of
    # Windows.Foundation.IAsyncOperation<T> that doesn't type-match the one resolved
    # from our own explicit Windows.Foundation.winmd reference (needed transitively by
    # Windows.Media.winmd/Windows.Graphics.winmd) - "no extension method found" despite
    # the interface itself resolving fine. Avoiding AsTask avoids that whole conflict.
    $csSource = @'
using Windows.Foundation;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
public static class OcrHelper {
    public static OcrResult Recognize(SoftwareBitmap bitmap) {
        var engine = OcrEngine.TryCreateFromUserProfileLanguages();
        if (engine == null) throw new System.Exception("No OCR engine available for the current user profile languages");
        var op = engine.RecognizeAsync(bitmap);
        while (op.Status == AsyncStatus.Started) { System.Threading.Thread.Sleep(5); }
        if (op.Status == AsyncStatus.Error) { throw new System.Exception("OCR failed: " + op.ErrorCode); }
        return op.GetResults();
    }
}
'@
    $csPath = Join-Path $env:TEMP "OverLexOcrHelper.cs"
    Set-Content -Path $csPath -Value $csSource -Encoding UTF8
    $refs = @($mscorlibDll, $systemRuntimeDll, "$winmdDir\Windows.Foundation.winmd", "$winmdDir\Windows.Media.winmd", "$winmdDir\Windows.Graphics.winmd") -join ";"
    $cscOut = & $csc /nologo /target:library "/out:$dllPath" "/reference:$refs" $csPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw "csc.exe failed: $cscOut" }
}
Add-Type -Path $dllPath

$src = [System.Drawing.Bitmap]::FromFile($imgPath)
$w = $src.Width
$h = $src.Height
$rect = New-Object System.Drawing.Rectangle(0, 0, $w, $h)
$bmpData = $src.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$bytes = New-Object byte[] ($bmpData.Stride * $h)
[System.Runtime.InteropServices.Marshal]::Copy($bmpData.Scan0, $bytes, 0, $bytes.Length)
$src.UnlockBits($bmpData)
$src.Dispose()

$buffer = [System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions]::AsBuffer($bytes)
$bitmap = [Windows.Graphics.Imaging.SoftwareBitmap]::CreateCopyFromBuffer(
    $buffer, [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [uint32]$w, [uint32]$h)

$result = [OcrHelper]::Recognize($bitmap)

foreach ($line in $result.Lines) {
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        Write-Output "$($r.X)|$($r.Y)|$($r.Width)|$($r.Height)|$($word.Text)"
    }
}
"""

if _IS_WIN:
    import subprocess
    _PS_SCRIPT = _data_dir / "_ocr_helper.ps1"
    _PS_SCRIPT.write_text(_PS_BODY, encoding="utf-8")

    def _ocr(img: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            img.save(f.name, "BMP"); tmp = f.name
        try:
            # StorageFile requires absolute path
            abs_tmp = str(Path(tmp).resolve())
            r = subprocess.run(
                ["powershell", "-NonInteractive", "-NoProfile",
                 "-ExecutionPolicy", "Bypass", "-File", str(_PS_SCRIPT), abs_tmp],
                capture_output=True, text=True, timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW)
            items = []
            for line in r.stdout.strip().splitlines():
                p = line.strip().split("|")
                if len(p) != 5: continue
                try:
                    x,y,w,h = float(p[0]),float(p[1]),float(p[2]),float(p[3])
                    items.append(([[x,y],[x+w,y],[x+w,y+h],[x,y+h]], p[4], 1.0))
                except: pass
            if r.stderr and "error" in r.stderr.lower():
                _log(f"[ocr] ps error: {r.stderr[:120]}")
            return items
        finally:
            try: os.unlink(tmp)
            except: pass

elif _IS_MAC:
    import subprocess
    if getattr(sys, "frozen", False):
        # PyInstaller's onedir macOS layout puts bundled binaries under Contents/Frameworks
        # (sys._MEIPASS), not next to the executable in Contents/MacOS (sys.executable).
        # build_mac.sh bundles a precompiled _ocr_helper_bin there so end users never need Xcode.
        _SWIFT_BIN = Path(sys._MEIPASS) / "_ocr_helper_bin"
    else:
        _SWIFT_BIN = _exe_dir / "_ocr_helper_bin"
        if not _SWIFT_BIN.exists():
            _SWIFT_SRC = Path(__file__).resolve().parent / "macos_ocr_helper.swift"
            _log("[ocr] compiling swift helper...")
            subprocess.run(["swiftc", str(_SWIFT_SRC), "-O", "-o", str(_SWIFT_BIN)], check=True)

    def _ocr(img: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f.name); tmp = f.name
        try:
            r = subprocess.run([str(_SWIFT_BIN), tmp],
                               capture_output=True, text=True, timeout=12)
            items = []
            for line in r.stdout.strip().splitlines():
                p = line.strip().split("|")
                if len(p) != 5: continue
                try:
                    x,y,w,h = float(p[0]),float(p[1]),float(p[2]),float(p[3])
                    items.append(([[x,y],[x+w,y],[x+w,y+h],[x,y+h]], p[4], 1.0))
                except: pass
            return items
        finally:
            try: os.unlink(tmp)
            except: pass
else:
    raise RuntimeError(f"Unsupported platform: {platform.system()}")

_log("[OverLex] OCR ready")

# == Qt =======================================================================

from PySide6.QtWidgets import (QApplication, QWidget, QGraphicsDropShadowEffect,
                             QSystemTrayIcon, QMenu, QLabel)
from PySide6.QtCore   import Qt, QTimer, Signal, QObject, QPoint, QRect
from PySide6.QtGui    import (QFont, QColor, QPainter, QPainterPath, QPen, QBrush,
                             QLinearGradient, QFontMetrics, QIcon, QPixmap,
                             QAction)

class _Bus(QObject):
    show       = Signal(int, int, str)
    hide_now   = Signal()
    show_block = Signal(int, int, str)
    sel_start  = Signal(int, int)
    sel_move   = Signal(int, int)
    sel_end    = Signal(int, int)
    sel_cancel = Signal()
bus = _Bus()

# == Translation ==============================================================

_cache: OrderedDict = OrderedDict()
def _tr_once(text):
    resp = _http.get(_TR_URL, params={"client":"gtx","sl":SRC,"tl":DST,"dt":"t","q":text})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]!r}")
    data = resp.json()
    return "".join(s[0] for s in data[0] if s[0]) if data[0] else text

def _tr(text):
    k = text.lower().strip()
    if k in _cache: _cache.move_to_end(k); return _cache[k]
    result = text
    for attempt in (1, 2):
        try:
            result = _tr_once(text)
            break
        except Exception as e:
            _log(f"[tr] attempt {attempt} failed: {e}")
            if attempt == 1: time.sleep(0.4)
    _cache[k] = result
    if len(_cache) > CACHE_MAX: _cache.popitem(last=False)
    return result

# == Input hooks ==============================================================

def _keys(*names):
    return {getattr(pkeyboard.Key, name) for name in names if hasattr(pkeyboard.Key, name)}

_CTRL_KEYS = _keys("ctrl", "ctrl_l", "ctrl_r")
_ALT_KEYS = _keys("alt", "alt_l", "alt_r", "alt_gr")

DRAG_PX = 6  # move further than this before release -> sentence mode; otherwise -> word mode

_ctrl = False; _alt = False; _busy = False; _last_xy = (0, 0)
_armed = False; _drag_button = None; _press_xy = (0, 0); _dragging = False
_mouse_ctl = pmouse.Controller()

def _start_at(x, y):
    global _busy
    if not _busy:
        _busy = True
        threading.Thread(target=_run, args=(x, y), daemon=True).start()

def _current_xy():
    try:
        x, y = _mouse_ctl.position
        return int(x), int(y)
    except Exception:
        return _last_xy

def _kp(k):
    global _ctrl, _alt, _armed, _dragging
    if k in _CTRL_KEYS: _ctrl = True
    elif k in _ALT_KEYS: _alt = True
    elif k == pkeyboard.Key.esc and _armed:
        _log("[input] Esc cancel region select")
        _armed = False; _dragging = False
        bus.sel_cancel.emit()
    elif _IS_MAC and k == pkeyboard.Key.space and _ctrl and _alt:
        _log("[input] Ctrl+Option+Space")
        _start_at(*_current_xy())

def _kr(k):
    global _ctrl, _alt
    if k in _CTRL_KEYS: _ctrl = False
    elif k in _ALT_KEYS: _alt = False

def _mm(x, y):
    global _last_xy, _dragging
    _last_xy = (x, y)
    if not _armed: return
    if not _dragging:
        dx, dy = x-_press_xy[0], y-_press_xy[1]
        if dx*dx + dy*dy >= DRAG_PX*DRAG_PX:
            _dragging = True
            bus.sel_start.emit(int(_press_xy[0]), int(_press_xy[1]))
    if _dragging:
        bus.sel_move.emit(int(x), int(y))

def _mc(x, y, b, pressed):
    global _armed, _drag_button, _press_xy, _dragging
    if _armed:
        if not pressed and b == _drag_button:
            _armed = False
            if _dragging:
                _dragging = False
                bus.sel_end.emit(int(x), int(y))
            else:
                _start_at(*_press_xy)
        return
    if not pressed: return
    trigger = ((_IS_MAC and b == pmouse.Button.left and _alt) or
               (_IS_WIN and b == pmouse.Button.middle and _ctrl))
    if trigger:
        _log(f"[input] {'Option' if _IS_MAC else 'Ctrl'}+Click at {int(x)},{int(y)}")
        _armed = True; _drag_button = b; _press_xy = (x, y); _dragging = False
    elif (_IS_MAC and b != pmouse.Button.left) or (_IS_WIN and b != pmouse.Button.middle):
        bus.hide_now.emit()

# == OCR helpers ==============================================================

def _rect(bbox):
    xs,ys = [float(p[0]) for p in bbox],[float(p[1]) for p in bbox]
    bx,by = min(xs),min(ys); return bx,by,max(xs)-bx,max(ys)-by

def _word_at(text, bx, bw, rx):
    words = text.split()
    if not words: return text
    if len(words) == 1: return words[0]
    total = sum(len(w) for w in words) or 1
    cx = bx
    for w in words:
        ww = bw*len(w)/total
        if cx <= rx <= cx+ww: return w
        cx += ww
    cx,best,bd = bx,words[0],float("inf")
    for w in words:
        ww = bw*len(w)/total
        d = abs(rx-(cx+ww/2))
        if d < bd: best,bd = w,d
        cx += ww
    return best

def _group_text(rows):
    """Reflow OCR boxes (word-level on Windows, line-level on macOS) into
    reading-order text: cluster by vertical overlap into lines, sort each
    line left-to-right, sort lines top-to-bottom."""
    items = []
    for bbox, text, _ in rows:
        t = text.strip()
        if not t: continue
        bx, by, bw, bh = _rect(bbox)
        items.append((by, by+bh, bx, t))
    if not items: return ""
    items.sort(key=lambda it: (it[0], it[2]))
    lines, cur, cur_bottom = [], [items[0]], items[0][1]
    for it in items[1:]:
        if it[0] >= cur_bottom:
            lines.append(cur); cur = [it]; cur_bottom = it[1]
        else:
            cur.append(it); cur_bottom = max(cur_bottom, it[1])
    lines.append(cur)
    return "\n".join(
        " ".join(w[3] for w in sorted(ln, key=lambda w: w[2]))
        for ln in lines)

# == Pipeline =================================================================

def _run(x, y):
    global _busy
    try:
        lft,top = max(0,x-CAPTURE_W//2), max(0,y-CAPTURE_H//2)
        with mss.MSS() as sct:
            raw = sct.grab({"left":lft,"top":top,"width":CAPTURE_W,"height":CAPTURE_H})
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img = img.resize((img.width*OCR_SCALE, img.height*OCR_SCALE), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(1.5)

        rows = _ocr(img)
        rx,ry = (x-lft)*OCR_SCALE, (y-top)*OCR_SCALE
        found = None; best_d = float("inf")
        for bbox,text,_ in rows:
            if not text.strip(): continue
            bx,by,bw,bh = _rect(bbox); pad = HIT_PAD*OCR_SCALE
            if bx-pad<=rx<=bx+bw+pad and by-pad<=ry<=by+bh+pad:
                found = _word_at(text,bx,bw,rx); best_d = 0; break
            d = ((rx-(bx+bw/2))**2+(ry-(by+bh/2))**2)**.5
            if d < best_d: best_d = d; found = _word_at(text,bx,bw,rx)

        if best_d > 300 or not found: bus.hide_now.emit(); return
        clean = re.sub(r"[^\w'\-]","",found).strip()
        if not clean or len(clean) < 2: bus.hide_now.emit(); return

        result = _tr(clean)
        _log(f"[run] {clean!r} -> {result!r}")
        bus.show.emit(x, y, result)
    except Exception as e:
        _log(f"[run] {e}"); import traceback; _log(traceback.format_exc())
        bus.hide_now.emit()
    finally:
        _busy = False

def _run_region(l, t, w, h):
    global _busy
    try:
        with mss.MSS() as sct:
            raw = sct.grab({"left": l, "top": t, "width": w, "height": h})
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if max(img.width, img.height) <= OCR_UPSCALE_MAX_SIDE:
            img = img.resize((img.width*OCR_SCALE, img.height*OCR_SCALE), Image.LANCZOS)
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = ImageEnhance.Sharpness(img).enhance(1.5)

        rows = _ocr(img)
        text = _group_text(rows)
        if not text.strip():
            bus.hide_now.emit(); return

        flat = re.sub(r"\s*\n\s*", " ", text).strip()
        result = _tr(flat)
        _log(f"[region] {flat!r} -> {result!r}")
        bus.show_block.emit(l + w//2, t + h, result)
    except Exception as e:
        _log(f"[region] {e}"); import traceback; _log(traceback.format_exc())
        bus.hide_now.emit()
    finally:
        _busy = False

# == Focus ====================================================================

def _grab_focus(hwnd):
    if _IS_WIN:
        import ctypes
        u32 = ctypes.windll.user32
        u32.SetForegroundWindow(hwnd); u32.BringWindowToTop(hwnd)
    elif _IS_MAC:
        import subprocess
        subprocess.Popen(["osascript", "-e",
            'tell app "System Events" to set frontmost of first process whose frontmost is true to false'])

# == Icon =====================================================================

def _make_icon(size=64):
    # Reuses the same squircle+A/Я design tools/gen_icon.py bakes into the
    # installed .ico/.icns, instead of maintaining a second, drifting QPainter
    # re-implementation of the same icon.
    from tools.gen_icon import render as _render_icon
    img = _render_icon(size).convert("RGBA")
    buf = io.BytesIO(); img.save(buf, "PNG")
    px = QPixmap(); px.loadFromData(buf.getvalue())
    return QIcon(px)

# == Overlay ==================================================================

OW=320; PAD_H=24; PAD_V=14; ABAR=3; R=12
BW=440; MAX_BH=360  # block (sentence-mode) overlay: wider, taller, word-wrapped
C_BG  = QColor(8,10,20,165)
C_AT  = QColor(48,130,255); C_AB = QColor(110,65,250)
C_TR  = QColor(230,240,255,255); C_BDR = QColor(255,255,255,18)

def _paint_card(painter, w, h):
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    clip=QPainterPath(); clip.addRoundedRect(0,0,w,h,R,R)
    painter.setClipPath(clip); painter.fillRect(0,0,w,h,C_BG)
    bar=QPainterPath(); bar.addRoundedRect(0,0,ABAR,h,1,1)
    g=QLinearGradient(0,0,0,h); g.setColorAt(0,C_AT); g.setColorAt(1,C_AB)
    painter.fillPath(bar,g)
    painter.setClipping(False); painter.setPen(C_BDR)
    brd=QPainterPath(); brd.addRoundedRect(.5,.5,w-1,h-1,R,R)
    painter.drawPath(brd)

def _place_near(widget, sx, sy):
    scr = QApplication.screenAt(QPoint(sx,sy)) or QApplication.primaryScreen()
    g = scr.geometry(); W,H = widget.width(),widget.height()
    x=sx+22; y=sy-H-14
    if x+W>g.right()-6:   x=sx-W-22
    if x<g.left()+6:      x=g.left()+6
    if y<g.top()+6:       y=sy+20
    if y+H>g.bottom()-6:  y=g.bottom()-H-6
    widget.move(x,y)

def _phys_to_logical(px, py):
    """pynput/mss report raw physical pixels on Windows; Qt's HiDPI-scaled
    widget positioning speaks logical pixels. Without this conversion the
    popup lands off by the monitor's scale factor on any non-100% display."""
    if not _IS_WIN:
        return px, py
    for scr in QApplication.screens():
        dpr = scr.devicePixelRatio()
        g = scr.geometry()
        left, top = g.left()*dpr, g.top()*dpr
        right, bottom = left+g.width()*dpr, top+g.height()*dpr
        if left <= px < right and top <= py < bottom:
            return g.left()+(px-left)/dpr, g.top()+(py-top)/dpr
    scr = QApplication.primaryScreen()
    dpr = scr.devicePixelRatio() if scr else 1.0
    return px/dpr, py/dpr

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|
                            Qt.Tool|Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.mousePressEvent = lambda _: self.hide()
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30); sh.setOffset(0,4); sh.setColor(QColor(0,0,0,185))
        self.setGraphicsEffect(sh)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._text = ""; self._font = QFont("Segoe UI",20,QFont.Bold)

    def present(self, sx, sy, word):
        sx, sy = _phys_to_logical(sx, sy)
        self._text = word
        fname = "Segoe UI" if _IS_WIN else "SF Pro Display"
        max_tw = OW-PAD_H*2-ABAR-6
        for sz in range(26,10,-1):
            f = QFont(fname, sz, QFont.Bold)
            if QFontMetrics(f).horizontalAdvance(word) <= max_tw:
                self._font = f; break
        fm = QFontMetrics(self._font)
        w = min(fm.horizontalAdvance(word)+PAD_H*2+ABAR+6, OW)
        h = fm.height()+PAD_V*2
        self.setFixedSize(w,h); self._place(sx,sy)
        self.show(); self.raise_()
        try: _grab_focus(int(self.winId()))
        except: pass
        self.update(); self._timer.start(HIDE_MS)

    def _place(self, sx, sy):
        _place_near(self, sx, sy)

    def paintEvent(self,_):
        p=QPainter(self)
        W,H=self.width(),self.height()
        _paint_card(p,W,H)
        p.setFont(self._font); p.setPen(C_TR)
        p.drawText(ABAR+PAD_H,0,W-ABAR-PAD_H*2,H,
                   Qt.AlignLeft|Qt.AlignVCenter|Qt.TextSingleLine,self._text)

# == Block overlay (sentence / region-translate mode) ========================

class BlockOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|
                            Qt.Tool|Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.mousePressEvent = lambda _: self.hide()
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30); sh.setOffset(0,4); sh.setColor(QColor(0,0,0,185))
        self.setGraphicsEffect(sh)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        fname = "Segoe UI" if _IS_WIN else "SF Pro Display"
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setFont(QFont(fname, 15, QFont.Bold))
        self._label.setStyleSheet("color: rgb(230,240,255); background: transparent;")
        self._label.setAlignment(Qt.AlignLeft|Qt.AlignTop)

    def present(self, sx, sy, text):
        sx, sy = _phys_to_logical(sx, sy)
        maxw = BW-PAD_H*2-ABAR-6
        self._label.setFixedWidth(maxw)
        self._label.setText(text)
        self._label.adjustSize()
        w = BW
        h = min(self._label.height()+PAD_V*2, MAX_BH)
        self.setFixedSize(w,h); self._label.move(ABAR+PAD_H,PAD_V)
        _place_near(self, sx, sy)
        self.show(); self.raise_()
        try: _grab_focus(int(self.winId()))
        except: pass
        self.update(); self._timer.start(HIDE_MS)

    def paintEvent(self,_):
        p=QPainter(self); _paint_card(p,self.width(),self.height())

# == Region selector (drag-to-select rubber band for sentence mode) ==========

class RegionSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|
                            Qt.Tool|Qt.WindowTransparentForInput|Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._raw_a = (0,0); self._raw_b = (0,0); self._geo = None

    def begin(self, x, y):
        self._raw_a = self._raw_b = (x, y)
        lx, ly = _phys_to_logical(x, y)
        scr = QApplication.screenAt(QPoint(int(lx),int(ly))) or QApplication.primaryScreen()
        self._geo = scr.geometry()
        self.setGeometry(self._geo)
        self.show(); self.raise_(); self.update()

    def move_to(self, x, y):
        # Repaint only the changed strip, not the whole (often 4K) virtual screen -
        # keeps the drag feeling instant instead of redoing full-screen alpha compositing
        # on every mouse-move event.
        dirty = self._local_rect().adjusted(-12,-12,12,12)
        self._raw_b = (x, y)
        dirty = dirty.united(self._local_rect().adjusted(-12,-12,12,12))
        self.update(dirty)

    def _local(self, x, y):
        lx, ly = _phys_to_logical(x, y)
        return QPoint(int(lx-self._geo.left()), int(ly-self._geo.top()))

    def _local_rect(self):
        return QRect(self._local(*self._raw_a), self._local(*self._raw_b)).normalized()

    def capture_rect(self):
        (ax,ay),(bx,by) = self._raw_a, self._raw_b
        l,t = min(ax,bx), min(ay,by)
        return int(l), int(t), int(abs(bx-ax)), int(abs(by-ay))

    def paintEvent(self,_):
        if self._geo is None: return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(6,8,16,90))
        r = self._local_rect()
        if r.width() < 1 or r.height() < 1: return
        rr = R+3
        clear = QPainterPath(); clear.addRoundedRect(r, rr, rr)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.fillPath(clear, Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # soft neon glow behind the crisp edge - a few widening, fading strokes
        for width, alpha in ((10,16),(6,28),(3,50)):
            glow = QColor(C_AT); glow.setAlpha(alpha)
            p.setPen(QPen(glow, width)); p.drawPath(clear)

        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, C_AT); grad.setColorAt(1, C_AB)
        p.setPen(QPen(QBrush(grad), 2)); p.drawPath(clear)

    def finish(self, x, y):
        # A bound QObject method (unlike a plain function) gets its Qt signal
        # connection auto-queued onto this widget's own thread - without that,
        # hide()/paint state here would be touched from the pynput listener
        # thread and the dimmed frame could get stuck on screen forever.
        global _busy
        self.move_to(x, y)
        l, t, w, h = self.capture_rect()
        self.hide()
        if w < 8 or h < 8 or _busy:
            return
        _busy = True
        threading.Thread(target=_run_region, args=(l, t, w, h), daemon=True).start()

# == Autostart ================================================================

def _autostart_args():
    if getattr(sys,"frozen",False): return [str(Path(sys.executable))]
    return [sys.executable, str(Path(__file__).resolve())]

def _autostart_set(enable: bool):
    if _IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE) as k:
                if enable:
                    value = " ".join(f'"{p}"' for p in _autostart_args())
                    winreg.SetValueEx(k,APP_NAME,0,winreg.REG_SZ,value)
                else:
                    try: winreg.DeleteValue(k,APP_NAME)
                    except FileNotFoundError: pass
        except Exception as e: _log(f"[autostart] {e}")
    elif _IS_MAC:
        plist = Path.home()/"Library"/"LaunchAgents"/"com.overlex.app.plist"
        if enable:
            args = "".join(f"<string>{p}</string>" for p in _autostart_args())
            plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.overlex.app</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>RunAtLoad</key><true/>
</dict></plist>""")
        else:
            plist.unlink(missing_ok=True)

def _autostart_get():
    if _IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k,APP_NAME); return True
        except: return False
    elif _IS_MAC:
        return (Path.home()/"Library"/"LaunchAgents"/"com.overlex.app.plist").exists()
    return False

# == Tray =====================================================================

class Tray(QSystemTrayIcon):
    def __init__(self, icon, app):
        super().__init__(icon); self._app=app; self._enabled=True
        hint = ("Option+Click: click=word, drag=sentence" if _IS_MAC
                else "Ctrl+Middle Click: click=word, drag=sentence")
        self.setToolTip(f"OverLex - {hint}")
        self._menu = QMenu()

        self._a_on = QAction("Active"); self._a_on.setCheckable(True)
        self._a_on.setChecked(True); self._a_on.triggered.connect(self._toggle)
        self._menu.addAction(self._a_on); self._menu.addSeparator()

        self._a_auto = QAction("Launch at login"); self._a_auto.setCheckable(True)
        self._a_auto.setChecked(_autostart_get())
        self._a_auto.triggered.connect(lambda c: _autostart_set(c))
        self._menu.addAction(self._a_auto); self._menu.addSeparator()

        self._a_quit = QAction("Quit")
        self._a_quit.triggered.connect(self._do_quit)
        self._menu.addAction(self._a_quit)

        self.setContextMenu(self._menu); self.show()

    def _toggle(self, on):
        self._enabled = on
        self._a_on.setText("Active" if on else "Paused")

    def _do_quit(self):
        _log("[tray] quit"); self.hide(); self._app.quit()

    @property
    def enabled(self): return self._enabled

# == Main =====================================================================

_tray_ref = None

def _mc_guard(x, y, b, pressed):
    if _tray_ref and not _tray_ref.enabled: return
    _mc(x, y, b, pressed)

def main():
    global _tray_ref
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    _tray_ref = Tray(_make_icon(), app)
    ov = Overlay(); bus.show.connect(ov.present); bus.hide_now.connect(ov.hide)
    blk = BlockOverlay(); bus.show_block.connect(blk.present); bus.hide_now.connect(blk.hide)
    sel = RegionSelector()
    bus.sel_start.connect(sel.begin)
    bus.sel_move.connect(sel.move_to)
    bus.sel_end.connect(sel.finish)
    bus.sel_cancel.connect(sel.hide)
    kb = pkeyboard.Listener(on_press=_kp, on_release=_kr)
    ms = pmouse.Listener(on_move=_mm, on_click=_mc_guard)
    kb.daemon = ms.daemon = True; kb.start(); ms.start()
    _log("[main] listeners OK")
    hint = ("Option+Click: click=word, drag=sentence" if _IS_MAC
            else "Ctrl+Middle Click: click=word, drag=sentence")
    _tray_ref.showMessage("OverLex", f"{hint}.",
                          QSystemTrayIcon.Information, 3000)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
