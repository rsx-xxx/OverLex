#!/usr/bin/env python3
"""
OverLex — Screen Translation Overlay
Ctrl + Middle Click → перевод слова EN→RU прямо на экране.
Windows: OCR via PowerShell / Windows.Media.Ocr
macOS:   OCR via Swift / Vision.framework
"""
import os, sys, re, threading, signal, io, platform
from pathlib import Path
from collections import OrderedDict

import mss, requests
from PIL import Image, ImageEnhance
from pynput import mouse as pmouse, keyboard as pkeyboard

_IS_WIN = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"

# ── Лог ───────────────────────────────────────────────────────────────────────
_exe_dir = Path(sys.executable if getattr(sys,"frozen",False) else __file__).parent
_LOG = open(_exe_dir / "overlex.log", "w", buffering=1, encoding="utf-8")
def _log(*a):
    s = " ".join(str(x) for x in a); print(s); _LOG.write(s+"\n")

_log(f"[OverLex] старт | {platform.system()} {platform.release()}")

# ── Конфигурация ──────────────────────────────────────────────────────────────
CAPTURE_W, CAPTURE_H = 900, 180
OCR_SCALE  = 2
HIDE_MS    = 5000
SRC, DST   = "en", "ru"
HIT_PAD    = 20
CACHE_MAX  = 500
APP_NAME   = "OverLex"

_TR_URL    = "https://translate.googleapis.com/translate_a/single"
_TR_PARAMS = {"client":"gtx","sl":SRC,"tl":DST,"dt":"t"}
_SESSION   = requests.Session()
_SESSION.headers.update({"User-Agent":"Mozilla/5.0"})

# ═══════════════════════════════════════════════════════════════════════════════
#  OCR — платформозависимый
# ═══════════════════════════════════════════════════════════════════════════════

if _IS_WIN:
    import subprocess, base64

    _PS_SCRIPT = _exe_dir / "_ocr_helper.ps1"
    _PS_SCRIPT.write_text(r"""
param([string]$b64)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Foundation,ContentType=WindowsRuntime]
function Await($t){$t.GetAwaiter().GetResult()}
$bytes=[Convert]::FromBase64String($b64)
$stream=[Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
$writer=[Windows.Storage.Streams.DataWriter]::new($stream)
$writer.WriteBytes($bytes)
Await($writer.StoreAsync())|Out-Null
$stream.Seek(0)
$dec=Await([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream))
$bmp=Await($dec.GetSoftwareBitmapAsync())
$eng=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$res=Await($eng.RecognizeAsync($bmp))
foreach($line in $res.Lines){foreach($word in $line.Words){
    $r=$word.BoundingRect
    Write-Output "$($r.X)|$($r.Y)|$($r.Width)|$($r.Height)|$($word.Text)"
}}
""", encoding="utf-8")

    def _ocr(img: Image.Image):
        buf = io.BytesIO(); img.save(buf,"BMP")
        b64 = base64.b64encode(buf.getvalue()).decode()
        r = subprocess.run(
            ["powershell","-NonInteractive","-NoProfile",
             "-ExecutionPolicy","Bypass","-File",str(_PS_SCRIPT),b64],
            capture_output=True, text=True, timeout=12)
        items = []
        for line in r.stdout.strip().splitlines():
            p = line.strip().split("|")
            if len(p)!=5: continue
            try:
                x,y,w,h=float(p[0]),float(p[1]),float(p[2]),float(p[3])
                bbox=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
                items.append((bbox,p[4],1.0))
            except: pass
        return items

elif _IS_MAC:
    import subprocess, tempfile

    # Swift-скрипт компилируется при первом запуске
    _SWIFT_SRC = _exe_dir / "_ocr_helper.swift"
    _SWIFT_BIN = _exe_dir / "_ocr_helper_bin"
    _SWIFT_SRC.write_text("""
import Vision, AppKit, Foundation
let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg  = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
for obs in (req.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    let x = b.origin.x * Double(cg.width)
    let y = (1 - b.origin.y - b.size.height) * Double(cg.height)
    let w = b.size.width  * Double(cg.width)
    let h = b.size.height * Double(cg.height)
    print("\\(x)|\\(y)|\\(w)|\\(h)|\\(top.string)")
}
""", encoding="utf-8")

    if not _SWIFT_BIN.exists():
        _log("[OCR] компиляция Swift-хелпера…")
        subprocess.run(["swiftc",str(_SWIFT_SRC),"-o",str(_SWIFT_BIN)],check=True)
        _log("[OCR] Swift-хелпер скомпилирован")

    def _ocr(img: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f.name); tmp = f.name
        try:
            r = subprocess.run([str(_SWIFT_BIN), tmp],
                               capture_output=True, text=True, timeout=12)
            items = []
            for line in r.stdout.strip().splitlines():
                p = line.strip().split("|")
                if len(p)!=5: continue
                try:
                    x,y,w,h=float(p[0]),float(p[1]),float(p[2]),float(p[3])
                    items.append(([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],p[4],1.0))
                except: pass
            return items
        finally:
            os.unlink(tmp)

