"""Private S3-compatible Django storage for opaque media objects."""

from __future__ import annotations

from typing import IO, TYPE_CHECKING, Any, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.core.files import File
from django.core.files.storage import Storage

from observability.dependencies import (
    RpcMethod,
    StorageReason,
    classify_storage_error,
    record_storage_operation,
)

from .keys import validate_image_key

_READ_URL_EXPIRY_SECONDS = 600
_NOT_FOUND_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_S3_CLIENT_CONFIG = Config(
    signature_version="s3v4",
    connect_timeout=2,
    read_timeout=5,
    retries={"mode": "standard", "total_max_attempts": 2},
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.core.files.base import File as DjangoFile


class _S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...

    def head_object(self, **kwargs: object) -> dict[str, object]: ...

    def delete_object(self, **kwargs: object) -> object: ...

    def generate_presigned_url(self, operation: str, **kwargs: object) -> str: ...


class S3MediaStorage(Storage):
    """Store only validated image keys through an S3-compatible client."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region_name: str | None = None,
        region: str | None = None,
        url_expiry_seconds: int = 600,
        client_factory: Callable[..., _S3Client] | None = None,
    ) -> None:
        super().__init__()
        selected_region = region_name if region_name is not None else region
        if selected_region is None:
            raise TypeError("S3MediaStorage requires a region.")
        if url_expiry_seconds != _READ_URL_EXPIRY_SECONDS:
            raise ValueError("S3MediaStorage read URL expiry must be 600 seconds.")
        self._bucket_name = bucket_name
        client_arguments: dict[str, object] = {
            "endpoint_url": endpoint_url,
            "region_name": selected_region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "config": _S3_CLIENT_CONFIG,
        }
        if client_factory is None:
            self._client = cast(
                _S3Client,
                boto3.client(  # pyright: ignore[reportUnknownMemberType]
                    "s3",
                    endpoint_url=endpoint_url,
                    region_name=selected_region,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    config=_S3_CLIENT_CONFIG,
                ),
            )
        else:
            self._client = client_factory(
                "s3",
                **client_arguments,
            )

    def _call[T](
        self,
        method: RpcMethod,
        operation: Callable[..., T],
        *,
        absence_is_success: bool = False,
        **arguments: object,
    ) -> T:
        """Run one network call, record exactly one operation, and re-raise as is."""
        try:
            result = operation(**arguments)
        except Exception as error:
            reason: StorageReason | None = classify_storage_error(error)
            if absence_is_success and _is_absence(error):
                reason = None
            record_storage_operation(method, reason)
            raise
        record_storage_operation(method)
        return result

    def _save(self, name: str, content: DjangoFile[bytes]) -> str:
        key = validate_image_key(name)
        arguments: dict[str, object] = {
            "Bucket": self._bucket_name,
            "Key": key,
            "Body": content.read(),
        }
        content_type = getattr(content, "content_type", None)
        if isinstance(content_type, str):
            arguments["ContentType"] = content_type
        self._call(RpcMethod.PUT_OBJECT, self._client.put_object, **arguments)
        return key

    def save(
        self, name: str | None, content: IO[Any], max_length: int | None = None
    ) -> str:
        """Save the exact validated key without Django's alternate-name fallback."""
        del max_length
        return self._save(
            validate_image_key(name) if name is not None else _missing_key(),
            cast("DjangoFile[bytes]", content),
        )

    def _open(self, name: str, mode: str = "rb") -> File[bytes]:
        key = validate_image_key(name)
        response = self._call(
            RpcMethod.GET_OBJECT,
            self._client.get_object,
            Bucket=self._bucket_name,
            Key=key,
        )
        body = response["Body"]
        return File(cast(IO[bytes], body), name=key)

    def exists(self, name: str) -> bool:
        key = validate_image_key(name)
        try:
            self._call(
                RpcMethod.HEAD_OBJECT,
                self._client.head_object,
                absence_is_success=True,
                Bucket=self._bucket_name,
                Key=key,
            )
        except ClientError as error:
            if _is_absence(error):
                return False
            raise
        return True

    def size(self, name: str) -> int:
        key = validate_image_key(name)
        response = self._call(
            RpcMethod.HEAD_OBJECT,
            self._client.head_object,
            Bucket=self._bucket_name,
            Key=key,
        )
        return cast(int, response["ContentLength"])

    def delete(self, name: str) -> None:
        key = validate_image_key(name)
        self._call(
            RpcMethod.DELETE_OBJECT,
            self._client.delete_object,
            Bucket=self._bucket_name,
            Key=key,
        )

    def url(self, name: str | None, parameters: Any | None = None) -> str:
        del parameters
        key = validate_image_key(name) if name is not None else _missing_key()
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": key},
            ExpiresIn=_READ_URL_EXPIRY_SECONDS,
        )


def _is_absence(error: BaseException) -> bool:
    return (
        isinstance(error, ClientError)
        and error.response.get("Error", {}).get("Code") in _NOT_FOUND_ERROR_CODES
    )


def _missing_key() -> str:
    raise ValueError("Invalid image key.")
