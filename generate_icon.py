#!/usr/bin/env python3
"""Generate valid 64x64 + 256x256 PNG icons for DSM 7.2."""
import base64
import struct
import zlib
import sys

def png_chunk(typ, data):
    crc = zlib.crc32(typ + data) & 0xffffffff
    return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", crc)

def make_icon(size):
    img = bytearray()
    cx, cy = size // 2, size // 2
    inner_r = int(size * 0.35)
    ring_r = int(size * 0.45)
    for y in range(size):
        img.append(0)
        for x in range(size):
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if d2 < inner_r * inner_r:
                r, g, b, a = 138, 43, 226, 255
            elif d2 < ring_r * ring_r:
                r, g, b, a = 95, 158, 255, 255
            else:
                r, g, b, a = 30, 41, 59, 255
            img.extend([r, g, b, a])

    raw = bytes(img)
    compressed = zlib.compress(raw, 9)
    png = b'\x89PNG\r\n\x1a\n'
    png += png_chunk(b'IHDR', struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += png_chunk(b'IDAT', compressed)
    png += png_chunk(b'IEND', b'')
    return png

if __name__ == "__main__":
    for size in (64, 256):
        png_bytes = make_icon(size)
        b64 = base64.b64encode(png_bytes).decode('ascii')
        with open(f"/tmp/icon_{size}.b64", "w") as f:
            f.write(b64)
        print(f"Icon {size}x{size}: {len(png_bytes)} bytes raw, {len(b64)} chars base64")