else:
    raise RuntimeError(f"Платформа не поддерживается: {platform.system()}")

_log("[OverLex] OCR готов")

# ═══════════════════════════════════════════════════════════════════════════════
#  Автозапуск — платформозависимый
# ═══════════════════════════════════════════════════════════════════════════════

def _autostart_val():
    if getattr(sys,"frozen",False): return str(Path(sys.executable))
    return f"{sys.executable} {Path(__file__).resolve()}"

def _autostart_set(enable: bool):
    if _IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE) as k:
                if enable:
                    winreg.SetValueEx(k,APP_NAME,0,winreg.REG_SZ,f'"{_autostart_val()}"')
                else:
                    try: winreg.DeleteValue(k,APP_NAME)
                    except FileNotFoundError: pass
        except Exception as e: _log(f"[autostart] {e}")

    elif _IS_MAC:
        plist_path = Path.home()/"Library"/"LaunchAgents"/f"com.overlex.app.plist"
        if enable:
            exe = _autostart_val()
            plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.overlex.app</string>
  <key>ProgramArguments</key><array>
    {"".join(f"<string>{p}</string>" for p in exe.split())}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict></plist>"""
            plist_path.write_text(plist)
            _log(f"[autostart] +{plist_path}")
        else:
            plist_path.unlink(missing_ok=True)
            _log("[autostart] удалён")

def _autostart_get() -> bool:
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

# ═══════════════════════════════════════════════════════════════════════════════
#  Фокус — платформозависимый
# ═══════════════════════════════════════════════════════════════════════════════

def _grab_focus(hwnd):
    if _IS_WIN:
        import ctypes
        u32 = ctypes.windll.user32
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
    elif _IS_MAC:
        import subprocess
        subprocess.Popen(["osascript","-e",
            'tell application "System Events" to set frontmost of first process whose frontmost is true to false'])

# ═══════════════════════════════════════════════════════════════════════════════
#  Qt
# ═══════════════════════════════════════════════════════════════════════════════
from PyQt5.QtWidgets import (QApplication, QWidget, QGraphicsDropShadowEffect,
                             QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtCore   import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt5.QtGui    import (QFont, QColor, QPainter, QPainterPath,
                             QLinearGradient, QFontMetrics, QIcon, QPixmap)

class _Bus(QObject):
    show     = pyqtSignal(int, int, str)
    hide_now = pyqtSignal()
bus = _Bus()

# ── Кэш + перевод ─────────────────────────────────────────────────────────────
_cache: OrderedDict = OrderedDict()
def _tr(text):
    k=text.lower().strip()
    if k in _cache: _cache.move_to_end(k); return _cache[k]
    try:
        r=_SESSION.get(_TR_URL,params={**_TR_PARAMS,"q":text},timeout=4)
        data=r.json()
        result="".join(s[0] for s in data[0] if s[0]) if data[0] else text
    except Exception as e: _log(f"[tr] {e}"); result=text
    _cache[k]=result
    if len(_cache)>CACHE_MAX: _cache.popitem(last=False)
    return result

# ── Хуки ──────────────────────────────────────────────────────────────────────
_ctrl=False; _busy=False
def _kp(k):
    global _ctrl
    if k in (pkeyboard.Key.ctrl_l,pkeyboard.Key.ctrl_r): _ctrl=True
def _kr(k):
    global _ctrl
    if k in (pkeyboard.Key.ctrl_l,pkeyboard.Key.ctrl_r): _ctrl=False
def _mc(x,y,b,pressed):
    global _busy
    if not pressed: return
    if b==pmouse.Button.middle and _ctrl:
        if not _busy: _busy=True; threading.Thread(target=_run,args=(x,y),daemon=True).start()
    elif b!=pmouse.Button.middle:
        bus.hide_now.emit()

# ── OCR helpers ───────────────────────────────────────────────────────────────
def _rect(bbox):
    xs,ys=[float(p[0]) for p in bbox],[float(p[1]) for p in bbox]
    bx,by=min(xs),min(ys); return bx,by,max(xs)-bx,max(ys)-by

def _word_at(text,bx,bw,rx):
    words=text.split()
    if not words: return text
    if len(words)==1: return words[0]
    total=sum(len(w) for w in words) or 1
    cx=bx
    for w in words:
        ww=bw*len(w)/total
        if cx<=rx<=cx+ww: return w
        cx+=ww
    cx,best,bd=bx,words[0],float("inf")
    for w in words:
        ww=bw*len(w)/total
        d=abs(rx-(cx+ww/2))
        if d<bd: best,bd=w,d
        cx+=ww
    return best

# ── Pipeline ──────────────────────────────────────────────────────────────────
def _run(x,y):
    global _busy
    try:
        lft,top=max(0,x-CAPTURE_W//2),max(0,y-CAPTURE_H//2)
        with mss.MSS() as sct:
            raw=sct.grab({"left":lft,"top":top,"width":CAPTURE_W,"height":CAPTURE_H})
            img=Image.frombytes("RGB",raw.size,raw.bgra,"raw","BGRX")
        img=img.resize((img.width*OCR_SCALE,img.height*OCR_SCALE),Image.LANCZOS)
        img=ImageEnhance.Contrast(img).enhance(2.0)
        img=ImageEnhance.Sharpness(img).enhance(1.5)
        rows=_ocr(img)
        rx,ry=(x-lft)*OCR_SCALE,(y-top)*OCR_SCALE
        found=None; best_d=float("inf")
        for bbox,text,_ in rows:
            if not text.strip(): continue
            bx,by,bw,bh=_rect(bbox); pad=HIT_PAD*OCR_SCALE
            if bx-pad<=rx<=bx+bw+pad and by-pad<=ry<=by+bh+pad:
                found=_word_at(text,bx,bw,rx); best_d=0; break
            d=((rx-(bx+bw/2))**2+(ry-(by+bh/2))**2)**.5
            if d<best_d: best_d=d; found=_word_at(text,bx,bw,rx)
        if best_d>300 or not found: bus.hide_now.emit(); return
        clean=re.sub(r"[^\w'\-]","",found).strip()
        if not clean or len(clean)<2: bus.hide_now.emit(); return
        result=_tr(clean)
        _log(f"[run] {clean!r} → {result!r}")
        bus.show.emit(x,y,result)
    except Exception as e:
        _log(f"[run] {e}"); import traceback; _log(traceback.format_exc())
        bus.hide_now.emit()
    finally:
        _busy=False

# ── Иконка ────────────────────────────────────────────────────────────────────
def _make_icon(size=64):
    px=QPixmap(size,size); px.fill(Qt.transparent)
    p=QPainter(px); p.setRenderHint(QPainter.Antialiasing)
    g=QLinearGradient(0,0,size,size)
    g.setColorAt(0,QColor(48,130,255)); g.setColorAt(1,QColor(110,65,250))
    path=QPainterPath(); path.addEllipse(2,2,size-4,size-4)
    p.fillPath(path,g)
    p.setPen(QColor(255,255,255))
    p.setFont(QFont("Segoe UI" if _IS_WIN else "SF Pro Display",int(size*.38),QFont.Bold))
    p.drawText(px.rect(),Qt.AlignCenter,"OL"); p.end()
    return QIcon(px)

# ── Overlay ───────────────────────────────────────────────────────────────────
OW=320; PAD_H=24; PAD_V=14; ABAR=3; R=12
C_BG=QColor(8,10,20,165); C_AT=QColor(48,130,255); C_AB=QColor(110,65,250)
C_TR=QColor(230,240,255,255); C_BDR=QColor(255,255,255,18)

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|
                            Qt.Tool|Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.mousePressEvent=lambda _:self.hide()
        sh=QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(30); sh.setOffset(0,4); sh.setColor(QColor(0,0,0,185))
        self.setGraphicsEffect(sh)
        self._timer=QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._text=""; self._font=QFont("Segoe UI",20,QFont.Bold)

    def present(self,sx,sy,word):
        self._text=word
        max_tw=OW-PAD_H*2-ABAR-6
        for sz in range(26,10,-1):
            f=QFont("Segoe UI" if _IS_WIN else "SF Pro Display",sz,QFont.Bold)
            if QFontMetrics(f).horizontalAdvance(word)<=max_tw:
                self._font=f; break
        fm=QFontMetrics(self._font)
        w=min(fm.horizontalAdvance(word)+PAD_H*2+ABAR+6,OW)
        h=fm.height()+PAD_V*2
        self.setFixedSize(w,h); self._place(sx,sy)
        self.show(); self.raise_()
        try: _grab_focus(int(self.winId()))
        except: pass
        self.update(); self._timer.start(HIDE_MS)

    def _place(self,sx,sy):
        scr=QApplication.screenAt(QPoint(sx,sy)) or QApplication.primaryScreen()
        g=scr.geometry(); W,H=self.width(),self.height()
        x=sx+22; y=sy-H-14
        if x+W>g.right()-6:  x=sx-W-22
        if x<g.left()+6:     x=g.left()+6
        if y<g.top()+6:      y=sy+20
        if y+H>g.bottom()-6: y=g.bottom()-H-6
        self.move(x,y)

    def paintEvent(self,_):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        W,H=self.width(),self.height()
        clip=QPainterPath(); clip.addRoundedRect(0,0,W,H,R,R)
        p.setClipPath(clip); p.fillRect(0,0,W,H,C_BG)
        bar=QPainterPath(); bar.addRoundedRect(0,0,ABAR,H,1,1)
        g=QLinearGradient(0,0,0,H); g.setColorAt(0,C_AT); g.setColorAt(1,C_AB)
        p.fillPath(bar,g)
        p.setFont(self._font); p.setPen(C_TR)
        p.drawText(ABAR+PAD_H,0,W-ABAR-PAD_H*2,H,
                   Qt.AlignLeft|Qt.AlignVCenter|Qt.TextSingleLine,self._text)
        p.setClipping(False); p.setPen(C_BDR)
        brd=QPainterPath(); brd.addRoundedRect(.5,.5,W-1,H-1,R,R)
        p.drawPath(brd)

# ── Tray ─────────────────────────────────────────────────────────────────────
class Tray(QSystemTrayIcon):
    def __init__(self,icon,app):
        super().__init__(icon); self._app=app; self._enabled=True
        self.setToolTip("OverLex — Ctrl+Middle Click")
        self._menu=QMenu()
        self._a_on=QAction("✅  Активен"); self._a_on.setCheckable(True)
        self._a_on.setChecked(True); self._a_on.triggered.connect(self._toggle)
        self._menu.addAction(self._a_on); self._menu.addSeparator()
        self._a_auto=QAction("🚀  Автозапуск"); self._a_auto.setCheckable(True)
        self._a_auto.setChecked(_autostart_get())
        self._a_auto.triggered.connect(lambda c:_autostart_set(c))
        self._menu.addAction(self._a_auto); self._menu.addSeparator()
        self._a_quit=QAction("❌  Выйти")
        self._a_quit.triggered.connect(self._do_quit)
        self._menu.addAction(self._a_quit)
        self.setContextMenu(self._menu); self.show()
    def _toggle(self,on):
        self._enabled=on
        self._a_on.setText("✅  Активен" if on else "⏸  Пауза")
    def _do_quit(self): _log("[tray] выход"); self.hide(); self._app.quit()
    @property
    def enabled(self): return self._enabled

# ── Main ──────────────────────────────────────────────────────────────────────
_tray_ref=None
def _mc_guard(x,y,b,pressed):
    if _tray_ref and not _tray_ref.enabled: return
    _mc(x,y,b,pressed)

def main():
    global _tray_ref
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    app=QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    _tray_ref=Tray(_make_icon(),app)
    ov=Overlay(); bus.show.connect(ov.present); bus.hide_now.connect(ov.hide)
    kb=pkeyboard.Listener(on_press=_kp,on_release=_kr)
    ms=pmouse.Listener(on_click=_mc_guard)
    kb.daemon=ms.daemon=True; kb.start(); ms.start()
    _log("[main] слушатели OK")
    _tray_ref.showMessage("OverLex","Ctrl+Middle Click — перевод слова.",
                          QSystemTrayIcon.Information,2000)
    sys.exit(app.exec_())

if __name__=="__main__":
    main()
