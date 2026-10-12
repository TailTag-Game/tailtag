"""The generated and loaded journey images are what the API expects (#221 J-7).

Names this file relies on, all in `tailtag_simulator.images` and stdlib-only:

    gif_bytes() -> bytes                  a minimal GIF
    non_image_bytes() -> bytes            a short byte string no image sniffer accepts
    oversized_png() -> bytes              a valid 5001x5001 1-bit PNG
    fallback_pngs() -> tuple[bytes, bytes]   two distinct small valid PNGs
    load_fixture_images(directory: Path) -> tuple[bytes, bytes]
        images A and B: the first two image files (by signature) in sorted filename
        order, cycling, or
        `fallback_pngs()` when the folder is empty or cannot be read
"""

import struct
import zlib
from pathlib import Path

import pytest

from tailtag_simulator.images import (
    fallback_pngs,
    gif_bytes,
    load_fixture_images,
    non_image_bytes,
    oversized_png,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def decode_png(data: bytes) -> tuple[int, int]:
    """Check the PNG is intact (chunk CRCs, pixel data size) and return its size."""
    assert data.startswith(PNG_SIGNATURE)
    position = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(
            ">I", data[position + 8 + length : position + 12 + length]
        )
        assert crc == zlib.crc32(kind + body)
        chunks.append((kind, body))
        position += 12 + length
    assert chunks[0][0] == b"IHDR"
    assert chunks[-1][0] == b"IEND"
    width, height, depth, color = struct.unpack(">IIBB", chunks[0][1][:10])
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    row = 1 + (width * channels * depth + 7) // 8
    pixels = zlib.decompress(b"".join(b for k, b in chunks if k == b"IDAT"))
    assert len(pixels) == row * height
    return width, height


def test_rejection_images_are_what_the_api_rejects() -> None:
    assert gif_bytes().startswith((b"GIF87a", b"GIF89a"))
    assert decode_png(oversized_png()) == (5001, 5001)
    assert len(oversized_png()) < 100_000  # a few KB, not a 25 MB upload
    junk = non_image_bytes()
    assert junk and not junk.startswith(
        (PNG_SIGNATURE, b"\xff\xd8\xff", b"GIF8", b"RIFF")
    )


def test_fallback_images_are_two_distinct_valid_pngs() -> None:
    first, second = fallback_pngs()

    assert first != second
    assert decode_png(first)[0] > 0 and decode_png(second)[0] > 0


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["b.png", "c.png", "a.png"], ("a", "b")),
        (["only.png"], ("o", "o")),
        # "junk.png" has an image suffix but no image signature, so it is skipped
        (["junk.png", "k.png"], ("k", "k")),
    ],
)
def test_fixture_images_come_from_sorted_filenames_cycling(
    tmp_path: Path, names: list[str], expected: tuple[str, str]
) -> None:
    for name in names:
        signature = b"" if name.startswith("junk") else PNG_SIGNATURE
        (tmp_path / name).write_bytes(signature + name[0].encode())

    assert load_fixture_images(tmp_path) == tuple(
        PNG_SIGNATURE + letter.encode() for letter in expected
    )


@pytest.mark.parametrize("folder", ["empty", "missing"])
def test_the_generated_fallback_is_used_when_the_folder_has_no_images(
    tmp_path: Path, folder: str
) -> None:
    directory = tmp_path if folder == "empty" else tmp_path / "absent"

    assert load_fixture_images(directory) == fallback_pngs()
