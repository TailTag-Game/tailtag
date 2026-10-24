"""Offline acceptance contract for the local replica job runners (#355 U3b).

The Cloud Run, Cloud Logging and gcloud boundaries are faked at
`urllib.request.OpenerDirector.open` and `subprocess.run`. Nothing here
reaches a network, a cloud project or a real gcloud.
"""

from __future__ import annotations

import http.client
import importlib
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Self, cast

import pytest

from tests import windows_acl_support as acl
from tests.semgrep_support import task_dry_run

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
JOB_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_replica_job.py"
RESET_SCRIPT = REPOSITORY_ROOT / "scripts" / "api_replica_reset.py"

PROJECT = "synthetic-replica-project"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
IDENTITY = {"source_sha": SOURCE_SHA, "environment": "replica"}
TOKEN = "synthetic-bearer-token-value"
TOKEN_REFRESHED = "synthetic-refreshed-token-value"
RESPONSE_CAP = 4 * 1024 * 1024
REQUEST_CAP = 65_536
BODY_SECRET = "synthetic-response-body-secret"
EXECUTION = "tailtag-replica-job-x7k2p"
FOREIGN_EXECUTION = "tailtag-replica-job-other"
ALLOWED_HOSTS = {"run.googleapis.com", "logging.googleapis.com"}
JOBS = {
    "migrate": "tailtag-replica-migrate",
    "pool": "tailtag-replica-pool",
    "fixture": "tailtag-replica-fixture",
    "inspect": "tailtag-replica-inspect",
    "reset": "tailtag-replica-reset",
    "registry-reconcile": "tailtag-replica-registry-reconcile",
}
GENERIC_FAMILIES = ("migrate", "pool", "fixture", "inspect")
FAIL_LAUNCHER_LINE = '{"result": "FAIL_LAUNCHER"}\n'
RESET_CONFIRM = "reset-tailtag-replica"
PROVISION_CONFIRM = "provision-tailtag-replica-reset"
CONFIGURATION_NAMES = (
    "TAILTAG_STAGING_RESET_ENABLED",
    "TAILTAG_STAGING_RESET_ID",
    "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
    "TAILTAG_STAGING_DATABASE_HOST",
    "TAILTAG_STAGING_DATABASE_PORT",
    "TAILTAG_STAGING_DATABASE_NAME",
    "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
    "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
    "TAILTAG_STAGING_RESET_MEDIA_KEY",
)
CONFIGURATION = {
    "TAILTAG_STAGING_RESET_ENABLED": "true",
    "TAILTAG_STAGING_RESET_ID": "2b859e84-1d92-4a8a-a72b-d3567219288d",
    "TAILTAG_STAGING_DATABASE_SYSTEM_ID": "742391",
    "TAILTAG_STAGING_DATABASE_HOST": "postgres.synthetic-private.internal",
    "TAILTAG_STAGING_DATABASE_PORT": "5432",
    "TAILTAG_STAGING_DATABASE_NAME": "tailtag",
    "TAILTAG_STAGING_RESET_OWNER_CLERK_ID": "user_synthetic_owner",
    "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_synthetic_catcher",
    "TAILTAG_STAGING_RESET_MEDIA_KEY": "images/0123456789abcdef0123456789abcdef.png",
}

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def load(script: Path, name: str) -> Any:
    """Import a runner once the implementation exists."""
    assert script.is_file(), f"{script.relative_to(REPOSITORY_ROOT)} must exist"
    return cast(Any, importlib.import_module(f"scripts.{name}"))


@pytest.fixture
def job_module() -> Any:
    return load(JOB_SCRIPT, "api_replica_job")


@pytest.fixture
def reset_module() -> Any:
    return load(RESET_SCRIPT, "api_replica_reset")


class FakeResponse:
    """Minimal urllib response: status, bounded reads, context manager."""

    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self._stream = io.BytesIO(payload)
        self.handed_out = 0

    def read(self, amt: int | None = None) -> bytes:
        chunk = self._stream.read(-1 if amt is None else amt)
        self.handed_out += len(chunk)
        return chunk

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return ""

    def close(self) -> None:
        return None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def result_payload(result: Any = "PASS", **overrides: Any) -> dict[str, Any]:
    return {
        "result": result,
        "data": {"checks": 1},
        "identity": dict(IDENTITY),
        **overrides,
    }


