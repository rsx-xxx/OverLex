#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

Dark squircle tile with a glowing viewfinder frame (echoing the in-app
region-select corner brackets) around a small card (echoing the actual dark
translated-text overlay, accent bar and all) - the same dark-surface +
neon-glow language the app itself uses, not a generic light gradient tile
that looks nothing like the real product. Depicts what OverLex specifically
does (select on screen -> get a translated caption) rather than a generic
translate-app trope.

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
# OKLCH instead keeps the whole gradient uniformly vivid - important here since
# the glow itself IS the icon's whole visual weight, not just a background wash.
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

# Deep near-black navy background - matches the app's own translucent dark
# overlay cards instead of a bright gradient tile that looks nothing like them.
C_BG_TOP = oklch_to_srgb(0.15, 0.035, HUE_START)
C_BG_BOTTOM = oklch_to_srgb(0.11, 0.03, HUE_END)
# Vivid glyph/glow gradient (max in-gamut chroma at this lightness, checked
# numerically across the whole hue sweep so nothing silently clips).
C_TOP = oklch_to_srgb(0.75, 0.128, HUE_START)
C_BOTTOM = oklch_to_srgb(0.75, 0.128, HUE_END)
# The little translated-text card echoed inside the frame.
C_CARD = oklch_to_srgb(0.26, 0.03, HUE_END)
C_CARD_TEXT = oklch_to_srgb(0.88, 0.01, HUE_END)


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

def _gradient_oklch(size: int, h0, h1, L, C, _n: int = 48) -> Image.Image:
    small = Image.new("RGB", (_n, _n))
    px = small.load()
    denom = max(1, 2 * (_n - 1))
    for y in range(_n):
        for x in range(_n):
            t = (x + y) / denom
            px[x, y] = oklch_to_srgb(L, C, h0 + (h1 - h0) * t)
    return small.resize((size, size), Image.BILINEAR)


def render(size: int) -> Image.Image:
    rr = int(size * 0.22)  # squircle corner radius
    bg_grad = _diagonal_gradient(size, C_BG_TOP, C_BG_BOTTOM)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=rr, fill=255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(bg_grad, (0, 0), mask)

    # Very subtle glass highlight in the upper-left - barely-there on a dark
    # surface, just enough to avoid a flat, lifeless black.
    highlight = Image.new("L", (size, size), 0)
    hd = ImageDraw.Draw(highlight)
    hd.ellipse([size * 0.05, -size * 0.25, size * 0.95, size * 0.55], fill=30)
    highlight = highlight.filter(ImageFilter.GaussianBlur(size * 0.08))
    glass = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    glass.putalpha(highlight)
    img = Image.alpha_composite(img, Image.composite(glass, Image.new("RGBA", (size, size), (0,0,0,0)), mask))

    # -- Glyph: viewfinder corner brackets, drawn as their own mask so the
    # vivid gradient and the glow can both be clipped to exactly this shape --
    glyph_mask = Image.new("L", (size, size), 0)
    gm = ImageDraw.Draw(glyph_mask)
    stroke = size * 0.075
    arm = size * 0.20
    inset = size * 0.17
    corners = [
        (inset, inset, 1, 1),
        (size - inset, inset, -1, 1),
        (inset, size - inset, 1, -1),
        (size - inset, size - inset, -1, -1),
    ]
    for cx, cy, dx, dy in corners:
        gm.line([(cx, cy), (cx + dx * arm, cy)], fill=255, width=int(stroke))
        gm.line([(cx, cy), (cx, cy + dy * arm)], fill=255, width=int(stroke))
        for px, py in ((cx, cy), (cx + dx * arm, cy), (cx, cy + dy * arm)):
            r = stroke / 2
            gm.ellipse([px - r, py - r, px + r, py + r], fill=255)

    # Neon glow behind the brackets - reads far more vividly against this dark
    # background than it ever could on a bright tile, which is the point.
    glow_src = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_src.paste(_gradient_oklch(size, HUE_START, HUE_END, 0.75, 0.128), (0, 0), glyph_mask)
    for blur, alpha in ((0.05, 235), (0.025, 235), (0.01, 255)):
        layer = glow_src.filter(ImageFilter.GaussianBlur(size * blur))
        r, g, b, a = layer.split()
        layer = Image.merge("RGBA", (r, g, b, a.point(lambda v: v * alpha // 255)))
        img = Image.alpha_composite(img, layer)

    # Crisp bracket fill on top of its own glow.
    bracket_fill = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bracket_fill.paste(_gradient_oklch(size, HUE_START, HUE_END, 0.86, 0.09), (0, 0), glyph_mask)
    img = Image.alpha_composite(img, bracket_fill)

    # -- Card: the app's actual translated-text overlay, echoed in miniature --
    card_w, card_h = size * 0.42, size * 0.165
    card_cx, card_cy = size * 0.5, size * 0.635
    card_box = [card_cx - card_w/2, card_cy - card_h/2, card_cx + card_w/2, card_cy + card_h/2]
    card_r = card_h * 0.32

    card_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(card_mask).rounded_rectangle(card_box, radius=card_r, fill=255)
    card_glow_src = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(card_glow_src).rounded_rectangle(card_box, radius=card_r, fill=(*C_TOP, 255))
    for blur, alpha in ((0.035, 130), (0.015, 150)):
        layer = card_glow_src.filter(ImageFilter.GaussianBlur(size * blur))
        r, g, b, a = layer.split()
        layer = Image.merge("RGBA", (r, g, b, a.point(lambda v: v * alpha // 255)))
        img = Image.alpha_composite(img, layer)

    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(card_box, radius=card_r, fill=(*C_CARD, 255))

    # left accent bar, same gradient as the frame - mirrors the app's real card style
    bar_w = card_h * 0.16
    bar_box = [card_box[0], card_box[1], card_box[0] + bar_w, card_box[3]]
    accent = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    accent.paste(_gradient_oklch(size, HUE_START, HUE_END, 0.75, 0.128), (0, 0), card_mask)
    accent_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(accent_mask).rounded_rectangle(bar_box, radius=bar_w/2, fill=255)
    card = Image.composite(accent, card, accent_mask)

    # light "text" dashes to the right of the accent bar - drawn onto the
    # reassigned card, not the pre-composite one, so they actually survive
    dash_h = card_h * 0.22
    cd = ImageDraw.Draw(card)
    for dx0, dw in ((0.20, 0.20), (0.44, 0.28), (0.76, 0.14)):
        x0 = card_box[0] + dx0 * card_w
        cd.rounded_rectangle([x0, card_cy - dash_h/2, x0 + dw*card_w, card_cy + dash_h/2],
                              radius=dash_h/2, fill=(*C_CARD_TEXT, 255))
    img = Image.alpha_composite(img, card)

    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
