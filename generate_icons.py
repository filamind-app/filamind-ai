#!/usr/bin/env python3
"""Professional SaynologyAI app icon — rounded-square base with chat-bubble + AI spark.

Design:
- Rounded-square base in modern app icon style
- Indigo→purple vertical gradient (matches AI/ML conventions)
- Central white chat bubble with a 4-point AI "spark" glyph
- Subtle inner shadow for depth
"""
import os
import sys
import base64

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "Pillow"])
    from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/saynologyai_icons"
os.makedirs(OUT_DIR, exist_ok=True)

# Brand palette
TOP    = (99, 102, 241, 255)    # indigo-500
BOTTOM = (139, 92, 246, 255)    # violet-500
ACCENT = (236, 72, 153, 255)    # pink-500 (sparkle)
WHITE  = (255, 255, 255, 255)


def gradient_fill(size):
    """Return an RGBA image with a vertical indigo→violet gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(TOP[0] * (1 - t) + BOTTOM[0] * t)
        g = int(TOP[1] * (1 - t) + BOTTOM[1] * t)
        b = int(TOP[2] * (1 - t) + BOTTOM[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    return img


def rounded_mask(size, radius_ratio=0.22):
    """Solid white rounded-square mask, alpha channel only."""
    radius = int(size * radius_ratio)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def draw_chat_bubble(draw, size):
    """Draw a centered chat bubble shape filled white."""
    # Bubble body
    pad = int(size * 0.22)
    bubble_box = (pad, pad, size - pad, int(size * 0.72))
    radius = int(size * 0.14)
    draw.rounded_rectangle(bubble_box, radius=radius, fill=WHITE)

    # Tail (triangle bottom-left of bubble)
    tail_w = int(size * 0.10)
    tail_h = int(size * 0.10)
    tx = int(size * 0.30)
    ty = int(size * 0.70)
    draw.polygon(
        [
            (tx, ty),
            (tx + tail_w, ty),
            (tx + tail_w // 2, ty + tail_h),
        ],
        fill=WHITE,
    )


def draw_spark(draw, size, cx, cy, r, color):
    """4-point star (sparkle) glyph centered at (cx, cy)."""
    # Vertical diamond
    draw.polygon(
        [(cx, cy - r), (cx + r // 3, cy), (cx, cy + r), (cx - r // 3, cy)],
        fill=color,
    )
    # Horizontal diamond
    draw.polygon(
        [(cx - r, cy), (cx, cy - r // 3), (cx + r, cy), (cx, cy + r // 3)],
        fill=color,
    )


def make_icon(size):
    # 1. Gradient + rounded mask = base
    grad = gradient_fill(size)
    mask = rounded_mask(size)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(grad, (0, 0), mask)

    # 2. Inner shadow ring for depth
    glow_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(glow_mask).rounded_rectangle(
        (1, 1, size - 2, size - 2),
        radius=int(size * 0.22),
        outline=140,
        width=max(1, size // 64),
    )
    glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(radius=max(1, size / 64)))
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow.putalpha(glow_mask)
    base.alpha_composite(shadow)

    # 3. Chat bubble + sparkle
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    draw_chat_bubble(d, size)

    # Sparkle inside bubble
    spark_r = max(2, int(size * 0.12))
    draw_spark(d, size, size // 2, int(size * 0.46), spark_r, (99, 102, 241, 255))

    # Small accent sparkle (top-right corner of bubble)
    if size >= 32:
        small_r = max(2, int(size * 0.07))
        draw_spark(
            d, size,
            int(size * 0.70),
            int(size * 0.34),
            small_r,
            ACCENT,
        )

    base.alpha_composite(layer)
    return base


sizes = [16, 24, 32, 48, 64, 72, 96, 128, 256]
for sz in sizes:
    icon = make_icon(sz)
    p = os.path.join(OUT_DIR, f"SaynologyAI-{sz}.png")
    icon.save(p, "PNG", optimize=True)
    print(f"  {p}  ({os.path.getsize(p)} bytes)")

# base64 for INFO file (64x64 and 256x256)
for sz in (64, 256):
    p = os.path.join(OUT_DIR, f"SaynologyAI-{sz}.png")
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    with open(os.path.join(OUT_DIR, f"icon_{sz}.b64"), "w") as f:
        f.write(b64)
print("  + icon_64.b64 / icon_256.b64 (for INFO)")
