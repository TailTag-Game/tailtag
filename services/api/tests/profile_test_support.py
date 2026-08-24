"""Deterministic adapters shared by the independent profile acceptance tests."""

from __future__ import annotations

from io import BytesIO

from django.core.files import File
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def image_upload(*, name: str = "avatar.png") -> SimpleUploadedFile:
    """Return a small, real raster upload without a binary fixture."""
    content = BytesIO()
    Image.new("RGB", (2, 3), color=(12, 34, 56)).save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


class RecordingStorage(InMemoryStorage):
    """In-memory storage that makes lifecycle ordering and URL generation visible."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, str]] = []
        self.url_calls = 0

    def save(
        self, name: str, content: File[bytes], max_length: int | None = None
    ) -> str:
        self.events.append(("save", name))
        return super().save(name, content, max_length=max_length)

    def delete(self, name: str) -> None:
        self.events.append(("delete", name))
        super().delete(name)

    def url(self, name: str) -> str:
        self.url_calls += 1
        self.events.append(("url", name))
        return f"https://media.example.test/read/{self.url_calls}"
