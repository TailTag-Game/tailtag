"""Offline contract for the Render Staging one-off job launcher (#410 AC6, AC11)."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pytest import MonkeyPatch

from tests.test_api_staging_render_promote import (
    API_KEY,
    OTHER_SHA,
    OWNER_ID,
    REPOSITORY_ROOT,
    SERVICE_ID,
    SOURCE_SHA,
    FakeClock,
    deploy,
    service,
)

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

LIVE_ID = "dep-d0livestaging0000000"
JOB_ID = "job-d0resetjob0000000000"
CREATED_AT = "2026-10-31T12:00:00.000000Z"
PREFIX = "TAILTAG-RENDER-JOB "
RESET_COMMAND = (
    "python -m rehearsal.render_job --operation reset "
    f"--source-sha {SOURCE_SHA} --confirm reset-tailtag-staging"
)
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
RESET_PASS = {
    "operation": "reset",
    "outcome": "PASS",
    "source_sha": SOURCE_SHA,
    "baseline_version": 1,
    "counts": COUNTS,
}
PUBLIC_IDENTITY = {
    "source_sha": SOURCE_SHA,
    "deployment_id": None,
    "environment": "staging",
}


def result_line(result: Mapping[str, object]) -> str:
    return PREFIX + json.dumps(result, sort_keys=True, separators=(",", ":"))


def log(message: str) -> dict[str, object]:
    return {
        "id": "log",
        "message": message,
        "timestamp": CREATED_AT,
        "labels": [{"name": "resource", "value": JOB_ID}],
    }


class FakeRender:
    """The Render API boundary. It records every call and never opens a socket."""

    def __init__(self) -> None:
        self.service = service()
        self.owners: list[object] = [{"owner": {"id": OWNER_ID, "type": "team"}}]
        self.recent: list[object] = [{"deploy": deploy("live", deploy_id=LIVE_ID)}]
        self.live: list[list[object]] = [
            [{"deploy": deploy("live", deploy_id=LIVE_ID)}]
        ]
        self.instances: list[object] = [{"id": "srv-instance-a", "createdAt": "t"}]
        # Instance lists to return first, one per read, before self.instances.
        self.instance_reads: list[list[object]] = []
        self.submission: tuple[int, object] = (
            201,
            self.job("pending", start_command=RESET_COMMAND),
        )
        self.statuses = ["pending", "running", "succeeded"]
        # Logs arrive late: the first read after the job ends is empty.
        self.log_pages: list[dict[str, object]] = [
            {"logs": [], "hasMore": False},
            {
                "logs": [log("Starting job")],
                "hasMore": True,
                "nextStartTime": "2026-10-31T12:00:05Z",
                "nextEndTime": "2026-10-31T12:10:00Z",
            },
            {"logs": [log(result_line(RESET_PASS))], "hasMore": False},
        ]
        self.calls: list[tuple[str, str]] = []
        self.log_queries: list[dict[str, list[str]]] = []
        self.body: Mapping[str, object] | None = None

    def job(self, status: str, *, start_command: str = RESET_COMMAND) -> object:
        return {
            "id": JOB_ID,
            "serviceId": SERVICE_ID,
            "startCommand": start_command,
            "planId": "plan-srv-006",
            "createdAt": CREATED_AT,
            "status": status,
        }

    def __call__(
        self, key: str, method: str, path: str, body: Mapping[str, object] | None = None
    ) -> tuple[int, object]:
        assert key == API_KEY
        self.calls.append((method, path))
        prefix = f"/services/{SERVICE_ID}"
        if (method, path) == ("GET", prefix):
            return 200, self.service
        if (method, path) == ("GET", "/owners?limit=100"):
            return 200, self.owners
        if (method, path) == ("GET", f"{prefix}/deploys?limit=20"):
            return 200, self.recent
        if (method, path) == ("GET", f"{prefix}/deploys?status=live&limit=20"):
            return 200, self.live[0] if len(self.live) == 1 else self.live.pop(0)
        if (method, path) == ("GET", f"{prefix}/instances"):
            if self.instance_reads:
                return 200, self.instance_reads.pop(0)
            return 200, self.instances
        if (method, path) == ("POST", f"{prefix}/jobs"):
            self.body = body
            return self.submission
        if (method, path) == ("GET", f"{prefix}/jobs/{JOB_ID}"):
            return 200, self.job(self.statuses.pop(0))
        if method == "GET" and path.startswith("/logs?"):
            self.log_queries.append(urllib.parse.parse_qs(path.removeprefix("/logs?")))
            return 200, self.log_pages.pop(0) if self.log_pages else {"logs": []}
        raise AssertionError(f"unexpected Render call {method} {path}")

    @property
    def submitted(self) -> bool:
        return ("POST", f"/services/{SERVICE_ID}/jobs") in self.calls


class Harness:
    def __init__(self, module: ModuleType, tmp_path: Path) -> None:
        self.module = module
        self.render = FakeRender()
        self.public: list[object] = []
        self.receipts = tmp_path / "staging-deployments"
        self.receipts.mkdir()
        self.write_receipt()

    def write_receipt(self, **overrides: object) -> None:
        receipt = {
            "deployment_id": LIVE_ID,
            "source_sha": SOURCE_SHA,
            "environment": "staging",
            "overall_outcome": "SUCCEEDED",
            "final_active_state": "ACTIVE",
            **overrides,
        }
        (self.receipts / f"{LIVE_ID}.json").write_text(json.dumps(receipt))

    def fetch(self, url: str) -> object:
        if self.public:
            return self.public.pop(0)
        return {"status": "ok"} if url.endswith("/health/ready") else PUBLIC_IDENTITY

    def run(
        self, capsys: pytest.CaptureFixture[str], *arguments: str
    ) -> tuple[int, str, str]:
        status = self.module.main(list(arguments))
        output = capsys.readouterr()
        assert API_KEY not in output.out + output.err
        return status, output.out, output.err


@pytest.fixture
def harness(monkeypatch: MonkeyPatch, tmp_path: Path) -> Harness:
    module = importlib.import_module("scripts.api_staging_render_job")
    promote = importlib.import_module("scripts.api_staging_render_promote")
    preflight = importlib.import_module("scripts.api_staging_preflight")
    value = Harness(module, tmp_path)
    clock = FakeClock()
    monkeypatch.setattr(promote, "_render", value.render)
    monkeypatch.setattr(promote, "_service_id", lambda: SERVICE_ID)
    monkeypatch.setattr(promote, "_prompt_key", lambda: API_KEY)
    monkeypatch.setattr(preflight, "_fetch_json", value.fetch)
    monkeypatch.setattr(module, "_RECEIPTS", value.receipts)
    monkeypatch.setattr(module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(module.time, "sleep", clock.sleep)
    return value


RESET = ("reset", "--confirm", "reset-tailtag-staging")


def test_reset_job_starts_once_and_prints_its_one_pass_line(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC6: the launcher checks the target, starts one job, and reads its line."""
    status, out, err = harness.run(capsys, *RESET)

    assert (status, out, err) == (0, result_line(RESET_PASS) + "\n", "")
    # AC5: the start command names only the operation, S, and the confirmation.
    assert harness.render.body == {"startCommand": RESET_COMMAND}
    calls = harness.render.calls
    assert calls.count(("POST", f"/services/{SERVICE_ID}/jobs")) == 1
    submit = calls.index(("POST", f"/services/{SERVICE_ID}/jobs"))
    # AC11: workspace, live deploy and instance checks run before and after.
    for check in (
        ("GET", "/owners?limit=100"),
        ("GET", f"/services/{SERVICE_ID}/deploys?status=live&limit=20"),
        ("GET", f"/services/{SERVICE_ID}/instances"),
    ):
        assert check in calls[:submit]
        assert check in calls[submit:]
    first, *_, last = harness.render.log_queries
    assert first["ownerId"] == [OWNER_ID]
    assert first["resource"] == [JOB_ID]
    assert first["startTime"] == [CREATED_AT]
    assert first["direction"] == ["forward"]
    assert last["startTime"] == ["2026-10-31T12:00:05Z"]
    assert last["endTime"] == ["2026-10-31T12:10:00Z"]


