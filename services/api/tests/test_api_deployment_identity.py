"""Acceptance contract for exact Railway deployment identity lookup."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest
from pytest import MonkeyPatch

SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
SECOND_SOURCE_SHA = "d" * 40
SECOND_DEPLOYMENT_ID = "1b6a4b35-4e94-4775-a4b9-304205c75786"
DEPLOYMENT_TIMESTAMP = "2026-09-17T00:16:10.526Z"
PROJECT_ID = "85324de4-be6a-49c3-a3f9-6cac13877849"
SERVICE_ID = "2247da27-97df-4d5d-b1dc-d21eeb7901d9"
SENSITIVE_VALUES = (
    "stdin-untrusted-secret",
    "railway-cli-stderr-secret",
    "graphql-error-secret",
    "control-plane-extra-metadata-secret",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def deployment_identity() -> ModuleType:
    """Load the maintainer command only once its implementation exists."""
    return importlib.import_module("scripts.api_deployment_identity")


def backend_identity(**overrides: object) -> dict[str, object]:
    """Return the exact safe tuple emitted by the backend operator command."""
    return {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
        **overrides,
    }


def deployment_record(**overrides: object) -> dict[str, object]:
    """Represent the one deployment object returned from Railway's exact-ID query."""
    return {
        "id": DEPLOYMENT_ID,
        "createdAt": DEPLOYMENT_TIMESTAMP,
        "meta": {
            "commitHash": SOURCE_SHA,
            "unapproved": "control-plane-extra-metadata-secret",
        },
        "projectId": PROJECT_ID,
        "environment": {"name": "staging"},
        "serviceId": SERVICE_ID,
        **overrides,
    }


def test_join_deployment_returns_only_validated_exact_record_fields(
    deployment_identity: ModuleType,
) -> None:
    """AC-4/6/7/8: createdAt from the matching deployment is the sole timestamp."""
    joined = deployment_identity.join_deployment(
        backend_identity(), deployment_record()
    )

    assert joined == {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
        "deployment_timestamp": DEPLOYMENT_TIMESTAMP,
    }
    assert set(joined) == {
        "source_sha",
        "deployment_id",
        "environment",
        "deployment_timestamp",
    }


@pytest.mark.parametrize(
    "record",
    (
        deployment_record(id="1b6a4b35-4e94-4775-a4b9-304205c75786"),
        deployment_record(meta={"commitHash": "b" * 40}),
        deployment_record(projectId="3b8d2a03-38ec-4bf7-91f1-1e562b9f4793"),
        deployment_record(environment={"name": "development"}),
        deployment_record(serviceId="2d913bc3-0fa2-436e-bd21-6b55847cf65e"),
        deployment_record(createdAt="2026-09-17T00:16:10.526"),
        deployment_record(createdAt=None, updatedAt="2030-01-01T00:00:00.000Z"),
    ),
)
def test_join_deployment_rejects_mismatched_target_identity_or_non_aware_timestamp(
    deployment_identity: ModuleType, record: Mapping[str, object]
) -> None:
    """AC-4/6/7/8: neither another deployment nor a derived timestamp can join."""
    with pytest.raises(ValueError):
        deployment_identity.join_deployment(backend_identity(), record)


@pytest.mark.parametrize(
    ("source_sha", "deployment_id"),
    ((SOURCE_SHA, DEPLOYMENT_ID), (SECOND_SOURCE_SHA, SECOND_DEPLOYMENT_ID)),
)
def test_main_queries_only_the_captured_deployment_id_and_renders_allowlisted_json(
    deployment_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source_sha: str,
    deployment_id: str,
) -> None:
    """AC-4/6/7/8: the CLI receives exact D and cannot emit record metadata."""
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def railway_run(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            ["railway", "api"],
            0,
            stdout=json.dumps(
                {
                    "data": {
                        "deployment": deployment_record(
                            id=deployment_id,
                            meta={
                                "commitHash": source_sha,
                                "unapproved": "control-plane-extra-metadata-secret",
                            },
                        )
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                backend_identity(source_sha=source_sha, deployment_id=deployment_id)
            )
        ),
    )
    monkeypatch.setattr(deployment_identity.subprocess, "run", railway_run)

    assert deployment_identity.main() == 0
    captured = capsys.readouterr()

    assert captured.err == ""
    assert json.loads(captured.out) == {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": "staging",
        "deployment_timestamp": DEPLOYMENT_TIMESTAMP,
    }
    assert len(calls) == 1
    command, options = calls[0]
    assert len(command) == 1
    assert isinstance(command[0], (list, tuple))
    arguments = [
        str(argument)
        for argument in cast(list[object] | tuple[object, ...], command[0])
    ]
    variables_index = arguments.index("--variables")
    assert json.loads(arguments[variables_index + 1]) == {"id": deployment_id}
    assert any("deployment(id: $id)" in argument for argument in arguments)
    assert options.get("shell") is False
    rendered = captured.out + captured.err
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    "raw_input",
    (
        json.dumps({**backend_identity(), "unexpected": "stdin-untrusted-secret"}),
        "{not valid json stdin-untrusted-secret}",
    ),
)
def test_main_rejects_untrusted_or_extra_stdin_before_contacting_railway(
    deployment_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw_input: str,
) -> None:
    """AC-5/8/SECURITY: malformed input cannot become a control-plane request or output."""
    calls: list[object] = []

    def forbidden_run(*args: object, **kwargs: object) -> NoReturn:
        calls.append((args, kwargs))
        raise AssertionError("invalid stdin must not invoke Railway")

    monkeypatch.setattr(sys, "stdin", io.StringIO(raw_input))
    monkeypatch.setattr(deployment_identity.subprocess, "run", forbidden_run)

    assert deployment_identity.main() != 0
    captured = capsys.readouterr()

    assert calls == []
    assert captured.out == ""
    for value in SENSITIVE_VALUES:
        assert value not in captured.err


@pytest.mark.parametrize(
    "completed",
    (
        subprocess.CompletedProcess(
            ("railway", "api"), 1, stdout="", stderr="railway-cli-stderr-secret"
        ),
        subprocess.CompletedProcess(
            ("railway", "api"),
            0,
            stdout=json.dumps({"errors": [{"message": "graphql-error-secret"}]}),
            stderr="",
        ),
    ),
)
def test_main_sanitizes_control_plane_failures_without_fabricating_a_tuple(
    deployment_identity: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed: subprocess.CompletedProcess[str],
) -> None:
    """AC-4/8/SECURITY: raw CLI and GraphQL errors cannot cross the command boundary."""

    def railway_run(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return completed

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(backend_identity())))
    monkeypatch.setattr(deployment_identity.subprocess, "run", railway_run)

    assert deployment_identity.main() != 0
    captured = capsys.readouterr()

    assert captured.out == ""
    for value in SENSITIVE_VALUES:
        assert value not in captured.err
