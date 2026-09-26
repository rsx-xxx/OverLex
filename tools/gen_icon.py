#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

Squircle tile (matches modern Windows 11 / macOS app-icon conventions) depicting
the app's actual mechanic instead of a generic language monogram: a viewfinder/
selection frame (four corner brackets, echoing the in-app region-select frame)
around a small caption pill (echoing the translated-text overlay that appears).
Select-a-region-of-screen -> get-a-translated-caption is what makes this app
different from any other translator, so the icon shows exactly that, not a
generic "two letters" translate-app trope.

Usage: python tools/gen_icon.py <out.png> [size]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

C_TOP, C_BOTTOM = (48, 130, 255), (110, 65, 250)


def _diagonal_gradient(size: int, _n: int = 48) -> Image.Image:
    # Corner-to-corner (not just top-to-bottom) reads as more "modern angled
    # gradient" and matches how most current macOS/Windows tile icons shade.
    # A diagonal linear gradient is linear in (x+y), so rendering it small and
    # letting a bilinear resize upscale it looks identical to a full-resolution
    # per-pixel loop but without the O(size^2) Python cost at size=1024.
    small = Image.new("RGB", (_n, _n))
    px = small.load()
    denom = max(1, 2 * (_n - 1))
    for y in range(_n):
        for x in range(_n):
            t = (x + y) / denom
            px[x, y] = tuple(int(C_TOP[c] + (C_BOTTOM[c] - C_TOP[c]) * t) for c in range(3))
    return small.resize((size, size), Image.BILINEAR)


def render(size: int) -> Image.Image:
    rr = int(size * 0.22)  # squircle corner radius
    grad = _diagonal_gradient(size)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=rr, fill=255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # Soft glass highlight in the upper-left, for a touch of depth without
    # looking dated/skeuomorphic.
    highlight = Image.new("L", (size, size), 0)
    hd = ImageDraw.Draw(highlight)
    hd.ellipse([size * 0.05, -size * 0.25, size * 0.95, size * 0.55], fill=70)
    highlight = highlight.filter(ImageFilter.GaussianBlur(size * 0.06))
    glass = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    glass.putalpha(highlight)
    img = Image.alpha_composite(img, Image.composite(glass, Image.new("RGBA", (size, size), (0,0,0,0)), mask))

    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)

    stroke = size * 0.075
    arm = size * 0.19
    inset = size * 0.19
    corners = [
        (inset, inset, 1, 1),                      # top-left, arms point right/down
        (size - inset, inset, -1, 1),               # top-right, arms point left/down
        (inset, size - inset, 1, -1),               # bottom-left, arms point right/up
        (size - inset, size - inset, -1, -1),       # bottom-right, arms point left/up
    ]
    for cx, cy, dx, dy in corners:
        gd.line([(cx, cy), (cx + dx * arm, cy)], fill=(255, 255, 255, 255), width=int(stroke))
        gd.line([(cx, cy), (cx, cy + dy * arm)], fill=(255, 255, 255, 255), width=int(stroke))
        for px, py in ((cx, cy), (cx + dx * arm, cy), (cx, cy + dy * arm)):
            r = stroke / 2
            gd.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, 255))

    # Caption pill: echoes the translated-text overlay the app actually shows,
    # sitting where a real result would appear inside the selected frame.
    pill_w, pill_h = size * 0.40, size * 0.155
    pill_cx, pill_cy = size * 0.5, size * 0.635
    pill_box = [pill_cx - pill_w / 2, pill_cy - pill_h / 2, pill_cx + pill_w / 2, pill_cy + pill_h / 2]
    gd.rounded_rectangle(pill_box, radius=pill_h / 2, fill=(255, 255, 255, 255))

    # Tiny accent dashes inside the pill, standing in for illegible micro-text -
    # dark enough to read against the white pill without trying to render real letters.
    dash_y = pill_cy
    dash_h = pill_h * 0.22
    for dx0, dw in ((-0.28, 0.22), (-0.02, 0.30), (0.32, 0.16)):
        x0 = pill_cx + dx0 * pill_w
        gd.rounded_rectangle([x0, dash_y - dash_h / 2, x0 + dw * pill_w, dash_y + dash_h / 2],
                              radius=dash_h / 2, fill=(90, 70, 200, 255))

    img = Image.alpha_composite(img, glyph)
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
