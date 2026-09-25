"""Offline acceptance tests for the replacement Railway generation binding.

All UUIDs here are synthetic. The tests exercise the reviewed internal seam,
never the owner-only target manifest or a provider connection.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest
from pytest import MonkeyPatch

PROJECT: Final = "a1111111-1111-4111-8111-111111111111"
DEVELOPMENT: Final = "22222222-2222-4222-8222-222222222222"
STAGING: Final = "33333333-3333-4333-8333-333333333333"
API: Final = "d4444444-4444-4444-8444-444444444444"
POSTGRES: Final = "55555555-5555-4555-8555-555555555555"
OLD_PROJECT: Final = "66666666-6666-4666-8666-666666666666"
RESET_ENVIRONMENT: Final = "77777777-7777-4777-8777-777777777777"
SENSITIVE: Final = "private-target-value-must-never-appear"
FIXED_FAILURE: Final = "Replacement target binding unavailable"
SELECTORS: Final = {
    "rebuild_railway_project_id": PROJECT,
    "rebuild_development_environment_id": DEVELOPMENT,
    "rebuild_staging_environment_id": STAGING,
    "rebuild_api_service_id": API,
    "rebuild_postgres_service_id": POSTGRES,
}
ROLES: Final = {
    "development-api": (PROJECT, DEVELOPMENT, API),
    "development-postgres": (PROJECT, DEVELOPMENT, POSTGRES),
    "staging-api": (PROJECT, STAGING, API),
    "staging-postgres": (PROJECT, STAGING, POSTGRES),
}


@pytest.fixture
def binding() -> ModuleType:
    """Exercise the intentionally package-internal target binding seam."""
    return importlib.import_module("config.replacement_target_binding")


def _expected_digest(role: str, values: tuple[str, str, str]) -> str:
    # This independent contract vector catches changed field order, framing,
    # namespace tag, or omitted logical role.
    return hashlib.sha256(
        "\0".join(("tailtag-rebuild-v1", role, *values)).encode("utf-8")
    ).hexdigest()


def _install_synthetic_pins(binding: ModuleType, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        binding,
        "_EXPECTED_DIGESTS",
        {role: _expected_digest(role, values) for role, values in ROLES.items()},
    )


def _assert_fixed_denial(binding: ModuleType, operation: Callable[[], object]) -> None:
    with pytest.raises(binding.TargetBindingError) as caught:
        operation()
    assert str(caught.value) == FIXED_FAILURE
    rendered = str(caught.value)
    for private_value in (*SELECTORS.values(), SENSITIVE):
        assert private_value not in rendered


@pytest.mark.parametrize("role", tuple(ROLES))
def test_fingerprint_matches_independent_role_bound_sha256_vector(
    binding: ModuleType, role: str
) -> None:
    """T-1: order, namespace tag, and logical role are all committed."""
    values = ROLES[role]
    assert binding.fingerprint_tuple(role, *values) == _expected_digest(role, values)


@pytest.mark.parametrize(
    ("role", "values"),
    (
        ("staging-api", (PROJECT, STAGING, POSTGRES)),
        ("development-api", (PROJECT, STAGING, API)),
        ("staging-postgres", (OLD_PROJECT, STAGING, POSTGRES)),
    ),
)
def test_fingerprint_changes_for_other_canonical_tuples(
    binding: ModuleType, role: str, values: tuple[str, str, str]
) -> None:
    """T-1: valid but unpinned project or role tuples hash differently."""
    assert binding.fingerprint_tuple(role, *values) != _expected_digest(
        role, ROLES[role]
    )


@pytest.mark.parametrize(
    ("role", "values"),
    (
        ("other-role", (PROJECT, STAGING, API)),
        ("staging-api", (PROJECT.upper(), STAGING, API)),
        ("staging-api", (PROJECT, "not-a-uuid", API)),
    ),
)
def test_fingerprint_rejects_unknown_roles_and_noncanonical_uuids(
    binding: ModuleType, role: str, values: tuple[str, str, str]
) -> None:
    """T-1: malformed selectors and an unapproved tuple role fail closed."""
    _assert_fixed_denial(binding, lambda: binding.fingerprint_tuple(role, *values))


def test_valid_synthetic_manifest_selectors_match_all_four_immutable_pins(
    binding: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """T-1/T-2: a complete selector set passes its four code-owned pins."""
    _install_synthetic_pins(binding, monkeypatch)
    assert binding.validate_selectors(SELECTORS) is None


@pytest.mark.parametrize(
    "changed",
    (
        {"rebuild_railway_project_id": OLD_PROJECT},
        {"rebuild_development_environment_id": STAGING},
        {"rebuild_staging_environment_id": DEVELOPMENT},
        {"rebuild_api_service_id": POSTGRES},
        {"rebuild_postgres_service_id": API},
        {"rebuild_staging_environment_id": "not-a-uuid"},
        {"rebuild_railway_project_id": PROJECT.upper()},
    ),
)
def test_manifest_cannot_redirect_operation_even_with_self_declared_expectation(
    binding: ModuleType, monkeypatch: MonkeyPatch, changed: Mapping[str, str]
) -> None:
    """T-1/T-2: a coherent-looking edited manifest cannot become authority."""
    _install_synthetic_pins(binding, monkeypatch)
    altered = {
        **SELECTORS,
        **changed,
        "expected_environment_id": changed.get(
            "rebuild_staging_environment_id", STAGING
        ),
        "expected_digest": SENSITIVE,
    }
    _assert_fixed_denial(binding, lambda: binding.validate_selectors(altered))


@pytest.mark.parametrize("missing_key", tuple(SELECTORS))
def test_missing_selector_fails_without_implicit_default(
    binding: ModuleType, monkeypatch: MonkeyPatch, missing_key: str
) -> None:
    """T-2: every selected provider identity is required explicitly."""
    _install_synthetic_pins(binding, monkeypatch)
    _assert_fixed_denial(
        binding,
        lambda: binding.validate_selectors(
            {key: value for key, value in SELECTORS.items() if key != missing_key}
        ),
    )


def _private_manifest(tmp_path: Path, data: str | Mapping[str, object]) -> Path:
    parent = tmp_path / "tailtag"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    path = parent / "staging-clean-rebuild-targets.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    path.chmod(0o600)
    return path


def test_loader_extracts_only_selectors_from_owner_only_manifest(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8: unrelated allocation metadata cannot act as target authority."""
    path = _private_manifest(
        tmp_path,
        {**SELECTORS, "allocation_note": SENSITIVE, "expected_digest": SENSITIVE},
    )
    before = path.read_bytes()
    assert binding.load_local_manifest(path) == SELECTORS
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "document",
    (
        "{bad json " + SENSITIVE,
        "[]",
        json.dumps({"rebuild_railway_project_id": PROJECT}),
        '{"rebuild_railway_project_id":"'
        + PROJECT
        + '","rebuild_railway_project_id":"'
        + OLD_PROJECT
        + '"}',
        json.dumps({**SELECTORS, "rebuild_api_service_id": "not-a-uuid"}),
    ),
)
def test_loader_rejects_malformed_missing_or_ambiguous_manifest(
    binding: ModuleType, tmp_path: Path, document: str
) -> None:
    """T-2/T-8: malformed JSON and duplicate keys fail with fixed output."""
    path = _private_manifest(tmp_path, document)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))