def result_entry(
    payload: Any, execution: str = EXECUTION, job: str | None = None
) -> dict[str, Any]:
    return {
        "jsonPayload": payload,
        "logName": f"projects/{PROJECT}/logs/run.googleapis.com%2Fstdout",
        "labels": {"run.googleapis.com/execution_name": execution},
        "resource": {"labels": {"job_name": job or "tailtag-replica-job"}},
    }


class FakeCloud:
    """Fake Cloud Run Admin v2, Cloud Logging v2 and `gcloud` behind urllib."""

    def __init__(self, job: str = "tailtag-replica-pool") -> None:
        self.job = job
        self.requests: list[dict[str, Any]] = []
        self.unexpected: list[str] = []
        self.subprocess_calls: list[Sequence[str]] = []
        self.token_ok = True
        self.run_metadata_name: str | None = None
        self.running_polls = 0
        self.never_completes = False
        self.execution_state: dict[str, Any] = {"succeededCount": 1}
        self.entries: list[dict[str, Any]] = [result_entry(result_payload())]
        self.honor_filter = True
        self.empty_log_calls = 0
        self.fail_on: str | None = None
        self.fail_body = BODY_SECRET
        self.big_logs = False
        self.big_response: FakeResponse | None = None
        self.fail_code = 500
        self.valid_token = TOKEN
        self.issued_token = TOKEN
        self.rotate_at_poll: int | None = None
        self.log_pages: dict[str, Any] | None = None
        self.raise_once: tuple[str, BaseException] | None = None
        self.logging_after_completion: list[bool] = []
        self._polls = 0
        self._completed = False
        self.clock = 0.0

    def for_family(self, family: str) -> None:
        self.job = JOBS[family]
        self.entries = [result_entry(result_payload(), job=self.job)]

    def execution_resource(self, job: str | None = None) -> str:
        return (
            f"projects/{PROJECT}/locations/us-east4/jobs/{job or self.job}"
            f"/executions/{EXECUTION}"
        )

    # urllib boundary -------------------------------------------------
    def open(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        url = request if isinstance(request, str) else request.full_url
        method = "GET" if isinstance(request, str) else request.get_method()
        data = None if isinstance(request, str) else request.data
        headers = {} if isinstance(request, str) else dict(request.header_items())
        record = {
            "url": url,
            "method": method,
            "body": json.loads(data) if data else None,
            "headers": {key.lower(): value for key, value in headers.items()},
            "timeout": kwargs.get("timeout", args[1] if len(args) > 1 else None),
        }
        self.requests.append(record)
        if (
            self.rotate_at_poll
            and f"/executions/{EXECUTION}" in url
            and self._polls + 1 == self.rotate_at_poll
            and self.valid_token == TOKEN
        ):
            self.valid_token = self.issued_token = TOKEN_REFRESHED
        if cast(dict[str, str], record["headers"]).get("authorization") != (
            f"Bearer {self.valid_token}"
        ):
            raise urllib.error.HTTPError(
                url, 401, "denied", cast(Any, {}), io.BytesIO(BODY_SECRET.encode())
            )
        run = (
            f"https://run.googleapis.com/v2/projects/{PROJECT}"
            f"/locations/us-east4/jobs/{self.job}:run"
        )
        execution = (
            f"https://run.googleapis.com/v2/projects/{PROJECT}"
            f"/locations/us-east4/jobs/{self.job}/executions/{EXECUTION}"
        )
        if self.raise_once and url.endswith(self.raise_once[0]):
            error = self.raise_once[1]
            self.raise_once = None
            raise error
        if self.fail_on and url.endswith(self.fail_on) or self.fail_on == "any":
            raise urllib.error.HTTPError(
                url,
                self.fail_code,
                "boom",
                cast(Any, {}),
                io.BytesIO(self.fail_body.encode()),
            )
        if url == run and method == "POST":
            return self._json(
                {
                    "name": f"projects/{PROJECT}/locations/us-east4/operations/op1",
                    "metadata": {
                        "name": self.run_metadata_name or self.execution_resource()
                    },
                    "done": False,
                }
            )
        if url == execution and method == "GET":
            self._polls += 1
            self.clock += 0.0
            if self.never_completes or self._polls <= self.running_polls:
                return self._json(
                    {"name": self.execution_resource(), "runningCount": 1}
                )
            self._completed = True
            return self._json(
                {
                    "name": self.execution_resource(),
                    "completionTime": "2026-10-23T12:00:00Z",
                    **self.execution_state,
                }
            )
        if url == "https://logging.googleapis.com/v2/entries:list" and method == "POST":
            self.logging_after_completion.append(self._completed)
            if self.big_logs:
                # Valid JSON with a passing entry: a reader without a cap would succeed.
                oversized = json.dumps(
                    {
                        "entries": self.entries,
                        "pad": "x" * (4 * RESPONSE_CAP),
                    }
                ).encode()
                self.big_response = FakeResponse(oversized)
                return self.big_response
            if self.log_pages is not None:
                page = cast(dict[str, Any], record["body"]).get("pageToken", "")
                return self._json(self.log_pages[page])
            if self.empty_log_calls > 0:
                self.empty_log_calls -= 1
                return self._json({})
            selected = self.entries
            if self.honor_filter:
                selected = [
                    entry
                    for entry in self.entries
                    if entry["labels"]["run.googleapis.com/execution_name"]
                    in cast(dict[str, Any], record["body"])["filter"]
                ]
            return self._json({"entries": selected})
        self.unexpected.append(url)
        raise urllib.error.HTTPError(
            url, 404, "unexpected", cast(Any, {}), io.BytesIO(BODY_SECRET.encode())
        )

    @staticmethod
    def _json(value: Any) -> FakeResponse:
        return FakeResponse(json.dumps(value).encode())

    # subprocess boundary ---------------------------------------------
    def run(self, args: Any, *pargs: Any, **kwargs: Any) -> Any:
        parts = cast(Sequence[Any], args if isinstance(args, (list, tuple)) else [args])
        argv = [str(part) for part in parts]
        self.subprocess_calls.append(argv)
        if "print-access-token" in argv and "gcloud" in Path(argv[0]).name.lower():
            done = subprocess.CompletedProcess(
                argv,
                0 if self.token_ok else 1,
                f"{self.issued_token}\n" if self.token_ok else "",
                "",
            )
            if kwargs.get("check") and done.returncode:
                raise subprocess.CalledProcessError(done.returncode, argv)
            return done
        raise AssertionError(f"unexpected subprocess: {argv[0]}")


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> FakeCloud:
    fake = FakeCloud()

    def opener_open(_opener: object, request: Any, *args: Any, **kwargs: Any) -> Any:
        return fake.open(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opener_open)
    monkeypatch.setattr(subprocess, "run", fake.run)

    def which(name: str, *_a: object, **_k: object) -> str:
        return name

    monkeypatch.setattr(shutil, "which", which)

    def sleep(seconds: float) -> None:
        fake.clock += max(seconds, 0.001)
        assert fake.clock < 24 * 3600, "runner never gives up"

    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(time, "monotonic", lambda: fake.clock)
    return fake


def run_main(
    module: Any, argv: Sequence[str], stdin: bytes | None = b""
) -> tuple[int, str, str]:
    """Run main() and return the exit code with captured streams."""
    out, err = io.StringIO(), io.StringIO()
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        try:
            code = module.main(list(argv), stdin=io.BytesIO(stdin or b""))
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 1
    finally:
        sys.stdout, sys.stderr = real_out, real_err
    return int(code or 0), out.getvalue(), err.getvalue()


def job_argv(
    family: str, source_sha: str = SOURCE_SHA, project: str = PROJECT
) -> list[str]:
    return ["--project", project, "--family", family, "--source-sha", source_sha]


def assert_no_cloud_contact(cloud: FakeCloud) -> None:
    assert cloud.requests == []
    assert cloud.subprocess_calls == []


def assert_fixed_failure(code: int, out: str, err: str, *private: str) -> None:
    assert code != 0
    assert out == FAIL_LAUNCHER_LINE
    assert err == ""
    for value in (TOKEN, PROJECT, BODY_SECRET, "googleapis", "https://", *private):
        assert value not in out + err


def posts(cloud: FakeCloud) -> list[dict[str, Any]]:
    return [r for r in cloud.requests if r["url"].endswith(":run")]


# --- L1: request building and identity injection ------------------------


def padded_stdin(final_size: int) -> bytes:
    """Stdin whose request value, with the identity added, is `final_size` bytes."""
    overhead = len(
        json.dumps({"pad": "", "identity": IDENTITY}, separators=(",", ":")).encode()
    )
    return json.dumps({"pad": "a" * (final_size - overhead)}).encode()


@pytest.mark.parametrize(
    ("family", "stdin"),
    (
        ("migrate", b""),
        ("migrate", b"{}"),
        ("pool", b'{"operation": "up", "count": 2}'),
        ("fixture", b'{"nested": {"keep": [1, 2]}}'),
        ("inspect", b'{"limit": 3}'),
        ("pool", padded_stdin(REQUEST_CAP)),
    ),
    ids=("migrate-empty", "migrate-braces", "pool", "fixture", "inspect", "max-size"),
)
def test_request_is_built_from_stdin_with_pinned_identity_and_bearer(
    job_module: Any,
    cloud: FakeCloud,
    capsys: pytest.CaptureFixture[str],
    family: str,
    stdin: bytes,
) -> None:
    """L1: the pinned job runs once with exactly one override env carrying body plus identity."""
    cloud.for_family(family)
    assert len(stdin) <= REQUEST_CAP

    code, out, err = run_main(job_module, job_argv(family), stdin)

    assert code == 0, (out, err)
    (run,) = posts(cloud)
    assert run["url"] == (
        f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/us-east4"
        f"/jobs/{JOBS[family]}:run"
    )
    overrides = run["body"]["overrides"]["containerOverrides"]
    assert len(overrides) == 1 and len(overrides[0]["env"]) == 1
    env = overrides[0]["env"][0]
    assert env["name"] == "TAILTAG_JOB_REQUEST"
    expected_body: dict[str, Any] = json.loads(stdin) if stdin.strip() else {}
    assert json.loads(env["value"]) == {**expected_body, "identity": IDENTITY}
    assert len(env["value"].encode()) <= REQUEST_CAP
    assert run["headers"]["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in run["url"] + json.dumps(run["body"])
    assert cloud.subprocess_calls and all(
        "print-access-token" in call for call in cloud.subprocess_calls
    )
    for request in cloud.requests:
        assert request["timeout"] is not None
        assert request["headers"]["authorization"] == f"Bearer {TOKEN}"
    assert cloud.unexpected == []
    assert out == json.dumps(result_payload(), sort_keys=True) + "\n"
    assert TOKEN not in out + err and PROJECT not in out + err


# --- L1: refusals before any cloud contact ------------------------------


@pytest.mark.parametrize(
    ("family", "argv_overrides", "stdin"),
    (
        ("pool", {}, b""),
        ("pool", {}, b"[]"),
        ("pool", {}, b"{not json"),
        ("pool", {}, b'{"a": 1, "a": 2}'),
        ("pool", {}, b'{"outer": {"a": 1, "a": 2}}'),
        ("pool", {}, b'{"a": "' + b"x" * 65_536 + b'"}'),
        ("pool", {}, padded_stdin(REQUEST_CAP + 1)),
        ("pool", {}, b'{"identity": {"source_sha": "' + b"f" * 40 + b'"}}'),
        ("migrate", {}, b'{"unexpected": 1}'),
        ("reset", {}, b"{}"),
        ("bogus", {}, b"{}"),
        ("pool", {"source_sha": SOURCE_SHA.upper()}, b"{}"),
        ("pool", {"source_sha": SOURCE_SHA[:39]}, b"{}"),
        ("pool", {"project": "x/../../evil"}, b"{}"),
    ),
    ids=(
        "empty",
        "array",
        "invalid",
        "duplicate",
        "nested-duplicate",
        "too-large",
        "final-value-too-large",
        "caller-identity",
        "migrate-nonempty",
        "family-reset",
        "family-unknown",
        "sha-uppercase",
        "sha-short",
        "project-path",
    ),
)
def test_job_runner_refuses_bad_input_before_any_cloud_call(
    job_module: Any,
    cloud: FakeCloud,
    family: str,
    argv_overrides: dict[str, str],
    stdin: bytes,
) -> None:
    """L1/FM2: only the four generic families and a well-formed body reach the cloud."""
    code, out, err = run_main(
        job_module,
        job_argv(family, **argv_overrides),
        stdin,
    )

    assert code != 0
    assert_no_cloud_contact(cloud)
    for value in (TOKEN, PROJECT, "googleapis", "x/../../evil"):
        assert value not in out + err


# --- L1: the response cannot choose what runs or what is read -----------


@pytest.mark.parametrize(
    "named",
    (
        f"projects/{PROJECT}/locations/us-east4/jobs/evil-job/executions/{EXECUTION}",
        "https://evil.example/v2/executions/e1",
        (
            f"projects/{PROJECT}/locations/us-east4/jobs/tailtag-replica-pool"
            '/executions/e1" OR true OR "'
        ),
    ),
    ids=("other-job", "absolute-url", "filter-injection"),
)
def test_execution_name_from_the_response_cannot_redirect_any_request(
    job_module: Any, cloud: FakeCloud, named: str
) -> None:
    """FM2: an inconsistent execution name fails; no URL or filter is built from it."""
    cloud.run_metadata_name = named

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert_fixed_failure(code, out, err, "evil")
    assert posts(cloud)[0]["url"].endswith("/jobs/tailtag-replica-pool:run")
    for request in cloud.requests:
        host = request["url"].split("/")[2]
        assert host in ALLOWED_HOSTS and request["url"].startswith("https://")
        assert "evil" not in request["url"] + json.dumps(request["body"])
        assert "OR true" not in json.dumps(request["body"])
    assert cloud.unexpected == []


# --- L1: waiting and log selection --------------------------------------


def test_logs_are_read_only_after_the_execution_completes(
    job_module: Any, cloud: FakeCloud
) -> None:
    """FM3: the runner polls the pinned execution until completionTime, then reads logs."""
    cloud.running_polls = 3

    code, out, _ = run_main(job_module, job_argv("pool"), b"{}")

    assert code == 0, out
    polls = [r for r in cloud.requests if f"/executions/{EXECUTION}" in r["url"]]
    assert len(polls) == 4
    assert cloud.logging_after_completion and all(cloud.logging_after_completion)
    last_poll = max(i for i, r in enumerate(cloud.requests) if r in polls)
    first_log = min(i for i, r in enumerate(cloud.requests) if "logging" in r["url"])
    assert last_poll < first_log


def test_runner_gives_up_when_the_execution_never_completes(
    job_module: Any, cloud: FakeCloud
) -> None:
    """FM3/L1: the wait has a bounded deadline and fails closed with fixed output."""
    cloud.never_completes = True

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert_fixed_failure(code, out, err)
    assert not any("logging" in r["url"] for r in cloud.requests)


@pytest.mark.parametrize(
    "honor_filter", (True, False), ids=("server-filter", "client-check")
)
def test_only_entries_of_the_launched_execution_are_used(
    job_module: Any, cloud: FakeCloud, honor_filter: bool
) -> None:
    """FM3: the filter names job and execution, and a foreign entry is ignored either way."""
    cloud.honor_filter = honor_filter
    foreign = result_payload("FAIL_FOREIGN")
    cloud.entries = [
        result_entry(foreign, execution=FOREIGN_EXECUTION),
        result_entry(
            result_payload("PASS", data={"mine": 1}), job="tailtag-replica-pool"
        ),
    ]

    code, out, _ = run_main(job_module, job_argv("pool"), b"{}")

    assert code == 0
    assert json.loads(out)["data"] == {"mine": 1}
    (log_request,) = [r for r in cloud.requests if "logging" in r["url"]]
    body = log_request["body"]
    assert body["resourceNames"] == [f"projects/{PROJECT}"]
    assert "tailtag-replica-pool" in body["filter"]
    assert EXECUTION in body["filter"]
    assert "stdout" in body["filter"]


def test_a_result_that_appears_late_in_the_log_is_found(
    job_module: Any, cloud: FakeCloud
) -> None:
    """L1: ingestion delay (empty first reads) is retried within the deadline."""
    cloud.empty_log_calls = 2

    code, out, _ = run_main(job_module, job_argv("pool"), b"{}")

    assert code == 0, out
    assert sum("logging" in r["url"] for r in cloud.requests) == 3


@pytest.mark.parametrize(
    "entries",
    (
        [],
        [result_entry(result_payload()), result_entry(result_payload())],
        [result_entry({**result_payload(), "extra": 1})],
        [result_entry({"result": "PASS", "data": {}})],
        [result_entry("plain text, not a json object")],
    ),
    ids=("zero", "two", "extra-key", "missing-key", "not-an-object"),
)
def test_exactly_one_well_formed_result_entry_is_required(
    job_module: Any, cloud: FakeCloud, entries: list[dict[str, Any]]
) -> None:
    """FM3: zero, several or malformed result entries never pass."""
    cloud.entries = entries

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert_fixed_failure(code, out, err)


def test_a_result_on_a_later_log_page_is_found(
    job_module: Any, cloud: FakeCloud
) -> None:
    """L1: nextPageToken is followed, and the lower time bound is in the filter."""
    cloud.log_pages = {
        "": {"nextPageToken": "page-2"},
        "page-2": {"entries": [result_entry(result_payload())]},
    }

    code, out, _ = run_main(job_module, job_argv("pool"), b"{}")

    assert code == 0, out
    first, second = [r["body"] for r in cloud.requests if "logging" in r["url"]]
    assert "pageToken" not in first and second["pageToken"] == "page-2"
    assert re.search(r'timestamp>="\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"', first["filter"])


def test_a_401_mid_poll_refreshes_the_token_once_and_continues(
    job_module: Any, cloud: FakeCloud
) -> None:
    """M2: an expired token is replaced once and the request is retried."""
    cloud.running_polls = 2
    cloud.rotate_at_poll = 2

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert code == 0, (out, err)
    assert len(cloud.subprocess_calls) == 2
    assert cloud.requests[-1]["headers"]["authorization"] == (
        f"Bearer {TOKEN_REFRESHED}"
    )
    assert TOKEN_REFRESHED not in out + err


@pytest.mark.parametrize(
    "error",
    (
        pytest.param(TimeoutError("read timed out"), id="read-timeout"),
        pytest.param(http.client.RemoteDisconnected("closed"), id="disconnected"),
        pytest.param(http.client.IncompleteRead(b"{"), id="short-read"),
    ),
)
@pytest.mark.parametrize(
    ("where", "passes"),
    (
        pytest.param(f"/executions/{EXECUTION}", True, id="poll"),
        pytest.param(":run", False, id="launch"),
    ),
)
def test_read_phase_network_errors_retry_only_after_the_launch(
    job_module: Any, cloud: FakeCloud, error: BaseException, where: str, passes: bool
) -> None:
    """A poll survives one read-phase error. A launch that may have started is not repeated."""
    cloud.running_polls = 1
    cloud.raise_once = (where, error)

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    if passes:
        assert code == 0, (out, err)
    else:
        assert_fixed_failure(code, out, err)
    assert len(posts(cloud)) == 1


def test_a_failed_run_request_is_never_retried(
    job_module: Any, cloud: FakeCloud
) -> None:
    """M2: a 503 on jobs:run could hide a started execution, so it is not repeated."""
    cloud.fail_on = ":run"
    cloud.fail_code = 503

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert_fixed_failure(code, out, err)
    assert len(posts(cloud)) == 1
    assert len(cloud.requests) == 1


def test_redirects_are_refused_by_the_runner_opener(job_module: Any) -> None:
    """L1: a 302 raises instead of sending the bearer token to another URL."""

    class Redirecting(urllib.request.BaseHandler):
        handler_order = 100
        opened: ClassVar[list[str]] = []

        def https_open(self, request: urllib.request.Request) -> Any:
            self.opened.append(request.full_url)
            headers = http.client.HTTPMessage()
            headers["Location"] = "https://evil.example/"
            response = urllib.response.addinfourl(
                io.BytesIO(b""), headers, request.full_url, 302
            )
            setattr(response, "msg", "Found")  # noqa: B010
            return response

    opener = job_module._opener()  # pyright: ignore[reportPrivateUsage]
    opener.add_handler(Redirecting())

    with pytest.raises(urllib.error.HTTPError) as caught:
        opener.open("https://run.googleapis.com/v2/x", timeout=1)

    assert caught.value.code == 302
    assert Redirecting.opened == ["https://run.googleapis.com/v2/x"]


# --- L1: exit status ----------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "state"),
    (
        (result_payload("FAIL_PREFLIGHT"), {"failedCount": 1}),
        (result_payload("pass"), {"succeededCount": 1}),
        (result_payload(True), {"succeededCount": 1}),
        (result_payload("PASS"), {"failedCount": 1}),
    ),
    ids=(
        "job-failure",
        "lowercase",
        "non-string",
        "pass-but-execution-failed",
    ),
)
def test_exit_zero_only_for_a_pass_result_of_a_succeeded_execution(
    job_module: Any, cloud: FakeCloud, payload: dict[str, Any], state: dict[str, Any]
) -> None:
    """FM4: any other result or a failed execution exits non-zero."""
    cloud.entries = [result_entry(payload)]
    cloud.execution_state = state

    code, out, _ = run_main(job_module, job_argv("pool"), b"{}")

    assert code != 0
    assert len(out.splitlines()) == 1
    json.loads(out)
    assert TOKEN not in out and PROJECT not in out


# --- L1: fixed failure output -------------------------------------------


@pytest.mark.parametrize(
    "failure",
    ("token-command", "logging-http-error", "oversized-response"),
)
def test_every_failure_prints_one_fixed_line_with_no_private_value(
    job_module: Any, cloud: FakeCloud, failure: str
) -> None:
    """FM1: token, project id, URL and response body never leave the process."""
    if failure == "token-command":
        cloud.token_ok = False
    elif failure == "logging-http-error":
        cloud.fail_on = "entries:list"
        cloud.fail_code = 400
    else:
        cloud.big_logs = True

    code, out, err = run_main(job_module, job_argv("pool"), b"{}")

    assert_fixed_failure(code, out, err)
    for request in cloud.requests:
        assert request["timeout"] is not None
    if failure == "oversized-response":
        # The reader stops at the cap, so the valid but oversized body never parses.
        assert cloud.big_response is not None
        assert cloud.big_response.handed_out <= RESPONSE_CAP + 1


# --- L2: reset runner ---------------------------------------------------


def write_config(path: Path, values: Mapping[str, str], mode: int = 0o600) -> Path:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(mode)
    if sys.platform == "win32":
        # Windows ignores chmod, so owner-only is an ACL. A wider mode adds a
        # Builtin Users read entry, as the Staging reset tests do.
        acl.make_owner_only(path.parent, container=True)
        acl.make_owner_only(path, extra_aces="" if mode == 0o600 else "(A;;FR;;;BU)")
    return path


def reset_argv(config: Path, operation: str, confirm: str | None = None) -> list[str]:
    argv = [
        "--project",
        PROJECT,
        "--source-sha",
        SOURCE_SHA,
        "--operation",
        operation,
        "--config",
        str(config),
    ]
    if confirm is not None:
        argv += ["--confirm", confirm]
    return argv


@pytest.mark.parametrize(
    ("operation", "confirm", "expected"),
    (
        (
            "reset",
            RESET_CONFIRM,
            ("tailtag-replica-reset", {"operation": "reset", "confirm": RESET_CONFIRM}),
        ),
        (
            "provision",
            PROVISION_CONFIRM,
            (
                "tailtag-replica-reset",
                {"operation": "provision", "confirm": PROVISION_CONFIRM},
            ),
        ),
        ("registry", None, ("tailtag-replica-registry-reconcile", dict[str, str]())),
    ),
)
def test_reset_runner_builds_the_u2_request_for_the_right_job(
    reset_module: Any,
    cloud: FakeCloud,
    tmp_path: Path,
    operation: str,
    confirm: str | None,
    expected: tuple[str, dict[str, str]],
) -> None:
    """L2: confirm strings and request shapes match U2; the registry operation needs no confirm."""
    job, fixed = expected
    cloud.job = job
    cloud.entries = [result_entry(result_payload())]
    config = write_config(tmp_path / "replica-reset.env", CONFIGURATION)

    code, out, err = run_main(reset_module, reset_argv(config, operation, confirm))

    assert code == 0, (out, err)
    (run,) = posts(cloud)
    assert run["url"].endswith(f"/jobs/{job}:run")
    value = json.loads(
        run["body"]["overrides"]["containerOverrides"][0]["env"][0]["value"]
    )
    assert value == {**fixed, "configuration": CONFIGURATION, "identity": IDENTITY}
    for private in (*CONFIGURATION.values(), TOKEN):
        assert private not in out + err


@pytest.mark.parametrize(
    ("operation", "confirm"),
    (
        ("reset", None),
        ("provision", RESET_CONFIRM),
    ),
    ids=("reset-none", "provision-swapped"),
)
def test_wrong_confirm_stops_before_any_subprocess_or_http_call(
    reset_module: Any,
    cloud: FakeCloud,
    tmp_path: Path,
    operation: str,
    confirm: str | None,
) -> None:
    """FM5: the confirm string is checked locally, before gcloud or any request."""
    config = write_config(tmp_path / "replica-reset.env", CONFIGURATION)

    code, out, err = run_main(reset_module, reset_argv(config, operation, confirm))

    assert code != 0
    assert_no_cloud_contact(cloud)
    for private in (*CONFIGURATION.values(), PROJECT, TOKEN):
        assert private not in out + err


def make_bad_config(tmp_path: Path, kind: str) -> Path:
    path = tmp_path / "replica-reset.env"
    if kind == "world-readable":
        return write_config(path, CONFIGURATION, 0o644)
    if kind == "missing-key":
        values = {k: v for k, v in CONFIGURATION.items() if k != CONFIGURATION_NAMES[8]}
        return write_config(path, values)
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ("world-readable", "missing-key"))
def test_unsafe_configuration_stops_before_any_cloud_call(
    reset_module: Any, cloud: FakeCloud, tmp_path: Path, kind: str
) -> None:
    """FM5: a loose, wrong or missing private file never reaches gcloud or the cloud."""
    if sys.platform == "win32" and kind == "world-readable":
        pytest.skip("POSIX mode bits")
    config = make_bad_config(tmp_path, kind)

    code, out, err = run_main(reset_module, reset_argv(config, "reset", RESET_CONFIRM))

    assert code != 0
    assert_no_cloud_contact(cloud)
    for private in (*CONFIGURATION.values(), PROJECT, TOKEN):
        assert private not in out + err


