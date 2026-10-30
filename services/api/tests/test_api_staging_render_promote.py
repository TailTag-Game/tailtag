"""Offline acceptance contract for the exact-SHA Render Staging promotion (#409)."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
import warnings
from collections.abc import Callable, Mapping
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import NoReturn, Self, cast

import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

SOURCE_SHA = "eb518d36baa21b7943acd9744f2499d80d527e61"
OTHER_SHA = "a" * 40
MAIN_SHA = "2586ade0c1115e090044c9385831b33538918dcf"
SERVICE_ID = "srv-d0staging000000000000"
OWNER_ID = "tea-d0tailtag0000000000"
DEPLOY_ID = "dep-d0promotion000000000"
API_KEY = "rnd_SyntheticRenderKey0123456789"
RUN_ID = 35179642379
CREATED_AT = "2026-10-30T12:00:00.000000Z"
RENDER_ORIGIN = "https://tailtag-api-staging.onrender.com"
RENDER_IDENTITY = {
    "source_sha": SOURCE_SHA,
    "deployment_id": None,
    "environment": "staging",
}


def service(**overrides: object) -> dict[str, object]:
    """Return the Render service fields that the preflight reads back."""
    value: dict[str, object] = {
        "id": SERVICE_ID,
        "name": "tailtag-api-staging",
        "ownerId": OWNER_ID,
        "type": "web_service",
        "repo": "https://github.com/TailTag-Game/tailtag",
        "branch": "main",
        "autoDeployTrigger": "off",
        "suspended": "not_suspended",
        "serviceDetails": {
            "runtime": "docker",
            "healthCheckPath": "/health/ready",
            "envSpecificDetails": {
                "preDeployCommand": "python -m config.replacement_migrate"
            },
        },
    }
    value.update(overrides)
    return value


def deploy(
    status: str, *, commit: str = SOURCE_SHA, deploy_id: str = DEPLOY_ID
) -> dict[str, object]:
    return {
        "id": deploy_id,
        "commit": {"id": commit},
        "status": status,
        "trigger": "api",
        "createdAt": CREATED_AT,
    }


class FakeRender:
    """The Render API boundary. It records every call and never opens a socket."""

    def __init__(self) -> None:
        self.service = service()
        self.owners: list[object] = [
            {"owner": {"id": OWNER_ID, "type": "team"}, "cursor": "c"}
        ]
        self.recent: list[object] = [{"deploy": deploy("live", commit=OTHER_SHA)}]
        self.submission: tuple[int, object] = (201, {"id": DEPLOY_ID})
        self.statuses = [
            "created",
            "queued",
            "build_in_progress",
            "pre_deploy_in_progress",
            "update_in_progress",
            "live",
        ]
        self.final = deploy("live")
        self.live: list[object] = []
        self.calls: list[tuple[str, str]] = []
        self.on_first_observation: Callable[[], None] | None = None

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
        if (method, path) == ("POST", f"{prefix}/deploys"):
            assert body == {"commitId": SOURCE_SHA, "clearCache": "do_not_clear"}
            return self.submission
        if (method, path) == ("GET", f"{prefix}/deploys/{DEPLOY_ID}"):
            if self.on_first_observation is not None:
                self.on_first_observation()
                self.on_first_observation = None
            if self.statuses:
                return 200, deploy(self.statuses.pop(0))
            return 200, self.final
        if (method, path) == ("GET", f"{prefix}/deploys?status=live&limit=20"):
            return 200, self.live
        raise AssertionError(f"unexpected Render call {method} {path}")

    @property
    def submitted(self) -> bool:
        return ("POST", f"/services/{SERVICE_ID}/deploys") in self.calls


class Harness:
    def __init__(self, module: ModuleType, tmp_path: Path) -> None:
        self.module = module
        self.render = FakeRender()
        self.identity: list[object] = [
            RENDER_IDENTITY,
            {"status": "ok"},
            RENDER_IDENTITY,
        ]
        self.smoke_returncode = 0
        self.smoke_urls: list[str] = []
        self.receipt = (
            tmp_path / "docs/development/staging-deployments" / f"{DEPLOY_ID}.json"
        )
        self.render.on_first_observation = self.assert_checkpoint

    def assert_checkpoint(self) -> None:
        """#202 AC4: the S/D record exists before the first observation of D."""
        receipt = self.receipt_json()
        assert receipt["deployment_id"] == DEPLOY_ID
        assert receipt["overall_outcome"] == "PENDING"

    def fetch(self, url: str) -> object:
        assert url.startswith(RENDER_ORIGIN + "/health/")
        return self.identity.pop(0)

    def run(
        self, arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert arguments == ["task", "api-smoke"]
        environment = cast(Mapping[str, str], kwargs["env"])
        self.smoke_urls.append(environment["API_BASE_URL"])
        return subprocess.CompletedProcess(arguments, self.smoke_returncode, "", "")

    def receipt_json(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.receipt.read_text()))


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def promote() -> ModuleType:
    return importlib.import_module("scripts.api_staging_render_promote")


