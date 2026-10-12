"""Fixture photos for simulation fursuits.

Committed images are used in sorted filename order, cycling. With none
committed, a deterministic generated PNG stands in.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Final

from django.core.files.base import ContentFile
from PIL import Image

IMAGE_DIRECTORY: Final = Path(__file__).resolve().parent / "images"
MAX_FIXTURE_IMAGE_BYTES: Final = 512 * 1024
MAX_FIXTURE_IMAGE_SIDE: Final = 2048

_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_GENERATED_SIDE: Final = 512


def _committed(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _SUFFIXES
    )


def _generated(position: int) -> ContentFile[bytes]:
    color = ((position * 67 + 40) % 256, (position * 131 + 90) % 256, 160)
    buffer = BytesIO()
    Image.new("RGB", (_GENERATED_SIDE, _GENERATED_SIDE), color).save(
        buffer, format="PNG"
    )
    return ContentFile(buffer.getvalue(), name=f"fixture-{position}.png")


def fixture_image(
    position: int, *, directory: Path = IMAGE_DIRECTORY
) -> ContentFile[bytes]:
    """Return the photo for the ``position``-th fursuit of a run."""
    committed = _committed(directory)
    if not committed:
        return _generated(position)
    path = committed[position % len(committed)]
    return ContentFile(path.read_bytes(), name=path.name)
