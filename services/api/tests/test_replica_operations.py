"""Replica job commands and their shared runner (#355 U2a, A1-A5).

Each test runs a real management command. Only the metadata server is faked, plus
one noise injector for the output rules. A target or request refusal must happen
before the handler touches the database, so those cases run with zero queries.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import override_settings
from pytest import CaptureFixture, MonkeyPatch

from config.settings.media import S3MediaConfiguration
from simulation_pool import services as pool_services
from simulation_pool.models import PoolSlot
from tests import replica_contract
from tests import replica_job_support as support
from tests.process_support import skip_on_windows
from tests.test_staging_registry_reconciliation import registry as persisted_registry
from tests.test_staging_registry_reconciliation import request as legacy_request

pytestmark = pytest.mark.django_db

UNSET: Final = object()
POOL_REGISTER: Final[dict[str, object]] = {
    "operation": "register",
    "pool": "gamma",
    "arguments": {"size": 2},
}
POOL_STATUS: Final[dict[str, object]] = {
    "operation": "status",
    "pool": "gamma",
    "arguments": {},
}
FIXTURE_RETAINED: Final[dict[str, object]] = {"operation": "retained", "arguments": {}}
MIGRATE_SETTINGS: Final = "config.settings.migrate"
PRODUCTION_SETTINGS: Final = "config.settings.production"
TLS_OPTIONS: Final = {
    "connect_timeout": 5,
    "sslmode": "verify-full",
    "sslrootcert": replica_contract.SSL_ROOT_CERT,
}

Invoke = Callable[..., dict[str, Any]]


@pytest.fixture
def invoke(
    monkeypatch: MonkeyPatch, tmp_path: Path, capfd: CaptureFixture[str]
) -> Invoke:
    """Run one command in a faked replica process and return its one output line.

    Every call also proves the universal output rules: exactly one canonical JSON
    line, nothing on stderr, and exit status 0 only for PASS.
    """

    def run(
        command: str,
        extra: Mapping[str, object] | None = None,
        *,
        job: str,
        process: support.Process = "job",
        identity: object = None,
        raw: object = UNSET,
        source_sha: str | None = support.SOURCE_SHA,
        settings_module: str = PRODUCTION_SETTINGS,
        database: Mapping[str, object] | None = None,
        media_bucket: str = replica_contract.MEDIA_BUCKET,
        uses_media: bool = False,
    ) -> dict[str, Any]:
        support.configure_process(
            monkeypatch, tmp_path, process=process, job=job, source_sha=source_sha
        )
        monkeypatch.setattr(django_settings, "SETTINGS_MODULE", settings_module)
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", settings_module)
        payload: dict[str, object] = dict(extra or {})
        if identity is not UNSET:
            payload["identity"] = (
                {"source_sha": support.SOURCE_SHA, "environment": "replica"}
                if identity is None
                else identity
            )
        if raw is None:
            monkeypatch.delenv("TAILTAG_JOB_REQUEST", raising=False)
        else:
            monkeypatch.setenv(
                "TAILTAG_JOB_REQUEST",
                json.dumps(payload) if raw is UNSET else str(raw),
            )
        overrides: dict[str, object] = {
            "DATABASES": {
                "default": {
                    **django_settings.DATABASES["default"],
                    "HOST": replica_contract.DATABASE_HOST,
                    "NAME": replica_contract.DATABASE_NAME,
                    "OPTIONS": dict(TLS_OPTIONS),
                    **(database or {}),
                }
            }
        }
        if uses_media:
            overrides["MEDIA_STORAGE_CONFIGURATION"] = S3MediaConfiguration(
                endpoint_url=replica_contract.MEDIA_ENDPOINT,
                bucket_name=media_bucket,
                region="auto",
                access_key_id="test-access-key",
                secret_access_key="test-secret-key",
            )
        with override_settings(**overrides), pytest.raises(SystemExit) as exit_info:
            call_command(command)
        captured = capfd.readouterr()
        assert captured.err == ""
        lines = captured.out.splitlines()
        assert len(lines) == 1
        output = json.loads(lines[0])
        assert lines[0] == json.dumps(output, sort_keys=True)
        assert set(output) == {"result", "data", "identity"}
        assert exit_info.value.code == (0 if output["result"] == "PASS" else 1)
        return output

    return run


def passing(job: str, data: Mapping[str, object]) -> dict[str, Any]:
    """Return what a passing command must print, for an exact comparison."""
    return {
        "result": "PASS",
        "data": dict(data),
        "identity": support.runtime_identity(job),
    }


def test_migrate_applies_nothing_pending_and_reports_pass_under_migrate_settings(
    invoke: Invoke,
) -> None:
    """A1/A2: the migrate job passes in its own job and prints the runtime identity."""
    output = invoke(
        "replica_migrate",
        job=support.MIGRATE_JOB,
        settings_module=MIGRATE_SETTINGS,
    )

    assert output == passing(support.MIGRATE_JOB, {"unapplied": 0})


@pytest.mark.parametrize(
    ("command", "job", "extra", "uses_media", "data"),
    (
        pytest.param(
            "replica_pool",
            support.POOL_JOB,
            POOL_STATUS,
            False,
            {"total": 0, "available": 0, "leased": 0, "quarantined": 0},
            id="pool",
        ),
        pytest.param(
            "replica_fixture",
            support.FIXTURE_JOB,
            FIXTURE_RETAINED,
            True,
            {"runs": [], "retained": 0, "unfinished": 0},
            id="fixture",
        ),
    ),
)
def test_remote_module_command_runs_end_to_end_in_its_own_job(
    invoke: Invoke,
    command: str,
    job: str,
    extra: Mapping[str, object],
    uses_media: bool,
    data: Mapping[str, object],
) -> None:
    """A2/A3: the runner rebuilds the full request and the remote module accepts it.

    Pool runs without any media configuration, so skipping the media pin when
    `uses_media` is false is proven here. Fixture runs with the media pin checked.
    """
    output = invoke(command, extra, job=job, uses_media=uses_media)

    assert output == passing(job, data)


@pytest.mark.django_db(transaction=True)
def test_inspect_command_reaches_the_remote_module_with_a_fully_valid_request(
    invoke: Invoke,
) -> None:
    """A2: a valid inspect request gets past the target guard and request validation.

    The pool has no slots, so the module's own lease guard answers.
    """
    output = invoke(
        "replica_inspect",
        {
            "operation": "inspect",
            "arguments": {
                "pool": "gamma",
                "run_id": "cccccccc-3333-4333-8333-333333333333",
                "identities": {
                    "owner0": 5,
                    "owner1": 3,
                    "catcher0": 8,
                    "catcher1": 4,
                    "catcher2": 9,
                    "catcher3": 6,
                    "outsider": 7,
                },
            },
        },
        job=support.INSPECT_JOB,
    )

    assert output["result"] in {"FAIL_LEASE", "FAIL_RUN_UNKNOWN"}
    assert output["data"] == {}


def test_registry_reconcile_maps_its_checks_into_the_runner_output(
    invoke: Invoke, monkeypatch: MonkeyPatch
) -> None:
    """A5: the replica branch runs the reconciler and prints `{"checks": ...}` as data.

    The real replica configuration loader runs. Only the two database reads
    that need #204 rows are faked.
    """
    reconciliation = importlib.import_module("rehearsal.registry_reconciliation")

    monkeypatch.setattr(reconciliation, "read_registry", persisted_registry)
    monkeypatch.setattr(
        reconciliation,
        "read_actual_database_facts",
        lambda: ("tailtag_staging", "742391", "postgres.internal", "5432"),
    )

    output = invoke(
        "replica_registry_reconcile",
        {"configuration": legacy_request()["configuration"]},
        job=support.REGISTRY_JOB,
    )

    assert output["result"] == "PASS"
    assert set(output["data"]) == {"checks"}
    assert output["data"]["checks"]["registry_singleton"] == "PASS"
    assert output["identity"] == support.runtime_identity(support.REGISTRY_JOB)


@pytest.mark.parametrize(
    ("process", "job"),
    (
        pytest.param("job", support.FIXTURE_JOB, id="another-pinned-job"),
        pytest.param("service", support.POOL_JOB, id="replica-api-service"),
        pytest.param("railway", support.POOL_JOB, id="railway-process"),
        pytest.param("local", support.POOL_JOB, id="no-cloud-run-markers"),
    ),
)
def test_command_is_refused_outside_its_own_pinned_job_before_any_database_access(
    invoke: Invoke,
    django_assert_num_queries: Any,
    process: support.Process,
    job: str,
) -> None:
    """Failure mode 1: only the pinned job runs a command, and nothing is touched."""
    with django_assert_num_queries(0):
        output = invoke("replica_pool", POOL_REGISTER, job=job, process=process)

    assert output["result"] == "FAIL_TARGET"
    assert output["data"] == {}
    assert PoolSlot.objects.count() == 0


@pytest.mark.parametrize(
    ("identity", "source_sha", "results"),
    (
        pytest.param(
            {"source_sha": "d" * 40, "environment": "replica"},
            support.SOURCE_SHA,
            {"FAIL_TARGET"},
            id="other-source-sha",
        ),
        pytest.param(
            {"source_sha": support.SOURCE_SHA, "environment": "staging"},
            support.SOURCE_SHA,
            {"FAIL_TARGET"},
            id="other-environment",
        ),
        pytest.param(UNSET, support.SOURCE_SHA, {"FAIL_REQUEST"}, id="no-identity"),
        pytest.param(None, None, {"FAIL_TARGET"}, id="image-without-baked-source-sha"),
    ),
)
def test_request_identity_that_does_not_match_the_runtime_is_refused_up_front(
    invoke: Invoke,
    django_assert_num_queries: Any,
    identity: object,
    source_sha: str | None,
    results: set[str],
) -> None:
    """Failure mode 2: a mismatched or missing identity never reaches the handler."""
    with django_assert_num_queries(0):
        output = invoke(
            "replica_pool",
            POOL_REGISTER,
            job=support.POOL_JOB,
            identity=identity,
            source_sha=source_sha,
        )

    assert output["result"] in results
    assert output["data"] == {}
    assert PoolSlot.objects.count() == 0


def _valid_pool_text(**changes: object) -> str:
    return json.dumps(
        {
            **POOL_REGISTER,
            "identity": {"source_sha": support.SOURCE_SHA, "environment": "replica"},
            **changes,
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    "raw",
    (
        pytest.param(None, id="variable-missing"),
        pytest.param(
            _valid_pool_text() + " " * 65_536,
            id="over-65536-bytes",
            marks=skip_on_windows("Windows caps one environment value at 32,767 chars"),
        ),
        pytest.param(
            _valid_pool_text(pool="gamma\udcff"),
            id="not-utf-8",
            marks=skip_on_windows("Windows cannot hold undecodable environment bytes"),
        ),
        pytest.param("[1, 2]", id="not-an-object"),
        pytest.param(
            '{"operation": "register", "pool": "gamma", "arguments": {"size": 2},'
            ' "identity": {"source_sha": "' + support.SOURCE_SHA + '",'
            ' "environment": "replica", "environment": "replica"}}',
            id="nested-duplicate-key",
        ),
    ),
)
def test_unusable_request_text_is_refused_without_running_the_handler(
    invoke: Invoke, django_assert_num_queries: Any, raw: str | None
) -> None:
    """Failure mode 3: each variant would run to PASS if it were admitted."""
    with django_assert_num_queries(0):
        output = invoke("replica_pool", job=support.POOL_JOB, raw=raw)

    assert output["result"] == "FAIL_REQUEST"
    assert output["data"] == {}
    assert PoolSlot.objects.count() == 0


@pytest.mark.parametrize(
    ("command", "extra", "uses_media", "tweak"),
    (
        pytest.param(
            "replica_pool",
            POOL_REGISTER,
            False,
            {"database": {"OPTIONS": {**TLS_OPTIONS, "sslmode": "require"}}},
            id="database-without-verify-full",
        ),
        pytest.param(
            "replica_pool",
            POOL_REGISTER,
            False,
            {"database": {"HOST": "db.other-project.example.test"}},
            id="unpinned-database",
        ),
        pytest.param(
            "replica_fixture",
            FIXTURE_RETAINED,
            True,
            {"media_bucket": "tailtag-other-media"},
            id="unpinned-media-for-fixture",
        ),
    ),
)
def test_data_target_checks_are_enforced_before_any_database_access(
    invoke: Invoke,
    django_assert_num_queries: Any,
    command: str,
    extra: Mapping[str, object],
    uses_media: bool,
    tweak: Mapping[str, object],
) -> None:
    """Failure mode 9: TLS, the database pin and the media pin are all enforced."""
    job = support.FIXTURE_JOB if uses_media else support.POOL_JOB
    with django_assert_num_queries(0):
        output = invoke(command, extra, job=job, uses_media=uses_media, **tweak)

    assert output["result"] == "FAIL_TARGET"
    assert output["data"] == {}
    assert PoolSlot.objects.count() == 0


@pytest.mark.parametrize(
    "fails",
    (
        pytest.param(False, id="handler-passes-after-printing"),
        pytest.param(True, id="handler-crashes-after-printing"),
    ),
)
def test_handler_noise_and_crash_details_never_reach_the_output(
    invoke: Invoke, monkeypatch: MonkeyPatch, fails: bool
) -> None:
    """Failure mode 4: libraries write to both streams; a crash reveals no detail."""
    real_status = pool_services.status

    def noisy_status(pool: str) -> Any:
        print("NOISE-ON-STDOUT")
        sys.stderr.write("NOISE-ON-STDERR\n")
        if fails:
            raise RuntimeError("SECRET-CRASH-DETAIL")
        return real_status(pool)

    monkeypatch.setattr(pool_services, "status", noisy_status)

    output = invoke("replica_pool", POOL_STATUS, job=support.POOL_JOB)

    text = json.dumps(output)
    for private in ("NOISE", "SECRET-CRASH-DETAIL", "Traceback"):
        assert private not in text
    assert output["result"] == ("FAIL_EXECUTION" if fails else "PASS")
    if fails:
        assert output["data"] == {}


def test_migrate_is_refused_under_production_settings_without_migrating(
    invoke: Invoke, django_assert_num_queries: Any
) -> None:
    """Failure mode 7: the migrate job must run with the migrate-only settings."""
    with django_assert_num_queries(0):
        output = invoke(
            "replica_migrate",
            job=support.MIGRATE_JOB,
            settings_module=PRODUCTION_SETTINGS,
        )

    assert output["result"] == "FAIL_TARGET"
    assert output["data"] == {}


@pytest.mark.parametrize(
    "migrate_fails",
    (
        pytest.param(False, id="migrate-leaves-one-unapplied"),
        pytest.param(True, id="migrate-raises"),
    ),
)
def test_migrate_never_reports_pass_unless_everything_is_applied(
    invoke: Invoke, monkeypatch: MonkeyPatch, migrate_fails: bool
) -> None:
    """Failure mode 7: a silent partial migrate or an error is FAIL_MIGRATION."""
    loader = MigrationLoader(connection)
    app_label, name = next(
        key
        for key in sorted(loader.graph.leaf_nodes())
        if not loader.graph.node_map[key].children
    )
    MigrationRecorder(connection).record_unapplied(app_label, name)

    def migrate(self: MigrateCommand, *args: object, **options: object) -> None:
        if migrate_fails:
            raise CommandError("SECRET-MIGRATION-DETAIL")

    monkeypatch.setattr(MigrateCommand, "handle", migrate)

    output = invoke(
        "replica_migrate", job=support.MIGRATE_JOB, settings_module=MIGRATE_SETTINGS
    )

    assert output["result"] == "FAIL_MIGRATION"
    assert "SECRET-MIGRATION-DETAIL" not in json.dumps(output)
    if not migrate_fails:
        assert output["data"] == {"unapplied": 1}