@pytest.fixture
def harness(promote: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path) -> Harness:
    staging_promote = importlib.import_module("scripts.api_staging_promote")
    preflight = importlib.import_module("scripts.api_staging_preflight")
    value = Harness(promote, tmp_path)
    clock = FakeClock()
    monkeypatch.setattr(promote, "_REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(staging_promote, "_REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(promote, "_render", value.render)
    monkeypatch.setattr(promote, "_service_id", lambda: SERVICE_ID)
    monkeypatch.setattr(promote, "_prompt_key", lambda: API_KEY)

    def eligible(sha: str) -> tuple[str, dict[str, object]]:
        return MAIN_SHA, {"id": RUN_ID, "run_attempt": 1, "head_sha": sha}

    monkeypatch.setattr(promote, "_eligible", eligible)
    monkeypatch.setattr(promote, "_run", value.run)
    monkeypatch.setattr(preflight, "_fetch_json", value.fetch)
    monkeypatch.setattr(promote.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(promote.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_render_promote.py",
            "--source-sha",
            SOURCE_SHA,
            "--confirm",
            "promote-tailtag-render-staging",
        ],
    )
    return value


def test_promotion_records_one_exact_successful_render_deploy(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    """#409 AC2/AC8/AC10: one submission, exact identity, smoke, and active check."""
    assert harness.module.main() == 0

    assert harness.receipt_json() == {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOY_ID,
        "environment": "staging",
        "deployment_timestamp": CREATED_AT,
        "accepted_main_sha": MAIN_SHA,
        "validation_run_id": RUN_ID,
        "validation_run_attempt": 1,
        "deployment_outcome": "SUCCEEDED",
        "migration_outcome": "SUCCEEDED",
        "startup_outcome": "SUCCEEDED",
        "readiness_outcome": "SUCCEEDED",
        "identity_outcome": "SUCCEEDED",
        "smoke_outcome": "SUCCEEDED",
        "final_active_state": "ACTIVE",
        "overall_outcome": "SUCCEEDED",
    }
    assert [call for call in harness.render.calls if call[0] == "POST"] == [
        ("POST", f"/services/{SERVICE_ID}/deploys")
    ]
    assert harness.render.calls[:3] == [
        ("GET", f"/services/{SERVICE_ID}"),
        ("GET", "/owners?limit=100"),
        ("GET", f"/services/{SERVICE_ID}/deploys?limit=20"),
    ]
    assert harness.smoke_urls == [RENDER_ORIGIN]
    captured = capsys.readouterr()
    assert captured.out == (
        f"promotion {SOURCE_SHA} {DEPLOY_ID} SUCCEEDED "
        f"docs/development/staging-deployments/{DEPLOY_ID}.json\n"
    )
    assert API_KEY not in captured.out + captured.err + harness.receipt.read_text()


def _details(**overrides: object) -> dict[str, object]:
    details = cast(dict[str, object], service()["serviceDetails"])
    return {**details, **overrides}


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("service", service(autoDeployTrigger="checksPass")),
        ("service", service(branch="feature")),
        ("service", service(name="tailtag-api-development")),
        ("service", service(repo="https://github.com/other/tailtag")),
        ("service", service(suspended="suspended")),
        ("service", service(id="srv-d0other0000000000000")),
        (
            "service",
            service(serviceDetails=_details(healthCheckPath="/health/live")),
        ),
        (
            "service",
            service(serviceDetails=_details(envSpecificDetails={})),
        ),
        (
            "owners",
            [
                {"owner": {"id": OWNER_ID, "type": "team"}},
                {"owner": {"id": "usr-d0personal000000000", "type": "user"}},
            ],
        ),
        ("owners", [{"owner": {"id": "tea-d0other0000000000000", "type": "team"}}]),
        ("owners", [{"owner": {"id": OWNER_ID, "type": "user"}}]),
        ("recent", [{"deploy": deploy("build_in_progress", commit=OTHER_SHA)}]),
    ),
    ids=(
        "auto-deploy-on",
        "other-branch",
        "other-name",
        "other-repo",
        "suspended",
        "other-service",
        "other-health-check",
        "no-pre-deploy-command",
        "several-workspaces",
        "other-workspace",
        "personal-workspace",
        "deploy-building",
    ),
)
def test_render_preflight_mismatch_stops_before_submission(
    harness: Harness,
    capsys: pytest.CaptureFixture[str],
    change: str,
    value: object,
) -> None:
    """#409 AC1/AC7/AC9/AC10: settings, workspace, and idleness gate the deploy."""
    setattr(harness.render, change, value)

    assert harness.module.main() == 1

    assert not harness.render.submitted
    assert not harness.receipt.exists()
    assert capsys.readouterr().err == "FAIL promotion unavailable\n"


