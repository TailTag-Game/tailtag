"""Acceptance contract for immutable backend build identity."""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
SECOND_SOURCE_SHA = "d" * 40
RUNTIME_SHA = "a" * 40
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
SECOND_DEPLOYMENT_ID = "1b6a4b35-4e94-4775-a4b9-304205c75786"
SENSITIVE_VALUES = (
    RUNTIME_SHA,
    "runtime-sha-must-not-override-artifact",
    "unrelated-runtime-secret",
    "malformed-source-sha-secret",
    "malformed-deployment-id-secret",
    "staging unsafe",
)


@pytest.fixture
def build_identity() -> ModuleType:
    """Load the new reusable identity component after its absence is explicit."""
    return importlib.import_module("config.build_identity")


def write_metadata(path: Path, source_sha: object) -> None:
    """Create the one-field image metadata artifact represented by the contract."""
    path.write_text(json.dumps({"source_sha": source_sha}))


def runtime_environment(**overrides: str) -> dict[str, str]:
    """Supply only the runtime Railway identity values plus hostile ambient data."""
    return {
        "RAILWAY_DEPLOYMENT_ID": DEPLOYMENT_ID,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_GIT_COMMIT_SHA": RUNTIME_SHA,
        "UNRELATED_SECRET": "unrelated-runtime-secret",
        **overrides,
    }


@pytest.mark.parametrize(
    ("source_sha", "deployment_id"),
    ((SOURCE_SHA, DEPLOYMENT_ID), (SECOND_SOURCE_SHA, SECOND_DEPLOYMENT_ID)),
)
def test_load_identity_uses_only_baked_sha_and_explicit_runtime_fields(
    build_identity: ModuleType,
    tmp_path: Path,
    source_sha: str,
    deployment_id: str,
) -> None:
    """AC-1/2/3/8: runtime SHA and ambient configuration cannot replace or expand identity."""
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, source_sha)

    identity = build_identity._load_identity(
        metadata,
        runtime_environment(
            RAILWAY_DEPLOYMENT_ID=deployment_id,
            RAILWAY_GIT_COMMIT_SHA="runtime-sha-must-not-override-artifact",
        ),
    )

    assert identity == {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": "staging",
    }


def test_missing_local_metadata_is_explicit_null_without_inventing_source_identity(
    build_identity: ModuleType, tmp_path: Path
) -> None:
    """AC-1/2: contributor builds with no build argument report absent source identity."""
    identity = build_identity._load_identity(
        tmp_path / "absent-build-identity.json",
        runtime_environment(RAILWAY_ENVIRONMENT_NAME="development"),
    )

    assert identity == {
        "source_sha": None,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "development",
    }


def test_get_identity_uses_the_fixed_image_path_and_actual_runtime_environment(
    build_identity: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-2/3: callers cannot select a metadata path or inject an alternate environment."""
    observed: list[tuple[Path, Mapping[str, str]]] = []
    environment = runtime_environment()
    expected = {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
    }

    def load_identity(
        path: Path, supplied_environment: Mapping[str, str]
    ) -> dict[str, str]:
        observed.append((path, supplied_environment))
        return expected

    monkeypatch.setattr(build_identity, "_load_identity", load_identity)
    monkeypatch.setattr(build_identity.os, "environ", environment)

    assert build_identity.get_identity() == expected
    assert observed == [(Path("/opt/tailtag/build-identity.json"), environment)]


def test_main_emits_the_exact_three_field_allowlist(
    build_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-3/5/8: operator output cannot expose runtime SHA, secrets, or a timestamp."""
    # Replace the parsing seam with the valid observable identity to exercise main's
    # rendering boundary without making the production metadata path configurable.
    expected = {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
    }
    monkeypatch.setattr(build_identity, "get_identity", lambda: expected)
    monkeypatch.setattr(build_identity.os, "environ", runtime_environment())

    assert build_identity.main() == 0
    captured = capsys.readouterr()

    assert captured.err == ""
    assert json.loads(captured.out) == expected
    assert set(json.loads(captured.out)) == set(expected)
    rendered = captured.out + captured.err
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    ("has_metadata", "source_sha", "environment"),
    (
        (False, None, runtime_environment()),
        (True, None, runtime_environment()),
        (True, "malformed-source-sha-secret", runtime_environment()),
        (True, SOURCE_SHA[:7], runtime_environment()),
        (True, SOURCE_SHA, runtime_environment(RAILWAY_DEPLOYMENT_ID="")),
        (
            True,
            SOURCE_SHA,
            runtime_environment(RAILWAY_DEPLOYMENT_ID="malformed-deployment-id-secret"),
        ),
        (
            True,
            SOURCE_SHA,
            runtime_environment(RAILWAY_ENVIRONMENT_NAME="staging unsafe"),
        ),
    ),
)
def test_load_identity_rejects_missing_or_malformed_staging_values(
    build_identity: ModuleType,
    tmp_path: Path,
    has_metadata: bool,
    source_sha: object,
    environment: Mapping[str, str],
) -> None:
    """AC-8: incomplete or malformed Staging data has no reusable identity result."""
    metadata = tmp_path / "build-identity.json"
    if has_metadata:
        write_metadata(metadata, source_sha)

    with pytest.raises(ValueError):
        build_identity._load_identity(metadata, environment)


def test_main_sanitizes_identity_component_failures(
    build_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-8/SECURITY: metadata parsing errors never disclose their raw reason."""

    def failing_get_identity() -> NoReturn:
        raise ValueError("malformed-source-sha-secret")

    monkeypatch.setattr(
        build_identity,
        "get_identity",
        failing_get_identity,
    )

    assert build_identity.main() != 0
    captured = capsys.readouterr()

    assert captured.out == ""
    for value in SENSITIVE_VALUES:
        assert value not in captured.err


def test_clock_and_process_start_values_cannot_change_loaded_identity(
    build_identity: ModuleType, tmp_path: Path
) -> None:
    """AC-1/4/8: identity is stable across process timing and restart metadata."""
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, SOURCE_SHA)

    before = build_identity._load_identity(
        metadata,
        runtime_environment(PROCESS_STARTED_AT="2026-09-17T00:00:00Z"),
    )
    after = build_identity._load_identity(
        metadata,
        runtime_environment(PROCESS_STARTED_AT="2030-01-01T00:00:00Z"),
    )

    assert after == before
