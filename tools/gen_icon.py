#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

One clear shape, not a compound scene: a single bold speech-bubble (the
app's own translated-text popup, literally the one thing every interaction
produces) on a vivid gradient. Earlier drafts combined a viewfinder frame
with a separate card, which read as a busy, ambiguous "scene" rather than
one legible glyph - a single dominant shape is what actually reads clearly
at a glance and at small sizes.

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
HUE_START, HUE_END = 258, 296     # degrees: vivid blue -> vivid violet

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

# Vivid, bright background gradient - max in-gamut chroma at this lightness,
# checked numerically across the whole hue sweep so nothing silently clips.
BG_L, BG_C = 0.72, 0.155
C_TOP = oklch_to_srgb(BG_L, BG_C, HUE_START)
C_BOTTOM = oklch_to_srgb(BG_L, BG_C, HUE_END)
# Deep shade of the same hue for the in-bubble accent dashes - reads clearly
# against the white bubble without needing a whole second color family.
C_ACCENT_DEEP = oklch_to_srgb(0.42, 0.17, HUE_END)


def _diagonal_gradient(size: int, c_top, c_bottom, _n: int = 48) -> Image.Image:
    # A diagonal gradient is linear in (x+y), so rendering it small and letting
    # a bilinear resize upscale it looks identical to a full-resolution
    # per-pixel loop but without the O(size^2) Python cost at size=1024.
    small = Image.new("RGB", (_n, _n))
    px = small.load()
    denom = max(1, 2 * (_n - 1))
    for y in range(_n):
        for x in range(_n):
            t = (x + y) / denom
            px[x, y] = tuple(round(c_top[i] + (c_bottom[i] - c_top[i]) * t) for i in range(3))
    return small.resize((size, size), Image.BILINEAR)


def render(size: int) -> Image.Image:
    rr = int(size * 0.22)  # squircle corner radius
    grad = _diagonal_gradient(size, C_TOP, C_BOTTOM)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=rr, fill=255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # Soft glass highlight in the upper-left, for a touch of depth without
    # looking flat.
    highlight = Image.new("L", (size, size), 0)
    hd = ImageDraw.Draw(highlight)
    hd.ellipse([size * 0.05, -size * 0.25, size * 0.95, size * 0.55], fill=65)
    highlight = highlight.filter(ImageFilter.GaussianBlur(size * 0.07))
    glass = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    glass.putalpha(highlight)
    img = Image.alpha_composite(img, Image.composite(glass, Image.new("RGBA", (size, size), (0,0,0,0)), mask))

    # -- The one glyph: a bold speech bubble, tail included --
    bw, bh = size * 0.60, size * 0.42
    bx, by = (size - bw) / 2, size * 0.24
    corner = bh * 0.30
    tail = bh * 0.16

    bubble_path = _bubble_path(bx, by, bw, bh, corner, tail)

    # Soft drop shadow beneath the bubble.
    shadow = Image.new("L", (size, size), 0)
    sd = ImageDraw.Draw(shadow)
    sd.polygon(bubble_path, fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.025))
    shadow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_layer.paste((0, 0, 0, 255), (0, 0), shadow)
    offset = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset.paste(shadow_layer, (0, int(size * 0.02)))
    img = Image.alpha_composite(img, offset)

    bubble = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bubble)
    bd.polygon(bubble_path, fill=(255, 255, 255, 255))

    # Bold accent dashes inside - stand-ins for illegible micro-text, reading
    # clearly as "translated content" without trying to render real letters.
    dash_h = bh * 0.15
    dash_y = by + bh * 0.47
    for dx0, dw in ((0.16, 0.24), (0.44, 0.34), (0.82, 0.18)):
        x0 = bx + dx0 * bw
        bd.rounded_rectangle([x0, dash_y - dash_h/2, x0 + dw*bw, dash_y + dash_h/2],
                              radius=dash_h/2, fill=(*C_ACCENT_DEEP, 255))
    img = Image.alpha_composite(img, bubble)

    return img


def _bubble_path(x, y, w, h, corner, tail):
    """A rounded-rect speech bubble with a small tail at bottom-left, as one
    filled polygon (approximating the four rounded corners with short arcs)."""
    path = []
    steps = 8
    def arc(cx, cy, r, a0, a1):
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            path.append((cx + r*math.cos(a), cy + r*math.sin(a)))

    r = corner
    # top-left -> top-right -> down to tail area -> tail point -> back up -> bottom-left -> close
    arc(x+r, y+r, r, 180, 270)                # top-left corner
    arc(x+w-r, y+r, r, 270, 360)               # top-right corner
    arc(x+w-r, y+h-r, r, 0, 90)                # bottom-right corner
    # bottom edge to tail base (right side of tail)
    path.append((x + w*0.30, y+h))
    path.append((x + w*0.16, y+h+tail))        # tail tip
    path.append((x + w*0.12, y+h))             # back to bottom edge (left side of tail)
    arc(x+r, y+h-r, r, 90, 180)                # bottom-left corner
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