def _raise_value_error(*_: object) -> NoReturn:
    raise ValueError("synthetic denial")


@pytest.mark.parametrize("seam", ("_service_id", "_eligible", "_prompt_key"))
def test_target_eligibility_or_key_failure_stops_before_any_render_call(
    harness: Harness, monkeypatch: MonkeyPatch, seam: str
) -> None:
    """#409 AC2/AC7/AC9: no Render call happens before these gates pass."""
    if seam == "_eligible":

        def eligible(_: str) -> tuple[str, dict[str, object]]:
            return MAIN_SHA, {"id": RUN_ID, "run_attempt": 0}

        monkeypatch.setattr(harness.module, seam, eligible)
    else:
        monkeypatch.setattr(harness.module, seam, _raise_value_error)

    assert harness.module.main() == 1

    assert harness.render.calls == []
    assert not harness.receipt.exists()


@pytest.mark.parametrize(
    "submission",
    ((202, None), (201, {"id": "not-a-deploy"})),
    ids=("queued-without-body", "malformed-id"),
)
def test_submission_without_a_deploy_id_is_indeterminate_without_retry(
    harness: Harness,
    capsys: pytest.CaptureFixture[str],
    submission: tuple[int, object],
) -> None:
    """#409 AC10: no D means no receipt, no retry, and a distinct report."""
    harness.render.submission = submission

    assert harness.module.main() == 1

    assert [call[0] for call in harness.render.calls].count("POST") == 1
    assert not harness.receipt.exists()
    assert capsys.readouterr().err == (
        f"FAIL promotion submission indeterminate {SOURCE_SHA}\n"
    )


