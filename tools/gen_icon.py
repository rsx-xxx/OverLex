#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

Loads the real designed icon (tools/assets/icon_master.png, cropped from the
project's icon.jpg) and resizes it to whatever size is requested, rather than
procedurally drawing one - a real asset beats another generated attempt.

Usage: python tools/gen_icon.py <out.png> [size]
"""
import sys
from pathlib import Path

from PIL import Image

_MASTER_PATH = Path(__file__).parent / "assets" / "icon_master.png"


def render(size: int) -> Image.Image:
    img = Image.open(_MASTER_PATH).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
