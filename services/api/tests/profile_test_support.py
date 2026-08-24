"""Deterministic adapters shared by the independent profile acceptance tests."""

from __future__ import annotations

from io import BytesIO
from threading import Event, Lock
from typing import IO, Any, Protocol

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


class _JsonResponse(Protocol):
    def json(self) -> dict[str, object]: ...


def assert_profile_response(
    response: _JsonResponse, *, is_enabled: bool = True
) -> dict[str, object]:
    """Assert the approved five-field runtime representation and return it."""
    data = response.json()
    assert set(data) == {
        "handle",
        "display_name",
        "avatar_url",
        "onboarding_complete",
        "is_enabled",
    }
    assert data["is_enabled"] is is_enabled
    return data


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

    _save_entry_lock = Lock()
    _save_entries = 0
    first_save_stored: Event | None = None
    second_save_stored: Event | None = None
    release_first_save: Event | None = None
    release_second_save: Event | None = None

    @classmethod
    def configure_upload_pause(cls) -> tuple[Event, Event]:
        with cls._save_entry_lock:
            cls._save_entries = 0
            cls.first_save_stored = Event()
            cls.second_save_stored = Event()
            cls.release_first_save = Event()
            cls.release_second_save = Event()
            return cls.release_first_save, cls.release_second_save

    @classmethod
    def clear_upload_pause(cls) -> None:
        with cls._save_entry_lock:
            cls._save_entries = 0
            cls.first_save_stored = None
            cls.second_save_stored = None
            cls.release_first_save = None
            cls.release_second_save = None

    def save(
        self, name: str | None, content: IO[Any], max_length: int | None = None
    ) -> str:
        with type(self)._save_entry_lock:
            type(self)._save_entries += 1
            entry = type(self)._save_entries
            first_save_stored = type(self).first_save_stored
            second_save_stored = type(self).second_save_stored
            release_first_save = type(self).release_first_save
            release_second_save = type(self).release_second_save

        saved_name = super().save(name, content, max_length=max_length)
        if entry == 1 and first_save_stored is not None:
            first_save_stored.set()
            assert release_first_save is not None
            assert release_first_save.wait(timeout=10)
        elif entry == 2 and second_save_stored is not None:
            second_save_stored.set()
            assert release_second_save is not None
            assert release_second_save.wait(timeout=10)

        return saved_name