def test_unwritable_checkpoint_still_reports_d(
    harness: Harness, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#202 AC4: the operator keeps S and D when the receipt cannot be written."""

    def fail_persist(_: object) -> NoReturn:
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(harness.module, "_persist", fail_persist)

    assert harness.module.main() == 1

    assert capsys.readouterr().err == (
        f"FAIL promotion evidence unavailable for {SOURCE_SHA} {DEPLOY_ID} "
        f"docs/development/staging-deployments/{DEPLOY_ID}.json\n"
    )


@pytest.mark.parametrize(
    ("status", "outcomes"),
    (
        (
            "pre_deploy_failed",
            ("FAILED", "FAILED", "PENDING", "PENDING", "OR7_HANDOFF"),
        ),
        ("build_failed", ("FAILED", "PENDING", "PENDING", "PENDING", "FAILED")),
        ("update_failed", ("FAILED", "SUCCEEDED", "INDETERMINATE", "FAILED", "FAILED")),
        ("canceled", ("FAILED", "PENDING", "PENDING", "PENDING", "FAILED")),
        ("deactivated", ("FAILED", "PENDING", "PENDING", "PENDING", "FAILED")),
        (
            "unknown_status",
            ("INDETERMINATE", "PENDING", "PENDING", "PENDING", "INDETERMINATE"),
        ),
    ),
)
def test_render_deploy_status_maps_to_the_202_outcomes(
    harness: Harness, status: str, outcomes: tuple[str, ...]
) -> None:
    """#409 AC3/AC10: each terminal status ends the promotion with its outcome."""
    harness.render.statuses = ["build_in_progress", status]

    assert harness.module.main() == 1

    receipt = harness.receipt_json()
    assert (
        receipt["deployment_outcome"],
        receipt["migration_outcome"],
        receipt["startup_outcome"],
        receipt["readiness_outcome"],
        receipt["overall_outcome"],
    ) == outcomes
    assert receipt["identity_outcome"] == "PENDING"
    assert harness.smoke_urls == []


def test_deploy_that_never_finishes_is_indeterminate(harness: Harness) -> None:
    """#409 AC10: a timeout records INDETERMINATE and never submits again."""
    harness.render.statuses = ["build_in_progress"] * 1000

    assert harness.module.main() == 1

    assert harness.receipt_json()["overall_outcome"] == "INDETERMINATE"
    assert [call[0] for call in harness.render.calls].count("POST") == 1


def test_live_deploy_of_another_commit_is_indeterminate(harness: Harness) -> None:
    """#409 AC8: D must carry commit S."""
    harness.render.statuses = []
    harness.render.final = deploy("live", commit=OTHER_SHA)

    assert harness.module.main() == 1

    assert harness.receipt_json()["overall_outcome"] == "INDETERMINATE"
    assert harness.smoke_urls == []


def test_public_identity_mismatch_fails_before_smoke(harness: Harness) -> None:
    """#409 AC8: the public identity must show S. The preflight tests cover the rest."""
    public_identity = {**RENDER_IDENTITY, "source_sha": OTHER_SHA}
    harness.identity = [public_identity, {"status": "ok"}, public_identity]

    assert harness.module.main() == 1

    receipt = harness.receipt_json()
    assert receipt["identity_outcome"] == "FAILED"
    assert receipt["overall_outcome"] == "FAILED"
    assert harness.smoke_urls == []


def test_smoke_failure_fails_the_promotion(harness: Harness) -> None:
    """#202 AC8 on Render: the credential-free smoke must pass."""
    harness.smoke_returncode = 1

    assert harness.module.main() == 1

    receipt = harness.receipt_json()
    assert receipt["smoke_outcome"] == "FAILED"
    assert receipt["overall_outcome"] == "FAILED"


@pytest.mark.parametrize(
    ("final", "live", "state", "overall"),
    (
        (
            deploy("deactivated"),
            [{"deploy": deploy("live", commit=OTHER_SHA, deploy_id="dep-d0newer0")}],
            "SUPERSEDED",
            "SUPERSEDED",
        ),
        (deploy("deactivated"), [], "INACTIVE", "FAILED"),
        (deploy("update_in_progress"), [], "INDETERMINATE", "FAILED"),
        (
            deploy("deactivated"),
            [{"deploy": deploy("deactivated")}],
            "INDETERMINATE",
            "FAILED",
        ),
    ),
    ids=("superseded", "inactive", "unexpected-status", "unfiltered-live-list"),
)
def test_final_active_check_requires_d_to_stay_live(
    harness: Harness,
    final: dict[str, object],
    live: list[object],
    state: str,
    overall: str,
) -> None:
    """#409 AC10: success needs D still live at declaration."""
    harness.render.final = final
    harness.render.live = live

    assert harness.module.main() == 1

    receipt = harness.receipt_json()
    assert receipt["final_active_state"] == state
    assert receipt["overall_outcome"] == overall


class _Response(io.BytesIO):
    status = 201

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_render_transport_sends_the_key_only_as_a_bearer_header(
    promote: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """#409 AC9 SECURITY: the key never reaches a URL, a body, or an error."""
    requests: list[urllib.request.Request] = []

    class Opener:
        def __init__(self, result: object) -> None:
            self.result = result

        def open(self, request: urllib.request.Request, **_: object) -> object:
            requests.append(request)
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

    def success_opener(*_: object) -> Opener:
        return Opener(_Response(b'{"id": "dep-d0x"}'))

    monkeypatch.setattr(urllib.request, "build_opener", success_opener)
    assert promote._render(API_KEY, "POST", "/services/x/deploys", {"a": 1}) == (
        201,
        {"id": "dep-d0x"},
    )
    request = requests[0]
    assert request.full_url == "https://api.render.com/v1/services/x/deploys"
    assert request.get_header("Authorization") == f"Bearer {API_KEY}"
    assert API_KEY not in request.full_url + cast(bytes, request.data).decode()

    error = urllib.error.HTTPError(
        "https://api.render.com", 401, f"denied {API_KEY}", Message(), None
    )

    def failing_opener(*_: object) -> Opener:
        return Opener(error)

    monkeypatch.setattr(urllib.request, "build_opener", failing_opener)
    with pytest.raises(ValueError) as caught:
        promote._render(API_KEY, "GET", "/owners?limit=100")
    assert str(caught.value) == "render request failed"


@pytest.mark.parametrize(
    ("tty", "typed"),
    (
        (False, API_KEY),
        (True, "bad key"),
        (True, "bad\r\nInjected: header"),
        (True, ""),
        (True, None),
    ),
    ids=("no-terminal", "whitespace", "control-characters", "empty", "echo-fallback"),
)
def test_key_prompt_requires_a_terminal_and_a_render_key(
    promote: ModuleType, monkeypatch: MonkeyPatch, tty: bool, typed: str | None
) -> None:
    """#409 AC9: the key comes only from a hidden prompt on a terminal."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty, raising=False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: tty, raising=False)

    def getpass(*_: object, **__: object) -> str:
        if typed is None:
            warnings.warn("echo", promote.getpass.GetPassWarning, stacklevel=1)
            return API_KEY
        return typed

    monkeypatch.setattr(promote.getpass, "getpass", getpass)

    with pytest.raises(ValueError):
        promote._prompt_key()


def test_key_prompt_accepts_any_printable_key_format(
    promote: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """#409 AC9: Render decides whether a key works. The prompt checks no prefix."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)

    def getpass(*_: object, **__: object) -> str:
        return "rsk_scoped-key.Format_1"

    monkeypatch.setattr(promote.getpass, "getpass", getpass)

    assert promote._prompt_key() == "rsk_scoped-key.Format_1"
