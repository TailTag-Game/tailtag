"""Acceptance contract for server-controlled image normalization."""

from __future__ import annotations

from io import BytesIO
from struct import pack
from typing import Literal
from zlib import crc32

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, PngImagePlugin

from media.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    ImageRejectionCode,
    ImageValidationError,
    NormalizedImage,
    normalize_image,
)

ImageFormat = Literal["JPEG", "PNG", "WEBP"]


def image_bytes(
    image_format: ImageFormat,
    *,
    size: tuple[int, int] = (2, 3),
    **save_kwargs: object,
) -> bytes:
    """Create a valid image without a checked-in binary fixture."""
    image = Image.new("RGB", size, color=(12, 34, 56))
    if size == (2, 3):
        image.putdata(
            (
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (255, 255, 255),
                (0, 0, 0),
                (255, 255, 0),
            )
        )
    destination = BytesIO()
    image.save(destination, format=image_format, **save_kwargs)
    return destination.getvalue()


def tagged_image_bytes(image_format: ImageFormat) -> bytes:
    """Make a valid source that cannot itself be the canonical stored object."""
    exif = Image.Exif()
    exif[315] = "source-software-sentinel"
    if image_format == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Source", "metadata-sentinel")
        return image_bytes("PNG", pnginfo=metadata, exif=exif.tobytes())
    return image_bytes(image_format, exif=exif.tobytes())


def decoded_rgb(content: bytes) -> Image.Image:
    """Return a fully decoded display image detached from its source stream."""
    with Image.open(BytesIO(content)) as decoded:
        decoded.load()
        return decoded.convert("RGB").copy()


def assert_display_pixels_preserved(
    actual_content: bytes, expected: Image.Image
) -> None:
    """Reject blank/corrupt output while allowing expected lossy codec rounding."""
    actual = decoded_rgb(actual_content)
    assert actual.size == expected.size
    for actual_pixel, expected_pixel in zip(
        actual.getdata(), expected.getdata(), strict=True
    ):
        assert all(
            abs(actual_channel - expected_channel) <= 48
            for actual_channel, expected_channel in zip(
                actual_pixel, expected_pixel, strict=True
            )
        )


def upload(
    content: bytes,
    *,
    name: str = "source.bin",
    content_type: str = "application/octet-stream",
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


def assert_rejected(source: SimpleUploadedFile) -> ImageValidationError:
    """Require a domain-level, stable rejection rather than Pillow diagnostics."""
    with pytest.raises(ImageValidationError) as raised:
        normalize_image(source)

    error = raised.value
    assert type(error.code) is ImageRejectionCode
    assert error.code.value
    return error


@pytest.mark.parametrize(
    ("image_format", "content_type", "extension"),
    (
        ("JPEG", "image/jpeg", "jpg"),
        ("PNG", "image/png", "png"),
        ("WEBP", "image/webp", "webp"),
    ),
)
def test_normalize_image_returns_decoded_format_not_filename_or_claimed_mime_type(
    image_format: ImageFormat, content_type: str, extension: str
) -> None:
    """Decoded content, rather than upload labels, defines canonical media identity."""
    source = tagged_image_bytes(image_format)
    normalized = normalize_image(
        upload(
            source,
            name="misleading-name.svg",
            content_type="image/svg+xml",
        )
    )

    assert normalized == NormalizedImage(
        content=normalized.content,
        content_type=content_type,
        extension=extension,
        width=2,
        height=3,
    )
    assert normalized.content != source
    assert_display_pixels_preserved(normalized.content, decoded_rgb(source))


def test_normalize_image_applies_exif_orientation_and_replaces_source_bytes() -> None:
    image = Image.new("RGB", (3, 2), color=(12, 34, 56))
    image.putdata(
        (
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 255),
            (0, 0, 0),
            (255, 255, 0),
        )
    )
    exif = Image.Exif()
    exif[274] = 6
    source = BytesIO()
    image.save(source, format="JPEG", exif=exif)

    normalized = normalize_image(upload(source.getvalue(), name="camera.jpeg"))

    assert normalized.width == 2
    assert normalized.height == 3
    assert normalized.content != source.getvalue()
    with Image.open(BytesIO(source.getvalue())) as decoded_source:
        expected_display = ImageOps.exif_transpose(decoded_source).convert("RGB").copy()
    with Image.open(BytesIO(normalized.content)) as normalized_image:
        assert normalized_image.getexif().get(274) is None
    assert_display_pixels_preserved(normalized.content, expected_display)


