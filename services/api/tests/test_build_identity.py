"""Acceptance contract for immutable backend build identity."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

from tests.process_support import minimal_environment
from tests.render_target_support import STAGING_SERVICE, pin_render_services

WRITER = Path(__file__).resolve().parents[1] / "docker" / "write_build_identity.py"
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


def test_missing_local_metadata_is_explicit_null_without_inventing_source_identity(
    build_identity: ModuleType, tmp_path: Path
) -> None:
    """AC-1/2: contributor builds with no build argument report absent source identity."""
    identity = build_identity._load_identity(
        tmp_path / "absent-build-identity.json", {"UNRELATED_SECRET": "unrelated"}
    )

    assert identity == {"source_sha": None, "deployment_id": None, "environment": None}


def test_get_identity_uses_the_fixed_image_path_and_actual_runtime_environment(
    build_identity: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-2/3: callers cannot select a metadata path or inject an alternate environment."""
    observed: list[tuple[Path, Mapping[str, str]]] = []
    environment = render_environment(RENDER_STAGING_SERVICE)
    expected = {
        "source_sha": SOURCE_SHA,
        "deployment_id": None,
        "environment": "staging",
    }

    def load_identity(
        path: Path, supplied_environment: Mapping[str, str]
    ) -> dict[str, str | None]:
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
        "deployment_id": None,
        "environment": "staging",
    }
    monkeypatch.setattr(build_identity, "get_identity", lambda: expected)
    monkeypatch.setattr(
        build_identity.os, "environ", render_environment(RENDER_STAGING_SERVICE)
    )

    assert build_identity.main() == 0
    captured = capsys.readouterr()

    assert captured.err == ""
    assert json.loads(captured.out) == expected
    assert set(json.loads(captured.out)) == set(expected)
    rendered = captured.out + captured.err
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.usefixtures("render_pins")
@pytest.mark.parametrize(
    ("has_metadata", "source_sha"),
    (
        (False, None),
        (True, None),
        (True, "malformed-source-sha-secret"),
        (True, SOURCE_SHA[:7]),
    ),
)
def test_load_identity_rejects_missing_or_malformed_staging_values(
    build_identity: ModuleType,
    tmp_path: Path,
    has_metadata: bool,
    source_sha: object,
) -> None:
    """AC-8: incomplete or malformed Staging data has no reusable identity result."""
    metadata = tmp_path / "build-identity.json"
    if has_metadata:
        write_metadata(metadata, source_sha)

    with pytest.raises(ValueError):
        build_identity._load_identity(
            metadata, render_environment(RENDER_STAGING_SERVICE)
        )


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


@pytest.mark.usefixtures("render_pins")
def test_clock_and_process_start_values_cannot_change_loaded_identity(
    build_identity: ModuleType, tmp_path: Path
) -> None:
    """AC-1/4/8: identity is stable across process timing and restart metadata."""
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, SOURCE_SHA)

    before = build_identity._load_identity(
        metadata,
        render_environment(
            RENDER_STAGING_SERVICE, PROCESS_STARTED_AT="2026-09-17T00:00:00Z"
        ),
    )
    after = build_identity._load_identity(
        metadata,
        render_environment(
            RENDER_STAGING_SERVICE, PROCESS_STARTED_AT="2030-01-01T00:00:00Z"
        ),
    )

    assert after == before


RENDER_DEVELOPMENT_SERVICE = "srv-d0development00000000"
RENDER_STAGING_SERVICE = "srv-d0staging000000000000"


@pytest.fixture
def render_pins(monkeypatch: MonkeyPatch) -> None:
    """Pin synthetic Render services through the binding's reviewed seam."""
    binding = importlib.import_module("config.replacement_target_binding")
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            "development": binding.fingerprint_render_service(
                "development", RENDER_DEVELOPMENT_SERVICE
            ),
            "staging": binding.fingerprint_render_service(
                "staging", RENDER_STAGING_SERVICE
            ),
        },
    )


def render_environment(service_id: str, **overrides: str) -> dict[str, str]:
    """Supply Render runtime values plus a misleading Git variable."""
    return {
        "RENDER": "true",
        "RENDER_SERVICE_ID": service_id,
        "RENDER_SERVICE_NAME": "staging",
        "RENDER_GIT_COMMIT": RUNTIME_SHA,
        **overrides,
    }


