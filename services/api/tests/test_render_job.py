"""The in-image Render Staging reset job prints exactly one result line (#410 AC6)."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Self, cast

import pytest

from tests.test_staging_reset_configuration import (
    MEDIA_KEY,
    RENDER_DEVELOPMENT_SERVICE,
    RENDER_STAGING_SERVICE,
    RESET_ID,
    render_environment,
    render_private,
)

SOURCE_SHA = "eb518d36baa21b7943acd9744f2499d80d527e61"
OTHER_SHA = "a" * 40
PREFIX = "TAILTAG-RENDER-JOB "
SENSITIVE = "untrusted-render-job-diagnostic"
COUNTS = {
    "profiles": 2,
    "conventions": 1,
    "fursuits": 2,
    "enrollments": 2,
    "activations": 2,
    "catches": 0,
    "sessions": 0,
    "credentials": 0,
}


class Maintenance:
    """Observe the #204 maintenance boundary. Real gating has its own tests."""

    def __init__(self, events: list[str], failures: set[str]) -> None:
        self.events = events
        self.failures = failures

    def __enter__(self) -> Self:
        self.events.append("enter")
        return self

    def quiesce(self) -> None:
        self.events.append("quiesce")
        if "quiesce" in self.failures or (
            "regate" in self.failures and self.events.count("quiesce") == 2
        ):
            raise RuntimeError(SENSITIVE)

    def resume(self) -> None:
        self.events.append("resume")
        if "resume" in self.failures:
            raise RuntimeError(SENSITIVE)

    def __exit__(self, *_: object) -> None:
        self.events.append("exit")


class Harness:
    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self.events: list[str] = []
        self.failures: set[str] = set()

    def maintenance(self, configuration: object) -> Maintenance:
        assert configuration.platform == "render"  # type: ignore[attr-defined]
        return Maintenance(self.events, self.failures)

    def reset(self, _configuration: object) -> dict[str, int]:
        self.events.append("reset")
        # Noisy domain code must not add a second log line or leak a value.
        print(SENSITIVE)
        os.write(2, SENSITIVE.encode())
        if "reset" in self.failures:
            raise RuntimeError(SENSITIVE)
        if "reset-interrupted" in self.failures:
            # Render cancels a job with SIGTERM, which the job turns into this.
            raise KeyboardInterrupt
        return dict(COUNTS)

    def provision(self, _configuration: object) -> None:
        self.events.append("provision")
        if "provision" in self.failures:
            raise RuntimeError(SENSITIVE)

    def validate(self, _configuration: object) -> None:
        self.events.append("validate")

    def run(
        self, capfd: pytest.CaptureFixture[str], *arguments: str
    ) -> tuple[int, dict[str, object] | None, str]:
        status = self.module.main(list(arguments))
        output = capfd.readouterr()
        assert SENSITIVE not in output.out + output.err
        assert output.err == ""
        lines = output.out.splitlines()
        assert len(lines) == 1
        assert lines[0].startswith(PREFIX)
        return status, json.loads(lines[0].removeprefix(PREFIX)), output.out


def reset_arguments(source_sha: str = SOURCE_SHA) -> tuple[str, ...]:
    return (
        "--operation",
        "reset",
        "--source-sha",
        source_sha,
        "--confirm",
        "reset-tailtag-staging",
    )


def provision_arguments() -> tuple[str, ...]:
    return (
        "--operation",
        "provision",
        "--source-sha",
        SOURCE_SHA,
        "--confirm",
        "provision-tailtag-staging-reset",
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Harness:
    """A pinned Render Staging runtime whose image was built from SOURCE_SHA."""
    return pin_render_staging(monkeypatch, tmp_path)


def pin_render_staging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Harness:
    """Pin fictitious Render services, the AC5 digest, and the job's build file."""
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
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_RESET_DIGEST",
        binding.fingerprint_render_reset_configuration(render_private()),
    )
    for name in list(os.environ):
        if name.startswith("RAILWAY_"):
            monkeypatch.delenv(name)
    for name, value in render_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    module = importlib.import_module("rehearsal.render_job")
    identity = tmp_path / "build-identity.json"
    identity.write_text(json.dumps({"source_sha": SOURCE_SHA}) + "\n")
    monkeypatch.setattr(module, "_BUILD_IDENTITY_PATH", identity)
    value = Harness(module)
    monkeypatch.setattr(module, "DatabaseMaintenance", value.maintenance)
    monkeypatch.setattr(module, "reset_baseline", value.reset)
    monkeypatch.setattr(module, "provision_identity", value.provision)
    monkeypatch.setattr(module, "validate_identity", value.validate)
    return value


