# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, full-decode validation for untrusted product image uploads."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError


SUPPORTED_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "MPO": "image/jpeg",
    "WEBP": "image/webp",
}


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DecodedImage:
    media_type: str
    width: int
    height: int


def decode_image(content: bytes, *, max_pixels: int) -> DecodedImage:
    """Verify structure and decode all pixels without retaining decoded data."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened:
                detected = SUPPORTED_FORMATS.get(opened.format or "")
                if detected is None:
                    raise ImageValidationError(
                        "image_content_invalid", "Image format is malformed or unsupported"
                    )
                width, height = opened.size
                _validate_dimensions(width, height, max_pixels)
                frames=getattr(opened, "n_frames", 1)
                mpo=opened.format=='MPO'
                if frames != 1 and not mpo:
                    raise ImageValidationError(
                        "image_content_invalid", "Animated images are not supported"
                    )
                if mpo and not 1<=frames<=8:
                    raise ImageValidationError('image_content_invalid','MPO component count is invalid')
                opened.verify()

            # Pillow's verify() checks container integrity but does not decode pixels.
            # Reopen and load to force the codec to consume the full payload.
            with Image.open(BytesIO(content)) as decoded:
                if SUPPORTED_FORMATS.get(decoded.format or "") != detected:
                    raise ImageValidationError(
                        "image_content_invalid", "Image format changed during decoding"
                    )
                _validate_dimensions(decoded.width, decoded.height, max_pixels)
                decoded.load()
                if decoded.size != (width, height):
                    raise ImageValidationError(
                        "image_content_invalid", "Image dimensions changed during decoding"
                    )
                if mpo:
                    total=width*height
                    for index in range(1,frames):
                        decoded.seek(index)
                        _validate_dimensions(decoded.width,decoded.height,max_pixels)
                        total+=decoded.width*decoded.height
                        if total>max_pixels:
                            raise ImageValidationError('image_dimensions_invalid','Total MPO pixel count exceeds the limit')
                        decoded.load()
        return DecodedImage(detected, width, height)
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageValidationError(
            "image_dimensions_invalid", "Image pixel count exceeds the limit"
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, IndexError):
        raise ImageValidationError(
            "image_content_invalid", "Image content is malformed or cannot be decoded"
        ) from None


def _validate_dimensions(width: int, height: int, max_pixels: int) -> None:
    if width < 1 or height < 1:
        raise ImageValidationError("image_dimensions_invalid", "Image dimensions are invalid")
    if width * height > max_pixels:
        raise ImageValidationError(
            "image_dimensions_invalid", "Image pixel count exceeds the limit"
        )
