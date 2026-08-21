"""Safe, metadata-free normalization for uploaded still images."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from typing import Literal, NoReturn
from warnings import catch_warnings, simplefilter

from django.core.files import File
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


class ImageRejectionCode(StrEnum):
    FILE_TOO_LARGE = "file_too_large"
    INVALID_IMAGE = "invalid_image"
    UNSUPPORTED_FORMAT = "unsupported_format"
    ANIMATED_IMAGE = "animated_image"
    TOO_MANY_PIXELS = "too_many_pixels"


class ImageValidationError(ValueError):
    """A safe, stable rejection for an uploaded image."""

    def __init__(self, code: ImageRejectionCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    content: bytes
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    extension: Literal["jpg", "png", "webp"]
    width: int
    height: int


_OUTPUT_FORMATS: dict[
    str,
    tuple[
        Literal["JPEG", "PNG", "WEBP"],
        Literal["image/jpeg", "image/png", "image/webp"],
        Literal["jpg", "png", "webp"],
    ],
] = {
    "JPEG": ("JPEG", "image/jpeg", "jpg"),
    "PNG": ("PNG", "image/png", "png"),
    "WEBP": ("WEBP", "image/webp", "webp"),
}


def _reject(code: ImageRejectionCode) -> NoReturn:
    raise ImageValidationError(code)


def _read_upload(upload: File[bytes]) -> bytes:
    content = bytearray()
    while len(content) <= MAX_IMAGE_BYTES:
        chunk = upload.read(MAX_IMAGE_BYTES + 1 - len(content))
        if not chunk:
            break
        content.extend(chunk)

    if len(content) > MAX_IMAGE_BYTES:
        _reject(ImageRejectionCode.FILE_TOO_LARGE)
    return bytes(content)


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or "transparency" in image.info


def _has_disallowed_content_signature(content: bytes) -> bool:
    """Recognize only explicitly disallowed, non-raster content types."""
    if content.startswith((b"%PDF-", b"GIF87a", b"GIF89a")):
        return True

    if content[4:8] == b"ftyp" and content[8:12] in {
        b"avif",
        b"avis",
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
    }:
        return True

    leading_content = content.removeprefix(b"\xef\xbb\xbf").lstrip()
    if not leading_content.startswith(b"<svg"):
        return False

    root_boundary = leading_content[4:5]
    return (
        root_boundary in {b" ", b"\t", b"\r", b"\n", b"/", b">"}
        and b">" in leading_content[:4096]
    )


def _has_accepted_raster_signature(content: bytes) -> bool:
    return content.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) or (
        content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    )


def _save(image: Image.Image, image_format: Literal["JPEG", "PNG", "WEBP"]) -> bytes:
    destination = BytesIO()
    if image_format == "JPEG":
        image.save(
            destination,
            format="JPEG",
            quality=85,
            subsampling=0,
            optimize=False,
            progressive=False,
        )
    elif image_format == "PNG":
        image.save(destination, format="PNG", compress_level=6, optimize=False)
    else:
        image.save(destination, format="WEBP", quality=85, method=4)
    return destination.getvalue()


def normalize_image(upload: File[bytes]) -> NormalizedImage:
    """Decode a supported still image and return a canonical re-encoding."""
    content = _read_upload(upload)
    if _has_disallowed_content_signature(content):
        _reject(ImageRejectionCode.UNSUPPORTED_FORMAT)
    if not _has_accepted_raster_signature(content):
        _reject(ImageRejectionCode.INVALID_IMAGE)

    try:
        with catch_warnings():
            simplefilter("error")
            with Image.open(
                BytesIO(content), formats=("JPEG", "PNG", "WEBP")
            ) as source:
                source_format = source.format
                if source_format is None or source_format not in _OUTPUT_FORMATS:
                    _reject(ImageRejectionCode.UNSUPPORTED_FORMAT)
                if getattr(source, "n_frames", 1) != 1:
                    _reject(ImageRejectionCode.ANIMATED_IMAGE)

                width, height = source.size
                if width * height > MAX_IMAGE_PIXELS:
                    _reject(ImageRejectionCode.TOO_MANY_PIXELS)

                source.load()
                mode = "RGBA" if _has_alpha(source) else "RGB"
                ImageOps.exif_transpose(source, in_place=True)
                pixels = source.convert(mode)
                pixels.info.clear()

        output_format, content_type, extension = _OUTPUT_FORMATS[source_format]
        normalized = _save(pixels, output_format)
        return NormalizedImage(
            content=normalized,
            content_type=content_type,
            extension=extension,
            width=pixels.width,
            height=pixels.height,
        )
    except ImageValidationError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        _reject(ImageRejectionCode.TOO_MANY_PIXELS)
    except Warning:
        _reject(ImageRejectionCode.INVALID_IMAGE)
    except UnidentifiedImageError:
        if _has_disallowed_content_signature(content):
            _reject(ImageRejectionCode.UNSUPPORTED_FORMAT)
        _reject(ImageRejectionCode.INVALID_IMAGE)
    except (OSError, SyntaxError, ValueError):
        _reject(ImageRejectionCode.INVALID_IMAGE)
