"""Offline acceptance contract for the guarded Staging environment fingerprints."""

from __future__ import annotations

import http.client
import importlib
import logging
import socket
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import httpx
import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_environment_fingerprint.py"
CONFIRMATION = "run-tailtag-environment-fingerprint"
BASE_ENVIRONMENT = {
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "RAILWAY_SERVICE_NAME": "api",
    "TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM": CONFIRMATION,
    "DATABASE_URL": "postgresql://fingerprint-user:opaque@synthetic.invalid:5432/db",
    "DJANGO_SECRET_KEY": "django-fingerprint-secret",
    "CLERK_JWT_KEY": "clerk-fingerprint-verification-key",
    "CLERK_AUTHORIZED_PARTIES": "https://staging-clerk.synthetic.invalid",
    "MEDIA_STORAGE_BUCKET_NAME": "tailtag-staging-media-synthetic",
    "MEDIA_STORAGE_ACCESS_KEY_ID": "fingerprint-access-key",
    "MEDIA_STORAGE_SECRET_ACCESS_KEY": "fingerprint-secret-key",
}
FIELD_GROUPS = {
    "database": ("DATABASE_URL",),
    "django-secret": ("DJANGO_SECRET_KEY",),
    "clerk-verification": ("CLERK_JWT_KEY", "CLERK_AUTHORIZED_PARTIES"),
    "media-bucket": ("MEDIA_STORAGE_BUCKET_NAME",),
    "media-credential": (
        "MEDIA_STORAGE_ACCESS_KEY_ID",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY",
    ),
}
KNOWN_FINGERPRINTS = {
    "database": "65baf6860e6bb7aa",
    "django-secret": "c69fc44389313230",
    "clerk-verification": "929d27c564b696a5",
    "media-bucket": "865543fe346bea1a",
    "media-credential": "b2706122e67b5e86",
}
SENTINELS = tuple(
    BASE_ENVIRONMENT[name] for names in FIELD_GROUPS.values() for name in names
)


def prohibit_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """Fingerprinting configuration is a pure local operation."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("environment fingerprint tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", no_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    for client_type in (httpx.Client, httpx.AsyncClient):
        monkeypatch.setattr(client_type, "request", no_network)
        monkeypatch.setattr(client_type, "send", no_network)


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_outbound_network(monkeypatch)


@pytest.fixture
def fingerprint_script() -> ModuleType:
    """Load the new operator command only after reporting its missing file clearly."""
    assert SCRIPT.is_file(), "scripts/api_environment_fingerprint.py must exist"
    return importlib.import_module("scripts.api_environment_fingerprint")


def invoke_main(
    script: ModuleType,
    monkeypatch: MonkeyPatch,
    environment: Mapping[str, str],
    arguments: list[str] | None = None,
) -> int:
    monkeypatch.setattr(script.os, "environ", dict(environment))
    monkeypatch.setattr(sys, "argv", arguments or ["api_environment_fingerprint.py"])
    return script.main()


def parse_fingerprints(stdout: str, *, target: str) -> dict[str, str]:
    lines = stdout.splitlines()
    assert lines[0] == f"PASS target {target}/api"
    assert len(lines) == len(FIELD_GROUPS) + 1
    parsed: dict[str, str] = {}
    for line in lines[1:]:
        prefix, label, value = line.split(" ", maxsplit=2)
        assert prefix == "FINGERPRINT"
        assert label in FIELD_GROUPS
        assert (
            value.isascii()
            and len(value) == 16
            and all(character in "0123456789abcdef" for character in value)
        )
        parsed[label] = value
    assert set(parsed) == set(FIELD_GROUPS)
    return parsed


def test_environment_fingerprint_entry_point_exists() -> None:
    """AC-6: safe fingerprint evidence has a dedicated guarded command."""
    assert SCRIPT.is_file(), "scripts/api_environment_fingerprint.py must exist"


def test_exact_development_and_staging_identities_emit_only_group_fingerprints(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6: only explicit Railway identities may expose short group fingerprints."""
    staging_exit = invoke_main(fingerprint_script, monkeypatch, BASE_ENVIRONMENT)
    staging_output = capsys.readouterr()
    development_exit = invoke_main(
        fingerprint_script,
        monkeypatch,
        {**BASE_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "development"},
    )
    development_output = capsys.readouterr()

    assert staging_exit == development_exit == 0
    assert staging_output.err == development_output.err == ""
    assert parse_fingerprints(
        staging_output.out, target="staging"
    ) == parse_fingerprints(development_output.out, target="development")
    rendered = (
        staging_output.out
        + staging_output.err
        + development_output.out
        + development_output.err
    )
    for sentinel in SENTINELS:
        assert sentinel not in rendered


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {**BASE_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "Development"},
        {**BASE_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
        {**BASE_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "worker"},
        {**BASE_ENVIRONMENT, "TAILTAG_ENVIRONMENT_FINGERPRINT_CONFIRM": "yes"},
        *(
            {key: value for key, value in BASE_ENVIRONMENT.items() if key != field}
            for fields in FIELD_GROUPS.values()
            for field in fields
        ),
        *(
            {**BASE_ENVIRONMENT, field: ""}
            for fields in FIELD_GROUPS.values()
            for field in fields
        ),
    ),
)
def test_invalid_target_or_incomplete_input_has_one_fixed_failure_and_no_partial_output(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: Mapping[str, str],
) -> None:
    """AC-6/SECURITY: guards and every required field fail before any fingerprint."""
    assert invoke_main(fingerprint_script, monkeypatch, environment) != 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL environment fingerprint configuration invalid\n"
    for sentinel in SENTINELS:
        assert sentinel not in captured.err


