"""Acceptance contract for the private S3-compatible Django storage adapter."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from django.core.files.base import ContentFile

from media.storage import S3MediaStorage


class FakeS3Client:
    """Record S3 calls without a network client or credential-bearing output."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.head_error: BaseException | None = None

    def put_object(self, **kwargs: object) -> None:
        self.calls.append(("put_object", kwargs))

    def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
        self.calls.append(("get_object", kwargs))
        return {"Body": BytesIO(b"stored-content")}

    def head_object(self, **kwargs: object) -> None:
        self.calls.append(("head_object", kwargs))
        if self.head_error is not None:
            raise self.head_error

    def delete_object(self, **kwargs: object) -> None:
        self.calls.append(("delete_object", kwargs))

    def generate_presigned_url(self, operation: str, **kwargs: object) -> str:
        self.calls.append(
            ("generate_presigned_url", {"operation": operation, **kwargs})
        )
        return "https://read.example.test/private-object"


class RecordingClientFactory:
    """Observe boto3 client construction without exposing credential reprs."""

    def __init__(self, client: FakeS3Client) -> None:
        self.client = client
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, service_name: str, **kwargs: object) -> FakeS3Client:
        self.calls.append((service_name, kwargs))
        return self.client


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
        client_factory=lambda *_args, **_kwargs: client,
    )


def assert_bucket_and_key(call: tuple[str, dict[str, object]], key: str) -> None:
    """Every object operation stays in the configured bucket and validated namespace."""
    _, arguments = call
    assert arguments["Bucket"] == "development-media"
    assert arguments["Key"] == key


def client_error(code: str) -> ClientError:
    """Create the locked botocore error type returned by S3-compatible APIs."""
    return ClientError({"Error": {"Code": code, "Message": "test error"}}, "HeadObject")


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


def test_s3_storage_configures_a_signature_v4_client_with_only_its_supplied_s3_values() -> (
    None
):
    client = FakeS3Client()
    factory = RecordingClientFactory(client)
    secret = "test-" + "secret-" + "value"
    storage = S3MediaStorage(
        endpoint_url="https://r2.example.test",
        bucket_name="development-media",
        region_name="auto",
        access_key_id="test-access-key",
        secret_access_key=secret,
        client_factory=factory,
    )

    assert storage.exists("images/0123456789abcdef0123456789abcdef.jpg") is True

    assert len(factory.calls) == 1
    service_name, arguments = factory.calls[0]
    assert service_name == "s3"
    assert arguments["endpoint_url"] == "https://r2.example.test"
    assert arguments["region_name"] == "auto"
    assert arguments["aws_access_key_id"] == "test-access-key"
    assert (
        sha256(str(arguments["aws_secret_access_key"]).encode()).digest()
        == sha256(secret.encode()).digest()
    )
    assert arguments["config"].signature_version == "s3v4"


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


@pytest.mark.parametrize("requested_expiry", (1, 599, 601, 3_600))
def test_s3_storage_cannot_override_the_fixed_presigned_read_expiry(
    client: FakeS3Client, requested_expiry: int
) -> None:
    """Non-600 input must fail closed or still generate the fixed 600-second URL."""
    try:
        configured_storage = S3MediaStorage(
            endpoint_url="https://r2.example.test",
            bucket_name="development-media",
            region_name="auto",
            access_key_id="test-access-key",
            secret_access_key="test-" + "secret-" + "value",
            url_expiry_seconds=requested_expiry,
            client_factory=lambda *_args, **_kwargs: client,
        )
    except ValueError:
        return

    configured_storage.url("images/0123456789abcdef0123456789abcdef.jpg")

    assert client.calls[-1] == (
        "generate_presigned_url",
        {
            "operation": "get_object",
            "Params": {
                "Bucket": "development-media",
                "Key": "images/0123456789abcdef0123456789abcdef.jpg",
            },
            "ExpiresIn": 600,
        },
    )


@pytest.mark.parametrize("not_found_code", ("404", "NoSuchKey", "NotFound"))
def test_s3_storage_exists_returns_false_only_for_s3_not_found_errors(
    storage: S3MediaStorage, client: FakeS3Client, not_found_code: str
) -> None:
    client.head_error = client_error(not_found_code)

    assert storage.exists("images/0123456789abcdef0123456789abcdef.jpg") is False


@pytest.mark.parametrize("error_code", ("AccessDenied", "InternalError", "SlowDown"))
def test_s3_storage_exists_reraises_non_not_found_s3_errors(
    storage: S3MediaStorage, client: FakeS3Client, error_code: str
) -> None:
    raised = client_error(error_code)
    client.head_error = raised

    with pytest.raises(ClientError) as captured:
        storage.exists("images/0123456789abcdef0123456789abcdef.jpg")

    assert captured.value is raised


def test_s3_storage_exists_reraises_connectivity_errors(
    storage: S3MediaStorage, client: FakeS3Client
) -> None:
    raised = EndpointConnectionError(endpoint_url="https://r2.example.test")
    client.head_error = raised

    with pytest.raises(EndpointConnectionError) as captured:
        storage.exists("images/0123456789abcdef0123456789abcdef.jpg")

    assert captured.value is raised