def test_loader_sanitizes_json_integer_conversion_failure(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8: parser limits cannot leak an untrusted value or raw exception."""
    oversized_integer = "9" * 5000
    path = _private_manifest(
        tmp_path, '{"untrusted_allocation_count":' + oversized_integer + "}"
    )

    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))


def test_loader_sanitizes_excessive_json_nesting(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2/T-8: a bounded file can still exceed the JSON parser depth."""
    path = _private_manifest(tmp_path, "[" * 32000 + "0" + "]" * 32000)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))


def test_loader_rejects_missing_symlink_and_wrong_modes(
    binding: ModuleType, tmp_path: Path
) -> None:
    """T-2: wrong owner-only boundary is not silently accepted."""
    path = _private_manifest(tmp_path, SELECTORS)
    _assert_fixed_denial(
        binding, lambda: binding.load_local_manifest(path.parent / "missing.json")
    )

    alias = path.parent / "alias.json"
    alias.symlink_to(path)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(alias))

    path.chmod(0o644)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))
    path.chmod(0o600)
    path.parent.chmod(0o755)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))


def test_loader_rejects_wrong_owner_without_exposing_path_or_values(
    binding: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """T-2/T-8: current-process owner is part of the private-file boundary."""
    path = _private_manifest(tmp_path, SELECTORS)
    current_uid = os.getuid()
    monkeypatch.setattr(binding.os, "getuid", lambda: current_uid + 1)
    _assert_fixed_denial(binding, lambda: binding.load_local_manifest(path))


def _runtime(environment: str, service: str = "api") -> dict[str, str]:
    return {
        "RAILWAY_PROJECT_ID": PROJECT,
        "RAILWAY_ENVIRONMENT_ID": STAGING if environment == "staging" else DEVELOPMENT,
        "RAILWAY_SERVICE_ID": API if service == "api" else POSTGRES,
        "RAILWAY_ENVIRONMENT_NAME": environment,
        "RAILWAY_SERVICE_NAME": service,
        # #204's random reset UUID is deliberately a different namespace.
        "TAILTAG_STAGING_RESET_ENVIRONMENT_ID": RESET_ENVIRONMENT,
    }


@pytest.mark.parametrize("environment", ("development", "staging"))
def test_runtime_guard_accepts_only_actual_pinned_api_tuple_with_distinct_reset_uuid(
    binding: ModuleType, monkeypatch: MonkeyPatch, environment: str
) -> None:
    """T-1/T-3/T-5: Railway identity is independent of #204 reset identity."""
    _install_synthetic_pins(binding, monkeypatch)
    assert binding.validate_runtime_target(_runtime(environment)) is None


@pytest.mark.parametrize(
    "changed",
    (
        {"RAILWAY_PROJECT_ID": OLD_PROJECT},
        {"RAILWAY_ENVIRONMENT_ID": DEVELOPMENT},
        {"RAILWAY_SERVICE_ID": POSTGRES},
        {"RAILWAY_ENVIRONMENT_NAME": "development"},
        {"RAILWAY_ENVIRONMENT_NAME": "Staging"},
        {"RAILWAY_SERVICE_NAME": "Postgres"},
        {"RAILWAY_SERVICE_NAME": "API"},
        {"RAILWAY_PROJECT_ID": "not-a-uuid"},
        {"RAILWAY_SERVICE_ID": API.upper()},
        {"RAILWAY_ENVIRONMENT_ID": ""},
    ),
)
def test_runtime_guard_rejects_old_generation_swaps_names_and_malformed_fields(
    binding: ModuleType, monkeypatch: MonkeyPatch, changed: Mapping[str, str]
) -> None:
    """T-1/T-3: display names or a shared source SHA cannot override actual IDs."""
    _install_synthetic_pins(binding, monkeypatch)
    actual = {
        **_runtime("staging"),
        **changed,
        "RAILWAY_GIT_COMMIT_SHA": "a" * 40,
        "EXPECTED_TARGET_DIGEST": _expected_digest(
            "staging-api", (OLD_PROJECT, STAGING, API)
        ),
    }
    _assert_fixed_denial(binding, lambda: binding.validate_runtime_target(actual))


@pytest.mark.parametrize("missing", tuple(_runtime("staging").keys())[:5])
def test_runtime_guard_requires_every_actual_railway_field(
    binding: ModuleType, monkeypatch: MonkeyPatch, missing: str
) -> None:
    """T-1/T-3: absent runtime ID or name cannot acquire a default."""
    _install_synthetic_pins(binding, monkeypatch)
    actual = _runtime("staging")
    actual.pop(missing)
    _assert_fixed_denial(binding, lambda: binding.validate_runtime_target(actual))
