"""The in-image PITR restore counter for Render Staging (#410 AC13)."""

from __future__ import annotations

import getpass
import hashlib
import importlib
import json
import re
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import pytest

from tests.test_render_job import (
    OTHER_SHA,
    SOURCE_SHA,
    orm_counts,
    pin_render_staging,
)

PREFIX = "TAILTAG-RENDER-RESTORE "
PASSWORD = "recovery-password-never-printed"


class Terminal(StringIO):
    def isatty(self) -> bool:
        return True


class Pipe(StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture
def counter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """Pinned Render Staging and an image built from SOURCE_SHA."""
    pin_render_staging(monkeypatch, tmp_path)
    for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"):
        monkeypatch.delenv(name, raising=False)
    return importlib.import_module("rehearsal.render_restore_count")


def accept_local_alias(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the local alias of the test database stand in for a Render host."""
    pattern = module._INTERNAL_HOST.pattern  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(
        module, "_INTERNAL_HOST", re.compile(f"{pattern}|127\\.0\\.0\\.1|localhost")
    )


def recovery_url(*, host: str | None = None, password: str = PASSWORD) -> str:
    """The test database under another host name, as a new database would be."""
    from django.db import connection

    database = connection.settings_dict
    # The live Staging host must differ, so reach the same server by its alias.
    alias = "127.0.0.1" if database["HOST"] in {"localhost", ""} else "localhost"
    return (
        f"postgresql://{database['USER']}:{password}@{host or alias}:"
        f"{database['PORT'] or 5432}/{database['NAME']}"
    )


def digest(counts: dict[str, int]) -> str:
    canonical = json.dumps(counts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def run(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expected: str,
    source_sha: str = SOURCE_SHA,
    *,
    stdin: StringIO | None = None,
) -> tuple[int, str, str]:
    """Run in a fake terminal, and return the status, all output, and the result."""
    from django.db import connection

    # The real URL holds the test database password, which the test never prints.
    password = connection.settings_dict["PASSWORD"]
    secret = url.replace(PASSWORD, password)
    terminal = Terminal()
    monkeypatch.setattr(sys, "stdin", stdin or terminal)
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.setattr(sys, "stderr", Terminal())
    prompts: list[str] = []

    def read_hidden(prompt: str = "", **_: object) -> str:
        prompts.append(prompt)
        return secret

    monkeypatch.setattr(getpass, "getpass", read_hidden)
    status = module.main(["--source-sha", source_sha, "--expected-counts", expected])
    output = terminal.getvalue()
    assert prompts in ([], ["Recovery database URL: "])
    assert PASSWORD not in output
    assert password not in output
    assert secret not in output
    return status, output, output.splitlines()[-1]


@pytest.mark.django_db(transaction=True)
def test_matching_counts_pass_and_print_every_count(
    counter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC13: the new database passes only when its count digest matches."""
    accept_local_alias(counter, monkeypatch)
    counts = orm_counts()

    status, output, result = run(counter, monkeypatch, recovery_url(), digest(counts))

    assert (status, result) == (0, PREFIX + "PASS restore-count")
    [details] = [line for line in output.splitlines() if line.startswith("{")]
    assert json.loads(details) == {
        "tables": len(counts),
        "counts": counts,
        "counts_sha256": digest(counts),
        # The test database is not the pinned Staging cluster.
        "same_system_identifier": False,
    }


@pytest.mark.django_db(transaction=True)
def test_a_count_that_differs_fails_and_still_prints_the_counts(
    counter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different digest fails, and the printed counts show which table differs."""
    accept_local_alias(counter, monkeypatch)
    counts = orm_counts()

    status, output, result = run(counter, monkeypatch, recovery_url(), "0" * 64)

    assert (status, result) == (1, PREFIX + "FAIL restore-count counts")
    assert json.dumps(counts, sort_keys=True) in output


@pytest.mark.django_db(transaction=True)
def test_a_database_error_prints_only_its_fixed_phase(
    counter: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed connection names no URL part, and psycopg's message never shows."""
    accept_local_alias(counter, monkeypatch)
    missing = "tailtag_missing_recovery_database"
    url = recovery_url().rsplit("/", 1)[0] + "/" + missing

    status, output, result = run(counter, monkeypatch, url, "c" * 64)

    assert (status, result) == (1, PREFIX + "FAIL restore-count query")
    assert output.strip() == result
    assert missing not in output


@pytest.mark.parametrize(
    ("case", "phase"),
    [
        ("staging-host", "target"),
        ("staging-external-host", "url"),
        ("host-address", "url"),
        ("ip-address", "url"),
        ("other-name", "url"),
        ("libpq-redirect", "url"),
        ("no-host", "url"),
        ("not-a-url", "url"),
        ("not-a-terminal", "terminal"),
        ("other-build", "target"),
    ],
)
def test_the_counter_refuses_before_it_connects(
    counter: ModuleType, monkeypatch: pytest.MonkeyPatch, case: str, phase: str
) -> None:
    """The live Staging database can never be counted as its own restore."""
    import psycopg

    def forbidden(*_: object, **__: object) -> NoReturn:
        raise AssertionError("a refused count must not connect")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    url = "postgresql://tailtag@dpg-recoverytest-a/tailtag_staging"
    expected, source_sha, stdin = "c" * 64, SOURCE_SHA, None
    if case == "staging-host":
        url = "postgresql://tailtag@dpg-stagingtest-a/tailtag_staging"
    elif case == "staging-external-host":
        url = (
            "postgresql://tailtag@dpg-stagingtest-a.oregon-postgres.render.com"
            "/tailtag_staging"
        )
    elif case == "host-address":
        url += "?hostaddr=10.0.0.5"
    elif case == "ip-address":
        url = "postgresql://tailtag@10.0.0.5/tailtag_staging"
    elif case == "other-name":
        url = "postgresql://tailtag@staging-db.example.test/tailtag_staging"
    elif case == "libpq-redirect":
        monkeypatch.setenv("PGHOSTADDR", "10.0.0.5")
    elif case == "no-host":
        url = "postgresql:///tailtag_staging"
    elif case == "not-a-url":
        url = "not a database url"
    elif case == "not-a-terminal":
        stdin = Pipe()
    else:
        source_sha = OTHER_SHA

    status, _, result = run(
        counter, monkeypatch, url, expected, source_sha, stdin=stdin
    )

    assert (status, result) == (1, PREFIX + f"FAIL restore-count {phase}")