def test_reset_job_gates_resets_and_reopens_then_prints_one_pass_line(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    """The job binds its own build and runtime, then reports the baseline counts."""
    status, result, _ = harness.run(capfd, *reset_arguments())

    assert status == 0
    assert result == {
        "operation": "reset",
        "outcome": "PASS",
        "source_sha": SOURCE_SHA,
        "baseline_version": 1,
        "counts": COUNTS,
    }
    assert harness.events == ["enter", "quiesce", "reset", "resume", "exit"]


def test_provision_job_registers_and_validates_the_sentinel_without_a_gate(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    """A provision never enters reset maintenance and checks its postcondition."""
    status, result, _ = harness.run(capfd, *provision_arguments())

    assert status == 0
    assert result == {
        "operation": "provision",
        "outcome": "PASS",
        "source_sha": SOURCE_SHA,
        "provision_postcondition": "PASS",
    }
    assert harness.events == ["provision", "validate"]


@pytest.mark.parametrize(
    ("case", "phase"),
    [
        ("wrong-confirmation", "confirmation"),
        ("swapped-confirmation", "confirmation"),
        ("unknown-argument", "confirmation"),
        ("missing-confirmation", "confirmation"),
        ("other-build", "target"),
        ("railway-marker", "target"),
        ("development-service", "target"),
        ("local-settings", "target"),
        ("unpinned-values", "configuration"),
    ],
)
def test_job_refuses_before_any_database_work(
    harness: Harness,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    phase: str,
) -> None:
    """Every target, build, or configuration mismatch fails closed with no gate."""
    arguments = list(reset_arguments())
    if case == "wrong-confirmation":
        arguments[-1] = "reset-tailtag-production"
    elif case == "swapped-confirmation":
        arguments[-1] = "provision-tailtag-staging-reset"
    elif case == "unknown-argument":
        arguments.append("--force")
    elif case == "missing-confirmation":
        arguments = arguments[:-2]
    elif case == "other-build":
        arguments = list(reset_arguments(OTHER_SHA))
    elif case == "railway-marker":
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    elif case == "development-service":
        monkeypatch.setenv("RENDER_SERVICE_ID", RENDER_DEVELOPMENT_SERVICE)
    elif case == "local-settings":
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.local")
    else:
        monkeypatch.setenv("TAILTAG_STAGING_RESET_MEDIA_KEY", "images/other.png")

    status, result, _ = harness.run(capfd, *arguments)

    assert status == 1
    # The operation is not trusted until its exact confirmation matches.
    expected = {"outcome": "FAIL", "phase": phase}
    assert result == (
        expected if phase == "confirmation" else {"operation": "reset", **expected}
    )
    assert harness.events == []


@pytest.mark.parametrize(
    ("failure", "phase", "events"),
    [
        ("quiesce", "maintenance unknown", ["enter", "quiesce", "exit"]),
        ("reset", "maintenance retained", ["enter", "quiesce", "reset", "exit"]),
        (
            "reset-interrupted",
            "maintenance retained",
            ["enter", "quiesce", "reset", "exit"],
        ),
        (
            "resume",
            "committed maintenance retained",
            ["enter", "quiesce", "reset", "resume", "quiesce", "exit"],
        ),
        (
            "regate",
            "maintenance unknown",
            ["enter", "quiesce", "reset", "resume", "quiesce", "exit"],
        ),
    ],
)
def test_reset_failure_reports_only_its_fixed_maintenance_phase(
    harness: Harness,
    capfd: pytest.CaptureFixture[str],
    failure: str,
    phase: str,
    events: list[str],
) -> None:
    """A failed step never reports success, and a failed resume re-gates."""
    harness.failures.add(failure if failure != "regate" else "resume")
    if failure == "regate":
        harness.failures.add("regate")

    status, result, _ = harness.run(capfd, *reset_arguments())

    assert status == 1
    assert result == {"operation": "reset", "outcome": "FAIL", "phase": phase}
    assert harness.events == events


def test_provision_failure_reports_its_phase_and_skips_the_postcondition(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    harness.failures.add("provision")

    status, result, _ = harness.run(capfd, *provision_arguments())

    assert status == 1
    assert result == {"operation": "provision", "outcome": "FAIL", "phase": "provision"}
    assert harness.events == ["provision"]


def test_entry_point_restores_the_process_streams(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    """Output suppression ends with the job, so the caller's streams still work."""
    harness.run(capfd, *reset_arguments())

    print("after")
    os.write(2, b"after\n")
    output = capfd.readouterr()
    assert output.out == "after\n"
    assert output.err == "after\n"


# AC7: read-only registry reconcile and operator inspect jobs.

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def read_only_arguments(operation: str) -> tuple[str, ...]:
    return ("--operation", operation, "--source-sha", SOURCE_SHA)


def registry(**overrides: object) -> SimpleNamespace:
    """A registry row that matches the pinned private Render values."""
    values: dict[str, object] = {
        "pk": 1,
        "environment_id": RESET_ID,
        "cluster_identifier": "742391",
        "database_name": "tailtag_staging",
        "owner": SimpleNamespace(clerk_user_id="user_rehearsal_owner"),
        "catcher": SimpleNamespace(clerk_user_id="user_rehearsal_catcher"),
        "media_key": MEDIA_KEY,
        "convention_id": None,
        "first_fursuit_id": None,
        "second_fursuit_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "copy",
    [
        ("rehearsal/registry_reconcile.py", "api_staging_registry_reconcile_remote.py"),
        ("rehearsal/operator_inspect.py", "api_staging_operator_inspect.py"),
    ],
)
def test_in_image_check_copies_equal_the_reviewed_railway_sources(
    copy: tuple[str, str],
) -> None:
    """The Railway tests protect both copies until #412 deletes the Railway side."""
    image, railway = copy
    assert (REPOSITORY_ROOT / "services/api" / image).read_bytes() == (
        REPOSITORY_ROOT / "scripts" / railway
    ).read_bytes()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("port", "outcome"), [("", "PASS"), ("6543", "FAIL")])
def test_reconcile_job_compares_the_runtime_with_the_pinned_private_values(
    harness: Harness,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    port: str,
    outcome: str,
) -> None:
    """A Render URL with no port means 5432, as in the reset gate (#408)."""
    reconcile = importlib.import_module("rehearsal.registry_reconcile")
    monkeypatch.setattr(reconcile, "read_registry", registry)
    monkeypatch.setattr(
        reconcile,
        "read_actual_database_facts",
        lambda: ("tailtag_staging", "742391", "dpg-stagingtest-a", port),
    )

    status, result, _ = harness.run(capfd, *read_only_arguments("reconcile"))

    assert result is not None
    checks = cast(dict[str, str], result.pop("checks"))
    assert (status, result) == (
        0 if outcome == "PASS" else 1,
        {
            "operation": "reconcile",
            "outcome": outcome,
            "source_sha": SOURCE_SHA,
            "result": "PASS" if outcome == "PASS" else "MISMATCH",
        },
    )
    assert checks["database_port_runtime_private"] == (
        "MATCH" if outcome == "PASS" else "MISMATCH"
    )


@pytest.mark.django_db(transaction=True)
def test_read_only_jobs_cannot_write_to_the_database(
    harness: Harness,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checks run in a read-only transaction, so a write fails the query."""
    from django.contrib.auth.models import Group

    reconcile = importlib.import_module("rehearsal.registry_reconcile")

    def writing_registry() -> None:
        Group.objects.create(name="tailtag-read-only-probe")

    monkeypatch.setattr(reconcile, "read_registry", writing_registry)

    status, result, _ = harness.run(capfd, *read_only_arguments("reconcile"))

    assert (status, result) == (
        1,
        {
            "operation": "reconcile",
            "outcome": "FAIL",
            "source_sha": SOURCE_SHA,
            "result": "FAIL_QUERY",
            "checks": {},
        },
    )
    assert not Group.objects.filter(name="tailtag-read-only-probe").exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("case", ["empty-database", "passing-checks"])
def test_inspect_job_reports_the_operator_inspector_status(
    harness: Harness,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """The job runs the reviewed #243 ORM checks after its own target binding."""
    if case == "passing-checks":
        inspector = importlib.import_module("rehearsal.operator_inspect")
        monkeypatch.setattr(inspector, "_inspect_orm_preconditions", lambda: "PASS")

    status, result, _ = harness.run(capfd, *read_only_arguments("inspect"))

    expected = "PASS" if case == "passing-checks" else "FAIL_FIXTURE_MISSING"
    assert (status, result) == (
        0 if expected == "PASS" else 1,
        {
            "operation": "inspect",
            "outcome": "PASS" if expected == "PASS" else "FAIL",
            "source_sha": SOURCE_SHA,
            "result": expected,
        },
    )


def orm_counts() -> dict[str, int]:
    """Count every table through the ORM, and prove that no table is missing."""
    from django.apps import apps
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    models = [*apps.get_models(include_auto_created=True), MigrationRecorder.Migration]
    counts = {
        model._meta.db_table: model._base_manager.count()  # pyright: ignore[reportPrivateUsage]
        for model in models
    }
    assert set(counts) == set(connection.introspection.table_names())
    return dict(sorted(counts.items()))


@pytest.mark.django_db(transaction=True)
def test_row_counts_job_counts_every_public_table_and_records_its_time(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC13: the exact count of every public table, its digest, and time T."""
    import hashlib
    import re

    from django.contrib.auth.models import Group

    Group.objects.create(name="tailtag-row-count-probe")
    expected = orm_counts()

    status, result, _ = harness.run(capfd, *read_only_arguments("row-counts"))

    assert result is not None
    captured_at = cast(str, result.pop("captured_at"))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", captured_at)
    canonical = json.dumps(expected, sort_keys=True, separators=(",", ":"))
    assert (status, result) == (
        0,
        {
            "operation": "row-counts",
            "outcome": "PASS",
            "source_sha": SOURCE_SHA,
            "result": "PASS",
            "tables": len(expected),
            "counts": expected,
            "counts_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        },
    )
    assert expected["django_migrations"] > 0
    assert expected["auth_group"] == 1


def test_read_only_jobs_take_no_confirmation(
    harness: Harness, capfd: pytest.CaptureFixture[str]
) -> None:
    """A confirmation belongs only to a mutation, so a read-only job refuses one."""
    arguments = (
        *read_only_arguments("reconcile"),
        "--confirm",
        "reset-tailtag-staging",
    )

    status, result, _ = harness.run(capfd, *arguments)

    assert (status, result) == (1, {"outcome": "FAIL", "phase": "confirmation"})
