"""Journey images: loaded fixture photos, a generated fallback, and rejection files (#221).

Everything here is plain bytes built with the standard library. The valid images come
from the committed fixture folder when it has any, else from two small generated PNGs.
The rejection files are what the API refuses: a GIF, bytes no decoder accepts, and a
PNG whose header declares more pixels than the API allows (it compresses to a few KB).
"""

import binascii
import struct
import zlib
from pathlib import Path
from typing import Final

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_OVERSIZED_SIDE: Final = 5001


def _chunk(kind: bytes, body: bytes) -> bytes:
    crc = binascii.crc32(kind + body)
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def _png(width: int, height: int, depth: int, color: int, pixels: bytes) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(pixels))
        + _chunk(b"IEND", b"")
    )


def _solid_png(red: int, green: int, blue: int) -> bytes:
    side = 8
    row = b"\x00" + bytes((red, green, blue)) * side
    return _png(side, side, 8, 2, row * side)


def gif_bytes() -> bytes:
    """A minimal 1x1 GIF: a format the API does not accept."""
    return (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00"
        b"\x02\x02D\x01\x00;"
    )


def non_image_bytes() -> bytes:
    return b"this is not an image\n"


def oversized_png() -> bytes:
    """A valid 5001x5001 1-bit grayscale PNG: over the pixel limit, a few KB on the wire."""
    row = b"\x00" * (1 + (_OVERSIZED_SIDE + 7) // 8)
    return _png(_OVERSIZED_SIDE, _OVERSIZED_SIDE, 1, 0, row * _OVERSIZED_SIDE)


def fallback_pngs() -> tuple[bytes, bytes]:
    return _solid_png(200, 60, 60), _solid_png(60, 60, 200)


def content_type(image: bytes) -> str | None:
    """The upload content type for a PNG, JPEG, or WebP signature, else None."""
    if image.startswith(_PNG_SIGNATURE):
        return "image/png"
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return None


def load_fixture_images(directory: Path) -> tuple[bytes, bytes]:
    """Images A and B: the first two images of the folder in filename order, cycling.

    Only files with an image suffix and a PNG, JPEG, or WebP signature count. A folder
    with none, or one that cannot be read, gives the generated fallback instead of an
    error.
    """
    try:
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.suffix.lower() in _IMAGE_SUFFIXES and path.is_file()
        )
        images = [
            image
            for image in (path.read_bytes() for path in paths)
            if content_type(image)
        ]
        if images:
            return images[0], images[1 % len(images)]
    except OSError:
        pass
    return fallback_pngs()
