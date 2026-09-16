"""Emit guarded, non-reversible fingerprints for environment isolation evidence."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from typing import Final

_CONFIRMATION: Final = "run-tailtag-environment-fingerprint"
_TARGETS: Final = frozenset({"development", "staging"})
_FIELD_GROUPS: Final = {
    "database": ("DATABASE_URL",),
    "django-secret": ("DJANGO_SECRET_KEY",),
    "clerk-verification": ("CLERK_JWT_KEY", "CLERK_AUTHORIZED_PARTIES"),
    "media-bucket": ("MEDIA_STORAGE_BUCKET_NAME",),
    "media-credential": (
        "MEDIA_STORAGE_ACCESS_KEY_ID",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY",
    ),
}
_FINGERPRINT_LENGTH: Final = 16


def _valid_target(environment: Mapping[str, str]) -> str | None:
    target = environment.get("RAILWAY_ENVIRONMENT_NAME")
    if (
        target not in _TARGETS
        or environment.get("RAILWAY_SERVICE_NAME") != "api"
        or environment.get("TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM") != _CONFIRMATION
    ):
        return None
    return target


def _fingerprint(field_names: tuple[str, ...], environment: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for name in field_names:
        value = environment[name]
        encoded_name = name.encode("utf-8")
        encoded_value = value.encode("utf-8")
        digest.update(str(len(encoded_name)).encode("ascii"))
        digest.update(b":")
        digest.update(encoded_name)
        digest.update(b":")
        digest.update(str(len(encoded_value)).encode("ascii"))
        digest.update(b":")
        digest.update(encoded_value)
    return digest.hexdigest()[:_FINGERPRINT_LENGTH]


def main() -> int:
    """Validate every input before emitting the complete sanitized evidence set."""
    if len(sys.argv) != 1:
        print("FAIL environment fingerprint arguments invalid", file=sys.stderr)
        return 1

    target = _valid_target(os.environ)
    if target is None or any(
        not os.environ.get(field)
        for fields in _FIELD_GROUPS.values()
        for field in fields
    ):
        print("FAIL environment fingerprint configuration invalid", file=sys.stderr)
        return 1

    fingerprints = [
        (label, _fingerprint(fields, os.environ))
        for label, fields in _FIELD_GROUPS.items()
    ]
    print(f"PASS target {target}/api")
    for label, digest in fingerprints:
        print(f"FINGERPRINT {label} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
