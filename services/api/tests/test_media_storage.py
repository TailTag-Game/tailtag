"""Acceptance contract for the private S3-compatible Django storage adapter."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from media.storage import S3MediaStorage


class FakeS3Client:
    """Record S3 calls without a network client or credential-bearing output."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def put_object(self, **kwargs: object) -> None:
        self.calls.append(("put_object", kwargs))

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        self.calls.append(("get_object", kwargs))
        return {"Body": BytesIO(b"stored-content")}

    def head_object(self, **kwargs: object) -> None:
        self.calls.append(("head_object", kwargs))

    def delete_object(self, **kwargs: object) -> None:
        self.calls.append(("delete_object", kwargs))

    def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
        self.calls.append(
            ("generate_presigned_url", {"operation": operation, **kwargs})
        )
        return "https://read.example.test/private-object"


@pytest.fixture
def client() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture
def storage(client: FakeS3Client) -> S3MediaStorage:
    return S3MediaStorage(
        endpoint_url="https://r2.example.test",
        bucket_name="development-media",
        region_name="auto",
        access_key_id="test-access-key",
        secret_access_key="test-" + "secret-" + "value",
        client_factory=lambda: client,
    )


def assert_bucket_and_key(call: tuple[str, dict[str, object]], key: str) -> None:
    """Every object operation stays in the configured bucket and validated namespace."""
    _, arguments = call
    assert arguments["Bucket"] == "development-media"
    assert arguments["Key"] == key


def test_s3_storage_uses_configured_bucket_and_key_for_all_object_operations(
    storage: S3MediaStorage, client: FakeS3Client
) -> None:
    key = "images/0123456789abcdef0123456789abcdef.jpg"

    assert storage.save(key, ContentFile(b"canonical-content")) == key
    assert storage.open(key).read() == b"stored-content"
    assert storage.exists(key) is True
    storage.delete(key)

    operation_names = [operation for operation, _ in client.calls]
    assert operation_names == [
        "put_object",
        "get_object",
        "head_object",
        "delete_object",
    ]
    for call in client.calls:
        assert_bucket_and_key(call, key)
    assert client.calls[0][1]["Body"] == b"canonical-content"


@pytest.mark.parametrize(
    "unsafe_key",
    (
        "images/0123456789abcdef0123456789abcdef.gif",
        "../../development-media/private.jpg",
        "images/not-a-key.jpg",
    ),
)
def test_s3_storage_rejects_unvalidated_keys_before_client_access(
    storage: S3MediaStorage, client: FakeS3Client, unsafe_key: str
) -> None:
    for operation in (
        lambda: storage.save(unsafe_key, ContentFile(b"content")),
        lambda: storage.open(unsafe_key),
        lambda: storage.exists(unsafe_key),
        lambda: storage.delete(unsafe_key),
        lambda: storage.url(unsafe_key),
    ):
        with pytest.raises(ValueError):
            operation()

    assert client.calls == []


def test_s3_storage_generates_only_a_ten_minute_get_read_url(
    storage: S3MediaStorage, client: FakeS3Client
) -> None:
    key = "images/0123456789abcdef0123456789abcdef.webp"

    url = storage.url(key)

    assert url == "https://read.example.test/private-object"
    assert client.calls == [
        (
            "generate_presigned_url",
            {
                "operation": "get_object",
                "Params": {"Bucket": "development-media", "Key": key},
                "ExpiresIn": 600,
            },
        )
    ]
