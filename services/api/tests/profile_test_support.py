"""Deterministic adapters shared by the independent profile acceptance tests."""

from __future__ import annotations

from io import BytesIO
from threading import Event
from typing import IO, Any

from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

RECORDING_STORAGES = {
    "default": {"BACKEND": "tests.profile_test_support.RecordingStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
BLOCKING_RECORDING_STORAGES = {
    "default": {"BACKEND": "tests.profile_test_support.BlockingRecordingStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


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
        self, name: str | None, content: IO[Any], max_length: int | None = None
    ) -> str:
        assert isinstance(name, str)
        self.events.append(("save", name))
        return super().save(name, content, max_length=max_length)

    def delete(self, name: str) -> None:
        self.events.append(("delete", name))
        super().delete(name)

    def url(self, name: str | None, parameters: Any | None = None) -> str:
        del parameters
        assert isinstance(name, str)
        self.url_calls += 1
        self.events.append(("url", name))
        return f"https://media.example.test/read/{self.url_calls}"


class BlockingRecordingStorage(RecordingStorage):
    """A real in-memory storage backend that pauses uploads before reference commit."""

    saved: Event | None = None
    release: Event | None = None

    @classmethod
    def configure_upload_pause(cls) -> Event:
        cls.saved = Event()
        cls.release = Event()
        return cls.release

    @classmethod
    def clear_upload_pause(cls) -> None:
        cls.saved = None
        cls.release = None

    def save(
        self, name: str | None, content: IO[Any], max_length: int | None = None
    ) -> str:
        saved_name = super().save(name, content, max_length=max_length)
        if self.saved is not None and self.release is not None:
            self.saved.set()
            assert self.release.wait(timeout=10)
        return saved_name
