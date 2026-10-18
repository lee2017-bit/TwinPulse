# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Send the visible primary photograph from MPO; keep the immutable upload intact."""
from io import BytesIO


def image_payload(image):
    content=image.content
    # Ordinary JPEG/PNG/WebP and provider boundary fixtures remain byte-exact.
    if image.mime_type!='image/jpeg' or b'MPF\0' not in content[:65536]:
        return image.mime_type,content
    from PIL import Image, ImageOps
    with Image.open(BytesIO(content)) as opened:
        if opened.format!='MPO':
            return image.mime_type,content
        if not 1<=opened.n_frames<=8 or opened.width*opened.height>40_000_000:
            raise ValueError('MPO primary image exceeds the supported resource bound')
        opened.seek(0)
        primary=ImageOps.exif_transpose(opened).convert('RGB')
        output=BytesIO()
        primary.save(output,format='JPEG',quality=95)
        return 'image/jpeg',output.getvalue()
