"""Acceptance contract for media keys, reads, and lifecycle ordering."""

from __future__ import annotations

import logging
import re

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from media.images import NormalizedImage
from media.keys import create_image_key, validate_image_key
from media.service import (
    read_image_url,
    remove_optional_image,
    replace_image,
    store_image,
)

KEY_PATTERN = re.compile(r"images/[0-9a-f]{32}\.(?:jpg|png|webp)\Z")
OLD_KEY = "images/11111111111111111111111111111111.jpg"
REPLACEMENT_CLEANUP_WARNING = "Media cleanup failed after replacement commit."
REMOVAL_CLEANUP_WARNING = "Media cleanup failed after removal commit."


class OrderedStorage(Storage):
    """A tiny storage fake that exposes externally meaningful operation order."""

    def __init__(
        self, events: list[str], *, url: str = "https://read.example.test/object"
    ):
        self.events = events
        self._url = url
        self.saved: dict[str, bytes] = {}
        self.delete_error: BaseException | None = None

    def _open(self, name: str, mode: str = "rb") -> ContentFile:
        return ContentFile(self.saved[name], name=name)

    def _save(self, name: str, content: ContentFile) -> str:
        self.events.append(f"save:{name}")
        self.saved[name] = content.read()
        return name

    def delete(self, name: str) -> None:
        self.events.append(f"delete:{name}")
        if self.delete_error is not None:
            raise self.delete_error
        self.saved.pop(name, None)

    def exists(self, name: str) -> bool:
        return name in self.saved

    def url(self, name: str) -> str:
        self.events.append(f"url:{name}")
        return self._url


class SecretSafeUrl(str):
    """Avoid exposing a bearer query string if an assertion fails."""

    def __repr__(self) -> str:
        return "<presigned-url-redacted>"


class SecretSafeQuery(str):
    """Keep a synthetic bearer query out of assertion diagnostics."""

    def __repr__(self) -> str:
        return "<presigned-query-redacted>"


def canonical_image() -> NormalizedImage:
    return NormalizedImage(
        content=b"canonical-image-content",
        content_type="image/jpeg",
        extension="jpg",
        width=2,
        height=3,
    )


def test_image_keys_are_opaque_random_and_use_only_canonical_extensions() -> None:
    first = create_image_key("jpg")
    second = create_image_key("jpg")

    assert KEY_PATTERN.fullmatch(first)
    assert KEY_PATTERN.fullmatch(second)
    assert first != second
    assert validate_image_key(first) == first
    for extension in ("png", "webp"):
        assert KEY_PATTERN.fullmatch(create_image_key(extension))


@pytest.mark.parametrize(
    "unsafe_key",
    (
        "../images/0123456789abcdef0123456789abcdef.jpg",
        "images/0123456789abcdef0123456789abcdef.JPEG",
        "images/0123456789abcdef0123456789abcdef.svg",
        "images/not-a-uuid.jpg",
        "profiles/person.jpg",
        "images/0123456789abcdef0123456789abcdef.jpg/extra",
    ),
)
def test_storage_operations_reject_unsafe_or_unrecognized_keys_before_access(
    unsafe_key: str,
) -> None:
    storage = OrderedStorage([])

    with pytest.raises(ValueError):
        validate_image_key(unsafe_key)
    with pytest.raises(ValueError):
        read_image_url(unsafe_key, storage=storage)
    with pytest.raises(ValueError):
        remove_optional_image(unsafe_key, lambda: None, storage=storage)

    assert storage.events == []


def test_store_image_generates_a_key_and_saves_only_canonical_content() -> None:
    image = canonical_image()

    key = store_image(image)

    assert KEY_PATTERN.fullmatch(key)
    assert default_storage.open(key).read() == image.content


def test_read_image_url_returns_backend_url_without_persisting_or_logging_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "images/0123456789abcdef0123456789abcdef.jpg"
    secret_query = SecretSafeQuery("signature=" + "must-not-be-logged")
    url = SecretSafeUrl(f"https://read.example.test/object?{secret_query}")
    storage = OrderedStorage([], url=url)
    caplog.set_level(logging.DEBUG)

    result = read_image_url(key, storage=storage)

    assert result == url
    assert storage.events == [f"url:{key}"]
    assert secret_query not in caplog.text


def test_replace_image_saves_then_commits_then_deletes_old_object() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    new_key = replace_image(
        canonical_image(),
        old_key=OLD_KEY,
        commit=lambda key: events.append(f"commit:{key}"),
        storage=storage,
    )

    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{OLD_KEY}"]


def test_replace_image_rejects_an_unsafe_old_key_before_save_or_commit() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    with pytest.raises(ValueError):
        replace_image(
            canonical_image(),
            old_key="profiles/user-upload.jpg",
            commit=lambda key: events.append(f"commit:{key}"),
            storage=storage,
        )

    assert events == []


def test_replace_image_compensates_new_object_after_commit_failure_and_reraises_original() -> (
    None
):
    events: list[str] = []
    storage = OrderedStorage(events)
    original = RuntimeError("commit failed")

    def fail_commit(key: str) -> None:
        events.append(f"commit:{key}")
        raise original

    with pytest.raises(RuntimeError) as raised:
        replace_image(
            canonical_image(), old_key=OLD_KEY, commit=fail_commit, storage=storage
        )

    new_key = events[0].removeprefix("save:")
    assert raised.value is original
    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{new_key}"]


def test_replace_image_preserves_commit_failure_when_compensating_delete_also_fails() -> (
    None
):
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = OSError("cleanup failed")
    original = RuntimeError("commit failed")

    def fail_commit(key: str) -> None:
        events.append(f"commit:{key}")
        raise original

    with pytest.raises(RuntimeError) as raised:
        replace_image(
            canonical_image(), old_key=OLD_KEY, commit=fail_commit, storage=storage
        )

    assert raised.value is original


def test_replace_image_tolerates_old_object_delete_failure_without_another_commit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = OSError(
        "source exception includes "
        + OLD_KEY
        + " and https://read.example.test/object?signature=redacted"
    )
    caplog.set_level(logging.WARNING)

    new_key = replace_image(
        canonical_image(),
        old_key=OLD_KEY,
        commit=lambda key: events.append(f"commit:{key}"),
        storage=storage,
    )

    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{OLD_KEY}"]
    assert caplog.messages == [REPLACEMENT_CLEANUP_WARNING]


def test_remove_optional_image_commits_removal_then_deletes_old_object() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    remove_optional_image(
        OLD_KEY, lambda: events.append("commit:remove"), storage=storage
    )

    assert events == ["commit:remove", f"delete:{OLD_KEY}"]


def test_remove_optional_image_never_deletes_when_removal_commit_fails() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    original = RuntimeError("remove commit failed")

    def fail_commit() -> None:
        events.append("commit:remove")
        raise original

    with pytest.raises(RuntimeError) as raised:
        remove_optional_image(OLD_KEY, fail_commit, storage=storage)

    assert raised.value is original
    assert events == ["commit:remove"]


def test_remove_optional_image_tolerates_delete_failure_after_authoritative_commit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = OSError(
        "source exception includes "
        + OLD_KEY
        + " and https://read.example.test/object?signature=redacted"
    )
    caplog.set_level(logging.WARNING)

    remove_optional_image(
        OLD_KEY, lambda: events.append("commit:remove"), storage=storage
    )

    assert events == ["commit:remove", f"delete:{OLD_KEY}"]
    assert caplog.messages == [REMOVAL_CLEANUP_WARNING]
