#!/usr/bin/env python3
"""Renders the OverLex app icon to a PNG, for build-time packaging into a
Windows .ico / macOS .icns, and for the runtime tray icon.

Squircle tile (matches modern Windows 11 / macOS app-icon conventions) with
an overlapping A/Я monogram - the same "two overlapping language glyphs"
grammar as Google Translate's icon, specialized to this app's EN->RU pair.

Usage: python tools/gen_icon.py <out.png> [size]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_BOLD_FONTS = ("Arial Bold.ttf", "arialbd.ttf", "Arial-BoldMT.ttf", "DejaVuSans-Bold.ttf")

C_TOP, C_BOTTOM = (48, 130, 255), (110, 65, 250)


def _bold_font(size: int) -> ImageFont.FreeTypeFont:
    for name in _BOLD_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


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

    def glyph_layer(text, font, cx, cy, alpha):
        # ImageDraw.text with a semi-transparent fill doesn't blend against the
        # destination - it just stores raw white RGB with a lowered alpha,
        # discarding whatever gradient color was underneath. Drawing solid onto
        # its own layer and alpha_composite-ing that in blends it properly.
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]
        d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        if alpha < 255:
            r, g, b, a = layer.split()
            layer = Image.merge("RGBA", (r, g, b, a.point(lambda v: v * alpha // 255)))
        return layer

    # Background glyph: muted "A" (source language), upper-left.
    f_back = _bold_font(int(size * 0.40))
    img = Image.alpha_composite(img, glyph_layer("A", f_back, size * 0.30, size * 0.38, 150))

    # Foreground glyph: solid "Я" (target language), lower-right, overlapping.
    f_front = _bold_font(int(size * 0.46))
    img = Image.alpha_composite(img, glyph_layer("Я", f_front, size * 0.62, size * 0.64, 255))

    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
