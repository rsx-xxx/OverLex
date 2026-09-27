#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

Loads the real designed icon (tools/assets/icon_master.png, cropped from the
project's icon.jpg) and resizes it to whatever size is requested, rather than
procedurally drawing one - a real asset beats another generated attempt.

Usage: python tools/gen_icon.py <out.png> [size]
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_MASTER_PATH = Path(__file__).parent / "assets" / "icon_master.png"


def render(size: int) -> Image.Image:
    img = Image.open(_MASTER_PATH).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img


def _oklch_to_srgb(L, C, h_deg):
    h = math.radians(h_deg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r_lin = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

    return tuple(round(enc(c) * 255) for c in (r_lin, g_lin, b_lin))


def render_tray(size: int) -> Image.Image:
    """Bold, fully-opaque rendering for the small systray icon.

    icon_master.png is a soft translucent-glass design sized for a large app
    icon - at 16-24px its low contrast makes it nearly disappear against either
    a light or dark taskbar. The tray uses this solid rendering instead: same
    two-square motif, opaque OKLCH-picked colors and a dark outline so it reads
    against any taskbar background.
    """
    ss = 4  # supersample, then downsize, for clean edges at tiny final sizes
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    back_fill = _oklch_to_srgb(0.60, 0.17, 296) + (255,)   # vivid violet
    front_fill = _oklch_to_srgb(0.74, 0.15, 175) + (255,)  # vivid teal
    outline = (12, 12, 20, 235)

    r = int(s * 0.22)
    ow = max(2, int(s * 0.05))
    back = (int(s * 0.06), int(s * 0.06), int(s * 0.72), int(s * 0.72))
    front = (int(s * 0.30), int(s * 0.30), int(s * 0.94), int(s * 0.94))

    draw.rounded_rectangle(back, radius=r, fill=back_fill, outline=outline, width=ow)
    draw.rounded_rectangle(front, radius=r, fill=front_fill, outline=outline, width=ow)

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