def test_normalize_image_removes_source_metadata_and_unparsed_source_tail() -> None:
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "source-comment-sentinel")
    metadata.add_text("XML:com.adobe.xmp", "source-xmp-sentinel")
    exif = Image.Exif()
    exif[315] = "source-exif-sentinel"
    source_icc_profile = b"source-icc-sentinel"
    source = (
        image_bytes(
            "PNG",
            pnginfo=metadata,
            exif=exif.tobytes(),
            icc_profile=source_icc_profile,
        )
        + b"source-byte-tail-sentinel"
    )

    for marker in (
        b"source-comment-sentinel",
        b"source-xmp-sentinel",
        b"source-exif-sentinel",
    ):
        assert marker in source
    with Image.open(BytesIO(source)) as decoded_source:
        assert decoded_source.info["icc_profile"] == source_icc_profile

    normalized = normalize_image(upload(source, name="metadata.png"))

    for source_marker in (
        b"source-comment-sentinel",
        b"source-xmp-sentinel",
        b"source-exif-sentinel",
        b"source-byte-tail-sentinel",
    ):
        assert source_marker not in normalized.content
    with Image.open(BytesIO(normalized.content)) as decoded:
        assert decoded.getexif() == {}
        assert "icc_profile" not in decoded.info
        assert "Comment" not in decoded.info
        assert "XML:com.adobe.xmp" not in decoded.info


def append_png_text_chunk(source: bytes, target_size: int) -> bytes:
    """Pad a generated PNG to an exact valid byte size with an ancillary chunk."""
    assert source.startswith(b"\x89PNG\r\n\x1a\n")
    payload_size = target_size - len(source) - 12
    assert payload_size > len(b"padding\x00")
    payload = b"padding\x00" + (b"x" * (payload_size - len(b"padding\x00")))
    chunk_type = b"tEXt"
    chunk = (
        pack(">I", len(payload))
        + chunk_type
        + payload
        + pack(">I", crc32(chunk_type + payload) & 0xFFFFFFFF)
    )
    return source[:-12] + chunk + source[-12:]


def test_normalize_image_accepts_exact_byte_limit_and_rejects_one_byte_more() -> None:
    source = image_bytes("PNG")
    exact_limit = append_png_text_chunk(source, MAX_IMAGE_BYTES)

    normalized = normalize_image(upload(exact_limit, name="limit.png"))

    assert len(exact_limit) == MAX_IMAGE_BYTES == 10 * 1024 * 1024
    assert normalized.content_type == "image/png"
    assert_rejected(upload(exact_limit + b"x", name="too-large.png"))


def test_normalize_image_accepts_exact_pixel_limit_and_rejects_one_pixel_more() -> None:
    exact_limit = image_bytes("PNG", size=(5_000, 5_000))
    one_pixel_more = image_bytes("PNG", size=(5_000, 5_001))

    normalized = normalize_image(upload(exact_limit, name="pixel-limit.png"))

    assert MAX_IMAGE_PIXELS == 25_000_000
    assert normalized.width * normalized.height == MAX_IMAGE_PIXELS
    assert_rejected(upload(one_pixel_more, name="one-pixel-too-many.png"))


@pytest.mark.parametrize("pillow_limit", (4, 1), ids=("warning", "error"))
def test_normalize_image_rejects_pillow_decompression_bomb_warning_or_error(
    monkeypatch: pytest.MonkeyPatch, pillow_limit: int
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", pillow_limit)

    assert_rejected(upload(image_bytes("PNG"), name="small-but-bomb.png"))


@pytest.mark.parametrize(
    "source",
    (
        upload(b"<svg xmlns='http://www.w3.org/2000/svg' />", name="image.jpg"),
        upload(b"%PDF-1.7\nnot-an-image", name="looks-like.png"),
    ),
    ids=("svg", "unsupported-signature"),
)
def test_normalize_image_rejects_unsupported_content(
    source: SimpleUploadedFile,
) -> None:
    assert_rejected(source)


def test_normalize_image_rejects_an_image_identified_by_header_but_truncated_at_load() -> (
    None
):
    source = image_bytes("JPEG", size=(128, 128), quality=100, subsampling=0)
    truncated = source[:-64]

    with Image.open(BytesIO(truncated)) as identified:
        assert identified.format == "JPEG"
        with pytest.raises(OSError):
            identified.load()

    assert_rejected(upload(truncated, name="truncated.jpeg"))


def test_normalize_image_rejects_gif_and_animated_webp() -> None:
    first = Image.new("RGB", (2, 3), color=(1, 2, 3))
    second = Image.new("RGB", (2, 3), color=(3, 2, 1))
    gif = BytesIO()
    first.save(gif, format="GIF", save_all=True, append_images=[second])
    webp = BytesIO()
    first.save(
        webp,
        format="WEBP",
        save_all=True,
        append_images=[second],
        duration=[100, 100],
        loop=0,
        lossless=True,
    )

    with Image.open(BytesIO(webp.getvalue())) as animated_webp:
        assert animated_webp.n_frames > 1
        assert animated_webp.is_animated
        animated_webp.seek(1)
        assert animated_webp.convert("RGB").getpixel((0, 0)) == (3, 2, 1)

    assert_rejected(upload(gif.getvalue(), name="photo.png"))
    assert_rejected(upload(webp.getvalue(), name="photo.webp"))
