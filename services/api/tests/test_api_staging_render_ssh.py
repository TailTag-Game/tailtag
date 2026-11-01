"""Offline contract for the Render Staging operator SSH launcher (#410 AC9, AC11)."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pytest import MonkeyPatch

from tests.test_api_staging_render_job import (
    API_KEY,
    LIVE_ID,
    OWNER_ID,
    SERVICE_ID,
    SOURCE_SHA,
    FakeClock,
    Harness,
    deploy,
)

INSTANCE_ID = f"{SERVICE_ID}-abcde"
WHOAMI = {
    "email": "finn@finnthepanther.com",
    "id": "usr-finn",
    "name": "Finn the Panther",
}
# The read-only checks each operation needs before and after its session.
PLANS: dict[str, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]] = {
    "managed-create": (
        (("reconcile", "PASS"), ("inspect", "FAIL_MANAGED_OPERATOR_MISSING")),
        (("inspect", "FAIL_LIMITED_OPERATOR_MISSING"),),
    ),
    "lifecycle-provision": (
        (("reconcile", "PASS"), ("inspect", "FAIL_LIMITED_OPERATOR_MISSING")),
        (("inspect", "PASS"),),
    ),
    "lifecycle-rotate-password": ((("inspect", "PASS"),), (("inspect", "PASS"),)),
    "lifecycle-decommission": (
        (("inspect", "PASS"),),
        (("inspect", "FAIL_LIMITED_OPERATOR_STATE"),),
    ),
    "managed-password-rotate": (
        (("reconcile", "PASS"), ("inspect", "PASS")),
        (("inspect", "PASS"),),
    ),
    "managed-operator-replace": (
        (("reconcile", "PASS"), ("inspect", "PASS")),
        (("inspect", "PASS"),),
    ),
    "emergency-create": (
        (("reconcile", "PASS"), ("inspect", "PASS"), ("emergency-state", "ABSENT")),
        (("emergency-state", "READY"), ("inspect", "PASS")),
    ),
    "emergency-decommission": (
        (("reconcile", "PASS"), ("inspect", "PASS"), ("emergency-state", "READY")),
        (("emergency-state", "DECOMMISSIONED"), ("inspect", "PASS")),
    ),
}


class Fakes:
    """The Render CLI and the job runner, both at their process boundaries."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.whoami: object = WHOAMI
        self.whoami_returncode = 0
        self.ssh_returncode = 0
        self.ssh_calls: list[tuple[list[str], Mapping[str, object]]] = []
        self.results: list[str] = []
        self.jobs: list[str] = []
        self.events: list[str] = []
        self.job_failure: str | None = None
        self.real_interactive: object = None

    def run(
        self, arguments: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        argv = list(arguments)
        if argv[:2] == ["render", "whoami"]:
            assert argv == ["render", "whoami", "-o", "json"]
            self.events.append("whoami")
            return subprocess.CompletedProcess(
                argv, self.whoami_returncode, json.dumps(self.whoami), ""
            )
        assert argv[:2] == ["render", "ssh"]
        self.events.append("ssh")
        self.ssh_calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.ssh_returncode)

    def run_job(
        self, key: str, service_id: str, owner_id: str, operation: str, source_sha: str
    ) -> tuple[str, str, str]:
        assert (key, service_id, owner_id, source_sha) == (
            API_KEY,
            SERVICE_ID,
            OWNER_ID,
            SOURCE_SHA,
        )
        self.jobs.append(operation)
        self.events.append(operation)
        if self.job_failure == operation:
            job = importlib.import_module("scripts.api_staging_render_job")
            raise job.JobFailure("indeterminate job-d0failedjob0000000000")
        result = self.results.pop(0)
        line = "TAILTAG-RENDER-JOB " + json.dumps(
            {"operation": operation, "result": result, "source_sha": source_sha}
        )
        return "PASS", line, "job-d0okjob00000000000000"