# --- L3: Taskfile -------------------------------------------------------


def task_block(name: str) -> str:
    text = (REPOSITORY_ROOT / "Taskfile.yml").read_text()
    match = re.search(rf"^  {re.escape(name)}:\n((?:    .*\n|\n)+)", text, re.MULTILINE)
    assert match, f"Taskfile task {name} must exist"
    return match.group(1)


@pytest.mark.parametrize(
    ("task", "module"),
    (("replica-job", "api_replica_job"), ("replica-reset", "api_replica_reset")),
)
def test_replica_tasks_pass_cli_args_and_are_windows_safe(
    task: str, module: str
) -> None:
    """FM6/L3: same shape as replica-neon-roles, silent, with the Windows path separator."""
    block = task_block(task)
    assert "silent: true" in block
    assert f"python -m scripts.{module} {{{{.CLI_ARGS}}}}" in block
    assert '{{if eq OS "windows"}};{{else}}:{{end}}' in block
    # No POSIX-only constructs that silently break on Windows.
    for posix_only in ("bash ", "$HOME", "~/", "chmod", "/dev/null"):
        assert posix_only not in block

    dry = task_dry_run(task, "--", "--project", "synthetic-project")
    assert f"-m scripts.{module} --project synthetic-project" in dry.stdout
    assert "synthetic-project" in dry.stdout
