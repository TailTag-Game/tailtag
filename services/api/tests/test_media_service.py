"""Acceptance contract for media keys, reads, and lifecycle ordering."""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import cast

import pytest
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, PngImagePlugin

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
CLEANUP_FAILURE_URL = "https://read.example.test/object?signature=redacted"


class OrderedStorage(Storage):
    """A tiny storage fake that exposes externally meaningful operation order."""

    def __init__(
        self, events: list[str], *, url: str = "https://read.example.test/object"
    ):
        self.events = events
        self._url = url
        self.saved: dict[str, bytes] = {}
        self.delete_error: BaseException | None = None

    def _open(self, name: str, mode: str = "rb") -> ContentFile[bytes]:
        return ContentFile(self.saved[name], name=name)

    def _save(self, name: str, content: ContentFile[bytes]) -> str:
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

    def url(self, name: str | None, parameters: str | None = None) -> str:
        del parameters
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


class NonStringKey:
    """A non-string whose representation must never reach key-validation errors."""

    def __repr__(self) -> str:
        return "non-string-key-sentinel"


def canonical_upload() -> SimpleUploadedFile:
    """Use a real upload so public lifecycle calls exercise normalization."""
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Source", "caller-metadata-must-not-be-stored")
    destination = BytesIO()
    Image.new("RGB", (2, 3), color=(12, 34, 56)).save(
        destination, format="PNG", pnginfo=metadata
    )
    return SimpleUploadedFile(
        "caller-image.png", destination.getvalue(), content_type="image/png"
    )


def forged_normalized_image() -> NormalizedImage:
    """Model a caller attempting to bypass the public upload normalization boundary."""
    return NormalizedImage(
        content=b"caller-forged-canonical-bytes",
        content_type="image/jpeg",
        extension="jpg",
        width=2,
        height=3,
    )


def cleanup_failure() -> OSError:
    """Supply a cleanup error whose attached traceback would disclose private data."""
    return OSError(
        "source exception includes " + OLD_KEY + " and " + CLEANUP_FAILURE_URL
    )


def assert_sanitized_cleanup_warning(
    caplog: pytest.LogCaptureFixture, warning: str
) -> None:
    """Require a fixed warning with no exception attachment or sensitive record data."""
    assert caplog.messages == [warning]
    assert len(caplog.records) == 1
    assert all(
        record.exc_info is None
        and record.exc_text is None
        and record.stack_info is None
        for record in caplog.records
    )

    rendered_records = "\n".join(
        caplog.handler.format(record) for record in caplog.records
    )
    record_data = "\n".join(repr(record.__dict__) for record in caplog.records)
    assert all(record.exc_text is None for record in caplog.records)
    assert all(
        sentinel not in output
        for sentinel in (OLD_KEY, CLEANUP_FAILURE_URL)
        for output in (caplog.text, rendered_records, record_data)
    )


def assert_no_sensitive_cleanup_log_details(caplog: pytest.LogCaptureFixture) -> None:
    """Cleanup failures may be logged only without attached exception details."""
    assert all(
        record.exc_info is None
        and record.exc_text is None
        and record.stack_info is None
        for record in caplog.records
    )
    rendered_records = "\n".join(
        caplog.handler.format(record) for record in caplog.records
    )
    record_data = "\n".join(repr(record.__dict__) for record in caplog.records)
    assert all(
        sentinel not in output
        for sentinel in (OLD_KEY, CLEANUP_FAILURE_URL)
        for output in (caplog.text, rendered_records, record_data)
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


@pytest.mark.parametrize("unsafe_key", (None, 7, NonStringKey()))
def test_validate_image_key_rejects_non_strings_without_echoing_them(
    unsafe_key: object,
) -> None:
    with pytest.raises(ValueError) as raised:
        validate_image_key(unsafe_key)

    assert "non-string-key-sentinel" not in str(raised.value)
    assert "non-string-key-sentinel" not in repr(raised.value)


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
        remove_optional_image(
            old_key=unsafe_key, commit_removal=lambda: None, storage=storage
        )

    assert storage.events == []


def test_store_image_generates_a_key_and_saves_only_canonical_content() -> None:
    image = canonical_upload()
    source_content = image.read()
    image.seek(0)

    key = store_image(image)

    assert KEY_PATTERN.fullmatch(key)
    stored_file: File[bytes] = cast(
        "File[bytes]",
        default_storage.open(key),  # pyright: ignore[reportUnknownMemberType] - Django's lazy default storage loses the backend file generic.
    )
    stored_content = stored_file.read()
    assert stored_content != source_content
    with Image.open(BytesIO(stored_content)) as stored_image:
        assert stored_image.format == "PNG"
        assert "Source" not in stored_image.info


def test_store_image_rejects_a_caller_forged_normalized_image_before_save() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    with pytest.raises(TypeError):
        store_image(forged_normalized_image(), storage=storage)

    assert events == []


def test_replace_image_rejects_a_caller_forged_normalized_image_before_side_effects() -> (
    None
):
    events: list[str] = []
    storage = OrderedStorage(events)

    with pytest.raises(TypeError):
        replace_image(
            forged_normalized_image(),
            old_key=OLD_KEY,
            commit_reference=lambda key: events.append(f"commit:{key}"),
            storage=storage,
        )

    assert events == []


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
        canonical_upload(),
        old_key=OLD_KEY,
        commit_reference=lambda key: events.append(f"commit:{key}"),
        storage=storage,
    )

    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{OLD_KEY}"]


