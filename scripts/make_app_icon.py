# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pack apps/twinpulse-desktop/icon.ico from a square PNG rendering of icon.svg.

    python scripts/make_app_icon.py <square PNG, 256 px or larger> <output .ico>

The PNG is any rasterisation of apps/twinpulse-desktop/icon.svg (the 2026-10-27 icon used a
1024 px render). Entries: 16, 24, 32, 48, 64 and 128 px as 32-bit BMP (BITMAPINFOHEADER with
the AND mask, the layout Windows shell code paths expect for small sizes) and 256 px as PNG.
Only Pillow is needed; @electron/packager (resedit) and PyInstaller copy the entries as-is.
"""
import struct
import sys
from pathlib import Path

from PIL import Image

BMP_SIZES = (16, 24, 32, 48, 64, 128)
PNG_SIZE = 256


def bmp_entry(image):
    width, height = image.size
    rgba = image.tobytes()
    rows = []
    for y in range(height - 1, -1, -1):  # bottom-up BGRA
        row = rgba[y * width * 4:(y + 1) * width * 4]
        rows.append(bytes(b for x in range(width) for b in (row[x * 4 + 2], row[x * 4 + 1], row[x * 4], row[x * 4 + 3])))
    pixels = b''.join(rows)
    stride = (width + 31) // 32 * 4
    mask = bytearray()
    for y in range(height - 1, -1, -1):
        bits = 0
        for x in range(width):
            if rgba[(y * width + x) * 4 + 3] == 0:
                bits |= 1 << (stride * 8 - 1 - x)
        mask += bits.to_bytes(stride, 'big')
    header = struct.pack('<IiiHHIIiiII', 40, width, height * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + bytes(mask)


def main(source, target):
    base = Image.open(source).convert('RGBA')
    if base.size[0] != base.size[1] or base.size[0] < PNG_SIZE:
        raise SystemExit('ICON_SOURCE_MUST_BE_SQUARE_AND_AT_LEAST_256')
    entries = []
    for size in BMP_SIZES:
        entries.append((size, 32, bmp_entry(base.resize((size, size), Image.LANCZOS))))
    from io import BytesIO
    buffer = BytesIO()
    base.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(buffer, format='PNG', optimize=True)
    entries.append((PNG_SIZE, 32, buffer.getvalue()))
    offset = 6 + 16 * len(entries)
    directory = struct.pack('<HHH', 0, 1, len(entries))
    body = b''
    for size, depth, data in entries:
        directory += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, depth, len(data), offset)
        body += data
        offset += len(data)
    Path(target).write_bytes(directory + body)
    print(f'{target}: {len(entries)} entries, {offset} bytes')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
