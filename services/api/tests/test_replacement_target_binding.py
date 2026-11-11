"""Offline acceptance tests for the replacement Render target binding.

All UUIDs here are synthetic. The tests exercise the reviewed internal seam,
never the owner-only target manifest or a provider connection.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest
from pytest import MonkeyPatch

from tests import windows_acl_support as acl

RENDER_MANIFEST: Final = {"render_staging_api_service_id": "srv-d0staging000000000000"}
SENSITIVE: Final = "private-target-value-must-never-appear"
FIXED_FAILURE: Final = "Replacement target binding unavailable"


@pytest.fixture
def binding() -> ModuleType:
    """Exercise the intentionally package-internal target binding seam."""
    return importlib.import_module("config.replacement_target_binding")


def _assert_fixed_denial(binding: ModuleType, operation: Callable[[], object]) -> None:
    with pytest.raises(binding.TargetBindingError) as caught:
        operation()
    assert str(caught.value) == FIXED_FAILURE
    rendered = str(caught.value)
    for private_value in (*RENDER_MANIFEST.values(), SENSITIVE):
        assert private_value not in rendered


def _private_manifest(tmp_path: Path, data: str | Mapping[str, object]) -> Path:
    parent = tmp_path / "tailtag"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    path = parent / "staging-clean-rebuild-targets.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    path.chmod(0o600)
    if sys.platform == "win32":
        acl.make_owner_only(parent, container=True)
        acl.make_owner_only(path)
    return path


@pytest.fixture(autouse=True)
def restore_manifest_path(binding: ModuleType) -> Iterator[None]:
    original = binding._manifest_path
    yield
    setattr(binding, "_manifest_path", original)  # noqa: B010


def _load(binding: ModuleType, path: Path) -> object:
    setattr(binding, "_manifest_path", lambda: path)  # noqa: B010
    return binding.load_render_staging_service_id()


@pytest.mark.parametrize(
    "document",
    (
        "{bad json " + SENSITIVE,
        "[]",
        json.dumps({"unrelated": "value"}),
        '{"render_staging_api_service_id":"'
        + "srv-d0staging000000000000"
        + '","render_staging_api_service_id":"'
        + "srv-d0other0000000000000"
        + '"}',
        json.dumps({"render_staging_api_service_id": "not-a-service-id"}),
    ),
)
def test_loader_rejects_malformed_missing_or_ambiguous_manifest(
    binding: ModuleType, tmp_path: Path, document: str
) -> None:
    """T-2/T-8: malformed JSON and duplicate keys fail with fixed output."""
    path = _private_manifest(tmp_path, document)
    _assert_fixed_denial(binding, lambda: _load(binding, path))


def test_loader_sanitizes_json_integer_conversion_failure(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8: parser limits cannot leak an untrusted value or raw exception."""
    oversized_integer = "9" * 5000
    path = _private_manifest(
        tmp_path, '{"untrusted_allocation_count":' + oversized_integer + "}"
    )

    _assert_fixed_denial(binding, lambda: _load(binding, path))