def test_replace_image_rejects_an_unsafe_old_key_before_save_or_commit() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    with pytest.raises(ValueError):
        replace_image(
            canonical_upload(),
            old_key="profiles/user-upload.jpg",
            commit_reference=lambda key: events.append(f"commit:{key}"),
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
            canonical_upload(),
            old_key=OLD_KEY,
            commit_reference=fail_commit,
            storage=storage,
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
            canonical_upload(),
            old_key=OLD_KEY,
            commit_reference=fail_commit,
            storage=storage,
        )

    assert raised.value is original


@pytest.mark.parametrize(
    "compensation_error",
    (
        SystemExit(
            "source exception includes " + OLD_KEY + " and " + CLEANUP_FAILURE_URL
        ),
        KeyboardInterrupt(
            "source exception includes " + OLD_KEY + " and " + CLEANUP_FAILURE_URL
        ),
    ),
    ids=("system-exit", "keyboard-interrupt"),
)
def test_replace_image_preserves_commit_failure_when_compensating_delete_raises_base_exception(
    caplog: pytest.LogCaptureFixture, compensation_error: BaseException
) -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = compensation_error
    original = RuntimeError("commit failed")
    caplog.set_level(logging.DEBUG)

    def fail_commit(key: str) -> None:
        events.append(f"commit:{key}")
        raise original

    caught: BaseException | None = None
    try:
        replace_image(
            canonical_upload(),
            old_key=OLD_KEY,
            commit_reference=fail_commit,
            storage=storage,
        )
    except BaseException as error:  # noqa: BLE001 - verifies SystemExit/KeyboardInterrupt preservation.
        caught = error

    new_key = events[0].removeprefix("save:")
    if caught is not original:
        pytest.fail("replacement must preserve the original commit exception")
    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{new_key}"]
    assert_no_sensitive_cleanup_log_details(caplog)


def test_replace_image_tolerates_old_object_delete_failure_without_another_commit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = cleanup_failure()
    caplog.set_level(logging.WARNING)

    new_key = replace_image(
        canonical_upload(),
        old_key=OLD_KEY,
        commit_reference=lambda key: events.append(f"commit:{key}"),
        storage=storage,
    )

    assert events == [f"save:{new_key}", f"commit:{new_key}", f"delete:{OLD_KEY}"]
    assert_sanitized_cleanup_warning(caplog, REPLACEMENT_CLEANUP_WARNING)


def test_remove_optional_image_commits_removal_then_deletes_old_object() -> None:
    events: list[str] = []
    storage = OrderedStorage(events)

    remove_optional_image(
        old_key=OLD_KEY,
        commit_removal=lambda: events.append("commit:remove"),
        storage=storage,
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
        remove_optional_image(
            old_key=OLD_KEY, commit_removal=fail_commit, storage=storage
        )

    assert raised.value is original
    assert events == ["commit:remove"]


def test_remove_optional_image_tolerates_delete_failure_after_authoritative_commit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[str] = []
    storage = OrderedStorage(events)
    storage.delete_error = cleanup_failure()
    caplog.set_level(logging.WARNING)

    remove_optional_image(
        old_key=OLD_KEY,
        commit_removal=lambda: events.append("commit:remove"),
        storage=storage,
    )

    assert events == ["commit:remove", f"delete:{OLD_KEY}"]
    assert_sanitized_cleanup_warning(caplog, REMOVAL_CLEANUP_WARNING)