def test_extra_cli_arguments_are_rejected_before_fingerprinting(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-9/SECURITY: this operation accepts no alternate configuration channel."""
    assert (
        invoke_main(
            fingerprint_script,
            monkeypatch,
            BASE_ENVIRONMENT,
            ["api_environment_fingerprint.py", "--database=leak"],
        )
        != 0
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL environment fingerprint arguments invalid\n"


def test_fingerprints_match_independent_length_prefixed_sha256_vectors(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6: every group uses the documented field order, framing, and SHA-256."""
    assert invoke_main(fingerprint_script, monkeypatch, BASE_ENVIRONMENT) == 0

    result = parse_fingerprints(capsys.readouterr().out, target="staging")

    assert result == KNOWN_FINGERPRINTS


@pytest.mark.parametrize(
    "field_name",
    tuple(name for names in FIELD_GROUPS.values() for name in names),
)
def test_each_approved_field_affects_only_its_own_labeled_fingerprint(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field_name: str,
) -> None:
    """AC-6/DATA INTEGRITY: no required isolation field is omitted or cross-labeled."""
    assert invoke_main(fingerprint_script, monkeypatch, BASE_ENVIRONMENT) == 0
    before = parse_fingerprints(capsys.readouterr().out, target="staging")
    changed_environment = {**BASE_ENVIRONMENT, field_name: f"changed-{field_name}"}
    assert invoke_main(fingerprint_script, monkeypatch, changed_environment) == 0
    after = parse_fingerprints(capsys.readouterr().out, target="staging")

    expected_group = next(
        label for label, fields in FIELD_GROUPS.items() if field_name in fields
    )
    assert after[expected_group] != before[expected_group]
    assert {
        label: value for label, value in after.items() if label != expected_group
    } == {label: value for label, value in before.items() if label != expected_group}


def test_length_prefixing_rejects_ambiguous_paired_value_concatenation(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/DATA INTEGRITY: joining paired values cannot create equal credentials."""
    first = {
        **BASE_ENVIRONMENT,
        "MEDIA_STORAGE_ACCESS_KEY_ID": "a",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY": "bc",
    }
    second = {
        **BASE_ENVIRONMENT,
        "MEDIA_STORAGE_ACCESS_KEY_ID": "ab",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY": "c",
    }

    assert invoke_main(fingerprint_script, monkeypatch, first) == 0
    first_result = parse_fingerprints(capsys.readouterr().out, target="staging")
    assert invoke_main(fingerprint_script, monkeypatch, second) == 0
    second_result = parse_fingerprints(capsys.readouterr().out, target="staging")

    assert first_result["media-credential"] != second_result["media-credential"]


def test_unapproved_environment_values_do_not_influence_any_fingerprint(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6/SECURITY: the fixed map excludes ambient configuration and secrets."""
    assert invoke_main(fingerprint_script, monkeypatch, BASE_ENVIRONMENT) == 0
    before = parse_fingerprints(capsys.readouterr().out, target="staging")
    assert (
        invoke_main(
            fingerprint_script,
            monkeypatch,
            {**BASE_ENVIRONMENT, "UNRELATED_SECRET": "must-not-be-read"},
        )
        == 0
    )
    after = parse_fingerprints(capsys.readouterr().out, target="staging")

    assert after == before


def test_sentinel_values_never_cross_output_or_logs(
    fingerprint_script: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-6/SECURITY: truncated fingerprints are the sole disclosure boundary."""
    caplog.set_level(logging.DEBUG)
    assert invoke_main(fingerprint_script, monkeypatch, BASE_ENVIRONMENT) == 0
    captured = capsys.readouterr()
    rendered = f"{captured.out}\n{captured.err}\n{caplog.text}"

    for sentinel in SENTINELS:
        assert sentinel not in rendered