@pytest.fixture
def fakes(monkeypatch: MonkeyPatch, tmp_path: Path) -> Fakes:
    module = importlib.import_module("scripts.api_staging_render_job")
    promote = importlib.import_module("scripts.api_staging_render_promote")
    preflight = importlib.import_module("scripts.api_staging_preflight")
    harness = Harness(module, tmp_path)
    harness.render.instances = [{"id": INSTANCE_ID, "createdAt": "t"}]
    value = Fakes(harness)
    clock = FakeClock()
    monkeypatch.setattr(promote, "_render", harness.render)
    monkeypatch.setattr(promote, "_service_id", lambda: SERVICE_ID)
    monkeypatch.setattr(promote, "_prompt_key", lambda: API_KEY)
    monkeypatch.setattr(preflight, "_fetch_json", harness.fetch)
    monkeypatch.setattr(module, "_RECEIPTS", harness.receipts)
    monkeypatch.setattr(module, "run_job", value.run_job)
    monkeypatch.setattr(module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(module.time, "sleep", clock.sleep)
    launcher = importlib.import_module("scripts.api_staging_render_ssh")
    value.real_interactive = launcher._interactive  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(launcher.subprocess, "run", value.run)
    monkeypatch.setattr(launcher, "_interactive", lambda: True)
    return value


def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_staging_render_ssh")


def plan(fakes: Fakes, operation: str) -> None:
    before, after = PLANS[operation]
    fakes.results = [result for _, result in (*before, *after)]


def run(capsys: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str, str]:
    status = launcher().main(list(arguments))
    output = capsys.readouterr()
    assert API_KEY not in output.out + output.err
    return status, output.out, output.err


def test_the_launcher_plans_match_the_reviewed_table() -> None:
    """Each operation's checks are reviewed here against the inspector's order."""
    assert launcher()._PLANS == PLANS


@pytest.mark.parametrize("operation", ["emergency-create", "lifecycle-decommission"])
def test_each_operation_checks_runs_one_pinned_session_then_proves_its_state(
    fakes: Fakes, capsys: pytest.CaptureFixture[str], operation: str
) -> None:
    """AC9: the read-only jobs bracket one session on the exact live instance."""
    plan(fakes, operation)

    status, out, err = run(capsys, operation)

    assert (status, out, err) == (0, f"PASS render ssh {operation}\n", "")
    before, after = PLANS[operation]
    assert fakes.events == [
        "whoami",
        *(job for job, _ in before),
        "whoami",
        "ssh",
        *(job for job, _ in after),
    ]
    [(argv, kwargs)] = fakes.ssh_calls
    assert argv == [
        "render",
        "ssh",
        INSTANCE_ID,
        "-o",
        "text",
        "--",
        "-o",
        "UpdateHostKeys=no",
        "-t",
        (
            "cd /app && exec /app/.venv/bin/python -m accounts.render_operator "
            f"--operation {operation} --source-sha {SOURCE_SHA}"
        ),
    ]
    # The session uses the real terminal, so nothing is captured or piped.
    assert not {"stdin", "stdout", "stderr", "capture_output", "input"} & set(kwargs)


@pytest.mark.parametrize(
    ("case", "phase"),
    [
        ("unknown-operation", "arguments"),
        ("other-account", "identity"),
        ("other-name", "identity"),
        ("whoami-failed", "identity"),
        ("two-instances", "target"),
        ("odd-instance-id", "target"),
    ],
)
def test_identity_or_target_mismatch_stops_before_any_job_or_session(
    fakes: Fakes, capsys: pytest.CaptureFixture[str], case: str, phase: str
) -> None:
    """AC11: the CLI account, workspace, deploy, and one instance must all match."""
    operation = "emergency-create"
    render = fakes.harness.render
    if case == "unknown-operation":
        operation = "matrix"
    elif case == "other-account":
        fakes.whoami = {**WHOAMI, "email": "someone@example.com"}
    elif case == "other-name":
        fakes.whoami = {**WHOAMI, "name": "Someone Else"}
    elif case == "whoami-failed":
        fakes.whoami_returncode = 1
    elif case == "two-instances":
        render.instances = [{"id": INSTANCE_ID}, {"id": f"{SERVICE_ID}-fghij"}]
    else:
        render.instances = [{"id": "srv-otherservice0-abcde"}]

    status, out, err = run(capsys, operation)

    named = "" if phase == "arguments" else f" {operation}"
    assert (status, out, err) == (1, "", f"FAIL render ssh{named} {phase}\n")
    assert fakes.jobs == []
    assert fakes.ssh_calls == []


def test_an_unexpected_precondition_stops_before_the_session(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """Managed create needs the managed operator missing, so PASS refuses."""
    fakes.results = ["PASS", "PASS"]

    status, _, err = run(capsys, "managed-create")

    assert (status, err) == (1, "FAIL render ssh managed-create precondition inspect\n")
    assert fakes.ssh_calls == []


def test_a_job_with_no_proved_result_stops_without_a_retry(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    plan(fakes, "emergency-create")
    fakes.job_failure = "inspect"

    status, _, err = run(capsys, "emergency-create")

    assert status == 1
    assert err == (
        "FAIL render ssh emergency-create indeterminate job-d0failedjob0000000000\n"
    )
    assert fakes.jobs == ["reconcile", "inspect"]
    assert fakes.ssh_calls == []


def test_the_instance_must_still_be_the_same_right_before_the_session(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """A restart between the checks and the session refuses the old instance."""
    plan(fakes, "lifecycle-rotate-password")
    one = fakes.harness.render.instances
    # The target check and the instance pin each read the list, before the
    # jobs and again right before the session. Only the last read changes.
    fakes.harness.render.instance_reads = [
        one,
        one,
        one,
        [{"id": f"{SERVICE_ID}-fghij"}],
    ]

    status, _, err = run(capsys, "lifecycle-rotate-password")

    assert (status, err) == (1, "FAIL render ssh lifecycle-rotate-password target\n")
    assert fakes.jobs == ["inspect"]
    assert fakes.ssh_calls == []


def test_a_failed_session_is_reported_and_never_retried(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """The in-image entry point exits 1 on any failure, so the launcher stops."""
    plan(fakes, "managed-password-rotate")
    fakes.ssh_returncode = 1

    status, _, err = run(capsys, "managed-password-rotate")

    assert (status, err) == (
        1,
        "FAIL render ssh managed-password-rotate session uncertain\n",
    )
    assert len(fakes.ssh_calls) == 1
    assert fakes.jobs == ["reconcile", "inspect"]


def test_a_zero_exit_without_the_expected_new_state_fails(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """A zero exit alone never proves the command, the read-only check must."""
    plan(fakes, "emergency-create")
    fakes.results[-2] = "ABSENT"

    status, _, err = run(capsys, "emergency-create")

    assert (status, err) == (
        1,
        "FAIL render ssh emergency-create postcondition emergency-state\n",
    )


def test_a_changed_live_deploy_after_the_session_fails(
    fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    plan(fakes, "lifecycle-decommission")
    live = {"deploy": deploy("live", deploy_id=LIVE_ID)}
    other = {"deploy": deploy("live", deploy_id="dep-d0otherlive000000000")}
    fakes.harness.render.live = [[live], [live], [other]]

    status, _, err = run(capsys, "lifecycle-decommission")

    assert (status, err) == (
        1,
        "FAIL render ssh lifecycle-decommission target changed\n",
    )
    assert len(fakes.ssh_calls) == 1


def test_a_terminal_sees_each_wait_around_the_session(
    fakes: Fakes, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    """The operator sees when to wait and when the session prompts begin."""
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    plan(fakes, "lifecycle-rotate-password")

    status, out, err = run(capsys, "lifecycle-rotate-password")

    assert (status, out) == (0, "PASS render ssh lifecycle-rotate-password\n")
    assert err == (
        "... checking the Render Staging target\n"
        "... opening the render ssh session\n"
        "... waiting until Staging serves the same deploy again\n"
    )


def test_a_non_terminal_refuses_before_any_provider_call(
    fakes: Fakes, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    """The session needs your real terminal for its hidden prompts."""
    module = launcher()
    monkeypatch.setattr(module, "_interactive", fakes.real_interactive)
    monkeypatch.setattr("sys.stdin", io.StringIO())
    status = module.main(["emergency-create"])
    err = capsys.readouterr().err

    assert (status, err) == (1, "FAIL render ssh emergency-create terminal\n")
    assert fakes.events == []


def test_plans_cover_every_operation_of_the_in_image_entry_point() -> None:
    """Each in-image operation has a launcher plan, and no plan has no operation."""
    from accounts import render_operator

    operations = render_operator._OPERATIONS  # pyright: ignore[reportPrivateUsage]
    assert set(cast(dict[str, object], launcher()._PLANS)) == set(operations)
