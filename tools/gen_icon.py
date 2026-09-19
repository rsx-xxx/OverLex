#!/usr/bin/env python3
"""Renders the OverLex app icon (gradient circle + "OL") to a PNG, for
build-time packaging into a Windows .ico / macOS .icns.

Usage: python tools/gen_icon.py <out.png> [size]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_BOLD_FONTS = ("Arial Bold.ttf", "arialbd.ttf", "Arial-BoldMT.ttf", "DejaVuSans-Bold.ttf")


def _bold_font(size: int) -> ImageFont.FreeTypeFont:
    for name in _BOLD_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    pad = max(1, size // 32)
    top, bottom = (48, 130, 255), (110, 65, 250)

    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel((0, y), tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3)))
    grad = grad.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([pad, pad, size - pad, size - pad], fill=255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    font = _bold_font(int(size * 0.38))
    text = "OL"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), text, font=font, fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    out.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(out)
