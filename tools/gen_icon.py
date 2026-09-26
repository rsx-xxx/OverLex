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
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# == Color: OKLCH, not raw RGB =================================================
#
# OKLCH (Björn Ottosson's OKLab, in cylindrical L/C/H form; standardized in CSS
# Color Module 4 and the default palette space for most current design systems)
# keeps perceived lightness and saturation constant while sweeping hue. A plain
# RGB gradient between a blue and a violet dips through a desaturated, muddier
# tone at its midpoint because sRGB isn't perceptually uniform; interpolating in
# OKLCH instead keeps the whole gradient uniformly vivid.
#
# Same hue family as before (blue -> violet), chroma picked as the largest value
# that stays in-gamut across the whole hue sweep (checked numerically) so no
# stop silently clips and distorts the intended lightness/chroma.
HUE_START, HUE_END = 258, 296     # degrees: vivid blue -> vivid violet
LIGHTNESS, CHROMA = 0.70, 0.155   # background gradient
ACCENT_L, ACCENT_C = 0.45, 0.16   # deeper shade for the in-pill accent marks

def oklch_to_srgb(L, C, h_deg):
    h = math.radians(h_deg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r_lin = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    def enc(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return tuple(round(enc(c) * 255) for c in (r_lin, g_lin, b_lin))

C_TOP = oklch_to_srgb(LIGHTNESS, CHROMA, HUE_START)
C_BOTTOM = oklch_to_srgb(LIGHTNESS, CHROMA, HUE_END)
C_ACCENT_DEEP = oklch_to_srgb(ACCENT_L, ACCENT_C, HUE_END)


def _diagonal_gradient(size: int, _n: int = 48) -> Image.Image:
    # Corner-to-corner (not just top-to-bottom) reads as more "modern angled
    # gradient" and matches how most current macOS/Windows tile icons shade.
    # A diagonal gradient is linear in (x+y), so rendering it small and letting
    # a bilinear resize upscale it looks identical to a full-resolution
    # per-pixel loop but without the O(size^2) Python cost at size=1024 - the
    # OKLCH conversion per pixel is the more expensive part this sidesteps.
    small = Image.new("RGB", (_n, _n))
    px = small.load()
    denom = max(1, 2 * (_n - 1))
    for y in range(_n):
        for x in range(_n):
            t = (x + y) / denom
            px[x, y] = oklch_to_srgb(LIGHTNESS, CHROMA, HUE_START + (HUE_END - HUE_START) * t)
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
                              radius=dash_h / 2, fill=(*C_ACCENT_DEEP, 255))

    # Soft drop shadow beneath the glyph (offset + blurred alpha silhouette) for a
    # touch of floating depth - flat-on-flat reads dated by current conventions.
    shadow = glyph.split()[-1].point(lambda v: int(v * 0.35))
    shadow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_layer.paste((0, 0, 0, 255), (0, 0), shadow)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(size * 0.02))
    offset = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset.paste(shadow_layer, (0, int(size * 0.015)))
    img = Image.alpha_composite(img, offset)

    img = Image.alpha_composite(img, glyph)
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