def test_provision_job_uses_its_own_confirmation_and_command(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    command = (
        "python -m rehearsal.render_job --operation provision "
        f"--source-sha {SOURCE_SHA} --confirm provision-tailtag-staging-reset"
    )
    passed = {
        "operation": "provision",
        "outcome": "PASS",
        "source_sha": SOURCE_SHA,
        "provision_postcondition": "PASS",
    }
    harness.render.submission = (
        201,
        harness.render.job("pending", start_command=command),
    )
    harness.render.log_pages = [{"logs": [log(result_line(passed))], "hasMore": False}]

    status, out, _ = harness.run(
        capsys, "provision", "--confirm", "provision-tailtag-staging-reset"
    )

    assert (status, out) == (0, result_line(passed) + "\n")
    assert harness.render.body == {"startCommand": command}


@pytest.mark.parametrize(
    ("case", "phase"),
    [
        ("wrong-confirmation", "confirmation"),
        ("swapped-confirmation", "confirmation"),
        ("personal-workspace", "target"),
        ("deploy-in-progress", "target"),
        ("two-live-deploys", "target"),
        ("live-commit-differs", "target"),
        ("receipt-missing", "target"),
        ("receipt-not-succeeded", "target"),
        ("receipt-other-sha", "target"),
        ("public-other-sha", "target"),
        ("two-instances", "target"),
    ],
)
def test_target_mismatch_fails_closed_before_any_job_starts(
    harness: Harness, capsys: pytest.CaptureFixture[str], case: str, phase: str
) -> None:
    """AC11: every Render replacement for a Railway check refuses on its own."""
    arguments: list[str] = list(RESET)
    render = harness.render
    if case == "wrong-confirmation":
        arguments[-1] = "reset-tailtag-production"
    elif case == "swapped-confirmation":
        arguments[-1] = "provision-tailtag-staging-reset"
    elif case == "personal-workspace":
        render.owners = [{"owner": {"id": OWNER_ID, "type": "user"}}]
    elif case == "deploy-in-progress":
        render.recent = [{"deploy": deploy("build_in_progress")}]
    elif case == "two-live-deploys":
        live = {"deploy": deploy("live", deploy_id=LIVE_ID)}
        render.live = [[live, live]]
    elif case == "live-commit-differs":
        render.live = [
            [{"deploy": deploy("live", deploy_id=LIVE_ID, commit=OTHER_SHA)}]
        ]
    elif case == "receipt-missing":
        (harness.receipts / f"{LIVE_ID}.json").unlink()
    elif case == "receipt-not-succeeded":
        harness.write_receipt(overall_outcome="FAILED")
    elif case == "receipt-other-sha":
        harness.write_receipt(source_sha=OTHER_SHA)
    elif case == "public-other-sha":
        harness.public = [{**PUBLIC_IDENTITY, "source_sha": OTHER_SHA}]
    else:
        render.instances = [{"id": "a"}, {"id": "b"}]

    status, out, err = harness.run(capsys, *arguments)

    assert (status, out, err) == (1, "", f"FAIL render job {phase}\n")
    assert not render.submitted


@pytest.mark.parametrize(
    ("case", "line"),
    [
        ("job-failed", "printed"),
        ("succeeded-but-fail-line", "indeterminate"),
        ("failed-but-pass-line", "indeterminate"),
        ("canceled-fail-line", "indeterminate"),
        ("wrong-counts", "indeterminate"),
        ("other-sha", "indeterminate"),
        ("two-result-lines", "indeterminate"),
        ("no-result-line", "indeterminate"),
        ("target-changed", "changed"),
    ],
)
def test_launcher_exits_zero_only_for_a_consistent_pass(
    harness: Harness, capsys: pytest.CaptureFixture[str], case: str, line: str
) -> None:
    """AC6: a FAIL line, an odd result, or a changed target never exits 0."""
    render = harness.render
    failed = {"operation": "reset", "outcome": "FAIL", "phase": "maintenance retained"}

    def only(*messages: str) -> None:
        render.log_pages = [{"logs": [log(m) for m in messages], "hasMore": False}]

    if case == "job-failed":
        render.statuses = ["running", "failed"]
        only(result_line(failed))
    elif case == "succeeded-but-fail-line":
        only(result_line(failed))
    elif case == "failed-but-pass-line":
        render.statuses = ["failed"]
        only(result_line(RESET_PASS))
    elif case == "canceled-fail-line":
        render.statuses = ["canceled"]
        only(result_line(failed))
    elif case == "wrong-counts":
        only(result_line({**RESET_PASS, "counts": {**COUNTS, "catches": 1}}))
    elif case == "other-sha":
        only(result_line({**RESET_PASS, "source_sha": OTHER_SHA}))
    elif case == "two-result-lines":
        only(result_line(RESET_PASS), result_line(RESET_PASS))
    elif case == "no-result-line":
        render.log_pages = []
    else:
        other = {"deploy": deploy("live", deploy_id="dep-d0otherlive000000000")}
        render.live = [[{"deploy": deploy("live", deploy_id=LIVE_ID)}], [other]]

    status, out, err = harness.run(capsys, *RESET)

    assert status == 1
    if line == "printed":
        assert (out, err) == (result_line(failed) + "\n", "")
    elif line == "changed":
        assert (out, err) == ("", f"FAIL render job target changed {JOB_ID}\n")
    else:
        assert (out, err) == ("", f"FAIL render job indeterminate {JOB_ID}\n")


def test_a_web_restart_after_the_job_settles_before_the_pass_line(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate can restart the web instance, so the post-check waits a while."""
    one = harness.render.instances
    harness.render.instance_reads = [one, [], one + one]

    status, out, _ = harness.run(capsys, *RESET)

    assert (status, out) == (0, result_line(RESET_PASS) + "\n")


@pytest.mark.parametrize("case", ["malformed-job", "other-command"])
def test_unconfirmed_submission_is_indeterminate_and_never_retried(
    harness: Harness, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    """Render may have started a job although no matching job came back."""
    harness.render.submission = (
        (201, {"id": "not-a-job"})
        if case == "malformed-job"
        else (201, harness.render.job("pending", start_command="python -c pass"))
    )

    status, out, err = harness.run(capsys, *RESET)

    assert (status, out) == (1, "")
    assert err == "FAIL render job submission indeterminate\n"
    assert harness.render.calls.count(("POST", f"/services/{SERVICE_ID}/jobs")) == 1


def test_a_job_that_never_ends_is_indeterminate_and_is_not_canceled(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """Canceling a reset mid-gate is unsafe, so the launcher only reports it."""
    harness.render.statuses = ["running"] * 10_000

    status, out, err = harness.run(capsys, *RESET)

    assert (status, out) == (1, "")
    assert err == f"FAIL render job indeterminate {JOB_ID}\n"
    assert not any("cancel" in path for _, path in harness.render.calls)


def test_receipts_are_read_from_the_repository_record() -> None:
    module = importlib.import_module("scripts.api_staging_render_job")
    assert cast(Path, module._RECEIPTS) == (  # pyright: ignore[reportPrivateUsage]
        REPOSITORY_ROOT / "docs/development/staging-deployments"
    )