@pytest.mark.usefixtures("render_pins")
@pytest.mark.parametrize(
    ("service_id", "environment"),
    (
        (RENDER_DEVELOPMENT_SERVICE, "development"),
        (RENDER_STAGING_SERVICE, "staging"),
    ),
)
def test_render_identity_uses_baked_sha_pinned_environment_and_no_deployment(
    build_identity: ModuleType, tmp_path: Path, service_id: str, environment: str
) -> None:
    """AC10: Render has no runtime deploy ID, and the pin names the environment."""
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, SOURCE_SHA)

    assert build_identity._load_identity(metadata, render_environment(service_id)) == {
        "source_sha": SOURCE_SHA,
        "deployment_id": None,
        "environment": environment,
    }


RENDER_DEVELOPMENT_CLEANUP = "srv-d0developmentcleanup0"
RENDER_STAGING_CLEANUP = "srv-d0stagingcleanup00000"


@pytest.mark.usefixtures("render_pins")
def test_a_pinned_cleanup_cron_names_its_environment_but_passes_no_guard(
    build_identity: ModuleType, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """#507 AC41, AC42: cron pins widen build identity only, and start empty."""
    binding = importlib.import_module("config.replacement_target_binding")
    staging_target = importlib.import_module("accounts.staging_target")
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, SOURCE_SHA)
    actual = render_environment(RENDER_STAGING_CLEANUP)
    with pytest.raises(ValueError):
        build_identity._load_identity(metadata, actual)
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_CLEANUP_DIGESTS",
        {
            "development": binding.fingerprint_render_service(
                "development", RENDER_DEVELOPMENT_CLEANUP
            ),
            "staging": binding.fingerprint_render_service(
                "staging", RENDER_STAGING_CLEANUP
            ),
        },
    )

    identity = build_identity._load_identity(metadata, actual)

    assert identity == {
        "source_sha": SOURCE_SHA,
        "deployment_id": None,
        "environment": "staging",
    }
    with pytest.raises(binding.TargetBindingError):
        binding.validate_runtime_target(actual)
    assert staging_target.staging_platform(actual) is None


@pytest.mark.usefixtures("render_pins")
def test_render_staging_identity_requires_a_baked_source_sha(
    build_identity: ModuleType, tmp_path: Path
) -> None:
    """AC10: Render Staging has no fallback for a missing baked SHA."""
    with pytest.raises(ValueError):
        build_identity._load_identity(
            tmp_path / "absent-build-identity.json",
            render_environment(RENDER_STAGING_SERVICE),
        )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        ({}, None),
        ({"RAILWAY_GIT_COMMIT_SHA": SOURCE_SHA}, None),
        ({"RENDER_GIT_COMMIT": SOURCE_SHA}, SOURCE_SHA),
        ({"RENDER_GIT_COMMIT": "not-a-sha"}, "fail"),
    ),
    ids=("none", "retired-argument-ignored", "render", "malformed"),
)
def test_image_writer_bakes_one_host_build_sha_or_fails(
    tmp_path: Path, arguments: Mapping[str, str], expected: str | None
) -> None:
    """AC14: the Render build argument works, and a malformed one fails the build."""
    output = tmp_path / "opt" / "build-identity.json"
    completed = subprocess.run(
        [sys.executable, str(WRITER), str(output)],
        env={**minimal_environment(), **arguments},
        capture_output=True,
        text=True,
        check=False,
    )

    if expected == "fail":
        assert completed.returncode != 0
        assert not output.exists()
    else:
        assert completed.returncode == 0
        assert json.loads(output.read_text()) == {"source_sha": expected}


@pytest.mark.parametrize(
    "marker",
    (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_PROJECT_ID",
    ),
)
@pytest.mark.parametrize("render", (True, False), ids=("render", "no-render-markers"))
def test_any_retired_host_marker_fails_closed(
    build_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    marker: str,
    render: bool,
) -> None:
    """#412 AC11: identity loads without a Railway marker and fails with any one."""
    pin_render_services(monkeypatch)
    metadata = tmp_path / "build-identity.json"
    write_metadata(metadata, SOURCE_SHA)
    environment = (
        {"RENDER": "true", "RENDER_SERVICE_ID": STAGING_SERVICE} if render else {}
    )

    assert build_identity._load_identity(metadata, environment)["source_sha"] == (
        SOURCE_SHA
    )
    with pytest.raises(ValueError):
        build_identity._load_identity(metadata, {**environment, marker: "retired"})