def test_loader_sanitizes_excessive_json_nesting(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8: a bounded file can still exceed the JSON parser depth."""
    path = _private_manifest(tmp_path, "[" * 32000 + "0" + "]" * 32000)
    _assert_fixed_denial(binding, lambda: _load(binding, path))


def test_loader_rejects_missing_symlink_and_wrong_modes(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2: wrong owner-only boundary is not silently accepted."""
    path = _private_manifest(tmp_path, RENDER_MANIFEST)
    _assert_fixed_denial(binding, lambda: _load(binding, path.parent / "missing.json"))

    path.chmod(0o644)
    if sys.platform == "win32":
        acl.make_owner_only(path, extra_aces="(A;;FR;;;BU)")
    _assert_fixed_denial(binding, lambda: _load(binding, path))
    path.chmod(0o600)
    if sys.platform == "win32":
        acl.make_owner_only(path)
    path.parent.chmod(0o755)
    if sys.platform == "win32":
        acl.make_owner_only(path.parent, container=True, extra_aces="(A;;FR;;;BU)")
    _assert_fixed_denial(binding, lambda: _load(binding, path))

    # Last, because an account that cannot create symlinks skips from here.
    path.parent.chmod(0o700)
    if sys.platform == "win32":
        acl.make_owner_only(path.parent, container=True)
        acl.require_symlinks(tmp_path)
    alias = path.parent / "alias.json"
    alias.symlink_to(path)
    _assert_fixed_denial(binding, lambda: _load(binding, alias))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX uid ownership")
def test_loader_rejects_wrong_owner_without_exposing_path_or_values(
    binding: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """T-2/T-8: current-process owner is part of the private-file boundary."""
    path = _private_manifest(tmp_path, RENDER_MANIFEST)
    current_uid = os.getuid()
    # Patch the os module itself: the owner check no longer lives in this module.
    monkeypatch.setattr(os, "getuid", lambda: current_uid + 1)
    _assert_fixed_denial(binding, lambda: _load(binding, path))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows owner SIDs")
def test_loader_rejects_administrators_owned_manifest_without_exposing_values(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8, S3-1: the Windows owner must be the token user, never Administrators."""
    path = _private_manifest(tmp_path, RENDER_MANIFEST)
    try:
        acl.make_owner_only(path, owner=acl.ADMINISTRATORS_SID)
    except OSError:
        pytest.skip("this account cannot assign an Administrators owner")
    _assert_fixed_denial(binding, lambda: _load(binding, path))


@pytest.mark.parametrize(
    "encoded",
    (
        b"\xef\xbb\xbf" + json.dumps(RENDER_MANIFEST).encode(),
        json.dumps(RENDER_MANIFEST).encode("utf-16"),
        b'{"render_staging_api_service_id":"\xed\xa0\x80"}',
    ),
    ids=("utf8-bom", "utf-16", "lone-surrogate"),
)
def test_loader_decodes_strictly_as_utf8_on_every_platform(
    binding: ModuleType, tmp_path: Path, encoded: bytes
) -> None:
    """G3/S3-3: the bytes-returning helper must not widen JSON's own encoding detection."""
    path = _private_manifest(tmp_path, RENDER_MANIFEST)
    path.write_bytes(encoded)
    _assert_fixed_denial(binding, lambda: _load(binding, path))


RENDER_DEVELOPMENT_SERVICE: Final = "srv-d0development00000000"
RENDER_STAGING_SERVICE: Final = "srv-d0staging000000000000"
RENDER_DEVELOPMENT_HOST: Final = "tailtag-api-development.onrender.com"
RENDER_STAGING_HOST: Final = "tailtag-api-staging.onrender.com"


def _expected_render_digest(environment: str, service_id: str) -> str:
    # Independent vector for the Render namespace, framing, and environment.
    return hashlib.sha256(
        f"tailtag-render-api-v1\0{environment}\0{service_id}".encode()
    ).hexdigest()


def _expected_render_host_digest(environment: str, hostname: str) -> str:
    return hashlib.sha256(
        f"tailtag-render-api-host-v1\0{environment}\0{hostname}".encode()
    ).hexdigest()


def _install_render_pins(binding: ModuleType, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            "development": _expected_render_digest(
                "development", RENDER_DEVELOPMENT_SERVICE
            ),
            "staging": _expected_render_digest("staging", RENDER_STAGING_SERVICE),
        },
    )
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_HOST_DIGESTS",
        {
            "development": _expected_render_host_digest(
                "development", RENDER_DEVELOPMENT_HOST
            ),
            "staging": _expected_render_host_digest("staging", RENDER_STAGING_HOST),
        },
    )


def _render_runtime(service_id: str = RENDER_STAGING_SERVICE) -> dict[str, str]:
    return {
        "RENDER": "true",
        "RENDER_SERVICE_ID": service_id,
        "RENDER_SERVICE_NAME": "development",
    }


def test_shipped_render_pins_deny_unreviewed_services(
    binding: ModuleType,
) -> None:
    """AC11: the shipped pins accept no service except the reviewed ones."""
    for service_id in (RENDER_DEVELOPMENT_SERVICE, RENDER_STAGING_SERVICE):
        _assert_fixed_denial(
            binding,
            lambda service_id=service_id: binding.validate_runtime_target(
                _render_runtime(service_id)
            ),
        )


@pytest.mark.parametrize(
    ("service_id", "environment"),
    (
        (RENDER_DEVELOPMENT_SERVICE, "development"),
        (RENDER_STAGING_SERVICE, "staging"),
    ),
)
def test_render_environment_comes_only_from_the_matched_service_pin(
    binding: ModuleType,
    monkeypatch: MonkeyPatch,
    service_id: str,
    environment: str,
) -> None:
    """AC10/AC11: the service name and other variables cannot pick the environment."""
    _install_render_pins(binding, monkeypatch)
    assert binding.validate_runtime_target(_render_runtime(service_id)) == environment


@pytest.mark.parametrize(
    ("environment", "hostname"),
    (
        ("development", RENDER_DEVELOPMENT_HOST),
        ("staging", RENDER_STAGING_HOST),
    ),
)
def test_render_hostname_pins_return_only_the_reviewed_origin(
    binding: ModuleType, monkeypatch: MonkeyPatch, environment: str, hostname: str
) -> None:
    """AC12: each environment accepts only its own pinned onrender.com host."""
    _install_render_pins(binding, monkeypatch)
    assert binding.pinned_render_origin(environment, hostname) == f"https://{hostname}"
    other = (
        RENDER_STAGING_HOST
        if hostname == RENDER_DEVELOPMENT_HOST
        else RENDER_DEVELOPMENT_HOST
    )
    for environment_name, candidate in (
        (environment, other),
        (environment, hostname.upper()),
        (environment, f"{hostname}."),
        ("production", hostname),
    ):
        _assert_fixed_denial(
            binding,
            lambda e=environment_name, h=candidate: binding.pinned_render_origin(e, h),
        )


def test_shipped_render_hostname_pins_deny_unreviewed_hosts(
    binding: ModuleType,
) -> None:
    """AC12: the shipped pins accept no host except the reviewed ones."""
    _assert_fixed_denial(
        binding,
        lambda: binding.pinned_render_origin("development", "other-api.onrender.com"),
    )


@pytest.mark.parametrize(
    "actual",
    (
        {**_render_runtime(), "RENDER_SERVICE_ID": "srv-d0unpinned00000000000"},
        {**_render_runtime(), "RENDER_SERVICE_ID": RENDER_STAGING_SERVICE.upper()},
        {**_render_runtime(), "RENDER_SERVICE_ID": ""},
        {**_render_runtime(), "RENDER": "false"},
        {"RENDER_SERVICE_ID": RENDER_STAGING_SERVICE},
        {"RENDER": "true"},
        {**_render_runtime(), "RAILWAY_ENVIRONMENT_NAME": "staging"},
        {**_render_runtime(), "RAILWAY_PROJECT_ID": "retired"},
        {"RAILWAY_SERVICE_NAME": "api"},
        {},
    ),
    ids=(
        "unpinned-service",
        "noncanonical-service",
        "empty-service",
        "render-flag-false",
        "missing-render-flag",
        "missing-service",
        "render-with-retired-name",
        "render-with-retired-project",
        "retired-marker-only",
        "no-markers",
    ),
)
def test_render_runtime_guard_denies_unpinned_incomplete_or_retired_hosts(
    binding: ModuleType, monkeypatch: MonkeyPatch, actual: Mapping[str, str]
) -> None:
    """AC11: an unknown service or any Railway marker fails closed."""
    _install_render_pins(binding, monkeypatch)
    _assert_fixed_denial(binding, lambda: binding.validate_runtime_target(actual))
