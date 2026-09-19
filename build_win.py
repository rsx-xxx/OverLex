"""python build_win.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tools.gen_icon import render

ROOT = Path(__file__).parent

# Unused Qt modules - removing these cuts bundle size significantly
EXCLUDE = [
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
    "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtLocation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtDesigner", "PySide6.QtTest",
    "PySide6.QtXml", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DAnimation",
    "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtCharts",
]
COLLECT = ["PIL", "mss", "pynput"]
HIDDEN = [
    "pynput.keyboard._win32", "pynput.mouse._win32",
    "pynput.keyboard._base", "pynput.mouse._base", "winreg",
]


def _version_tuple(v: str):
    nums = [int(p) if p.isdigit() else 0 for p in v.split("+")[0].split("-")[0].split(".")][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def _write_version_file(path: Path, version: str) -> None:
    vt = _version_tuple(version)
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'OverLex'),
         StringStruct('FileDescription', 'OverLex - Screen Translation Overlay'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'OverLex'),
         StringStruct('OriginalFilename', 'OverLex.exe'),
         StringStruct('ProductName', 'OverLex'),
         StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)""", encoding="utf-8")


if __name__ == "__main__":
    import subprocess

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)

    icon_ico = build_dir / "icon.ico"
    render(256).save(icon_ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    version = os.environ.get("OVERLEX_VERSION", "0.0.0.0").lstrip("vV")
    version_file = build_dir / "version_info.txt"
    _write_version_file(version_file, version)

    flags = ["--icon", str(icon_ico), "--version-file", str(version_file)]
    for p in COLLECT: flags += ["--collect-all", p]
    for h in HIDDEN: flags += ["--hidden-import", h]
    for e in EXCLUDE: flags += ["--exclude-module", e]

    ps = ROOT / "_ocr_helper.ps1"
    if ps.exists(): flags += ["--add-data", f"{ps};."]

    cmd = [sys.executable, "-m", "PyInstaller",
           "--onedir", "--noconsole", "--name", "OverLex", "--noconfirm",
           *flags, "overlex.py"]

    print(f"[build] PyInstaller with {len(EXCLUDE)} excluded Qt modules, version {version}...")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode == 0:
        size = sum(f.stat().st_size for f in (ROOT / "dist" / "OverLex").rglob("*") if f.is_file())
        print(f"\n[OK] dist/OverLex/OverLex.exe  ({size // 1024 // 1024} MB)")
    else:
        sys.exit(r.returncode)
