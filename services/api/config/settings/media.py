"""Fail-closed, sanitized configuration for S3-compatible media storage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True, repr=False)
class S3MediaConfiguration:
    """The complete S3-compatible media storage configuration."""

    endpoint_url: str
    bucket_name: str
    region: str
    access_key_id: str
    secret_access_key: str

    def __repr__(self) -> str:
        """Prevent configuration values, especially credentials, entering diagnostics."""
        return "S3MediaConfiguration(<redacted>)"


_REQUIRED_VARIABLES = (
    "MEDIA_STORAGE_ENDPOINT_URL",
    "MEDIA_STORAGE_BUCKET_NAME",
    "MEDIA_STORAGE_REGION",
    "MEDIA_STORAGE_ACCESS_KEY_ID",
    "MEDIA_STORAGE_SECRET_ACCESS_KEY",
)


def _required_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not value or not value.strip():
        message = f"Missing required environment variable: {name}"
        raise RuntimeError(message)
    return value


def _is_valid_hostname(hostname: str | None) -> bool:
    """Accept a valid IP address or conventional DNS hostname only."""
    if not hostname or any(character.isspace() for character in hostname):
        return False

    try:
        ip_address(hostname)
    except ValueError:
        normalized_hostname = hostname.removesuffix(".")
        labels = normalized_hostname.split(".")
        return (
            bool(normalized_hostname)
            and len(hostname) <= 253
            and all(
                label
                and len(label) <= 63
                and label.isascii()
                and label[0].isalnum()
                and label[-1].isalnum()
                and all(character.isalnum() or character == "-" for character in label)
                for label in labels
            )
        )
    else:
        return True


def _validate_endpoint(endpoint_url: str) -> None:
    try:
        parsed = urlparse(endpoint_url)
        hostname_is_valid = _is_valid_hostname(parsed.hostname)
        _port = parsed.port
    except ValueError:
        message = "MEDIA_STORAGE_ENDPOINT_URL must be an HTTPS root URL."
        raise RuntimeError(message) from None

    if (
        parsed.scheme != "https"
        or not hostname_is_valid
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        message = "MEDIA_STORAGE_ENDPOINT_URL must be an HTTPS root URL."
        raise RuntimeError(message)


def load_s3_media_configuration(
    environment: Mapping[str, str],
) -> S3MediaConfiguration:
    """Load complete generic S3 configuration without exposing supplied values."""
    values = {name: _required_value(environment, name) for name in _REQUIRED_VARIABLES}
    _validate_endpoint(values["MEDIA_STORAGE_ENDPOINT_URL"])
    return S3MediaConfiguration(
        endpoint_url=values["MEDIA_STORAGE_ENDPOINT_URL"],
        bucket_name=values["MEDIA_STORAGE_BUCKET_NAME"],
        region=values["MEDIA_STORAGE_REGION"],
        access_key_id=values["MEDIA_STORAGE_ACCESS_KEY_ID"],
        secret_access_key=values["MEDIA_STORAGE_SECRET_ACCESS_KEY"],
    )
