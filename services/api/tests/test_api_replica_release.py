"""Offline acceptance contract for the replica release script (#356 U2).

Cloud Run, Artifact Registry, the candidate and service hosts, and gcloud and
docker are faked at `urllib.request.OpenerDirector.open` and `subprocess.run`.
The fake keeps service, revision, job and tag state, so each test checks what
the release leaves serving, not only which calls it made.
"""

from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self, cast

import pytest

from tests import replica_contract as contract

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

PROJECT = "synthetic-replica-project"
PROJECT_NUMBER = "424242424242"
REGION = "us-east4"
SERVICE = "tailtag-api-replica"
HOST = f"{SERVICE}-{PROJECT_NUMBER}.{REGION}.run.app"
CANDIDATE_HOST = f"candidate---{HOST}"
TOKEN = "synthetic-bearer-token-value"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
OLD_SHA = "fedcba9876543210fedcba9876543210fedcba98"
DIGEST = "sha256:" + "a" * 64
BUILT_DIGEST = "sha256:" + "b" * 64
OLD_DIGEST = "sha256:" + "c" * 64
IMAGE = f"{REGION}-docker.pkg.dev/{PROJECT}/tailtag-api/api"
PREVIOUS = f"{SERVICE}-00007-sd9"
# Cloud Run names the revision. The fake names it from the generation it creates.
CANDIDATE = f"{SERVICE}-00006-new"
RELEASE_LABEL = {"tailtag-release": "r123456a1"}
RUN_BASE = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}"
SERVICE_PATH = f"projects/{PROJECT}/locations/{REGION}/services/{SERVICE}"
TAG_URL = (
    f"https://artifactregistry.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}"
    "/repositories/tailtag-api/packages/api/tags/"
)
REVISION_TYPE = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
JOBS = (
    "tailtag-replica-migrate",
    "tailtag-replica-reset",
    "tailtag-replica-fixture",
    "tailtag-replica-pool",
    "tailtag-replica-inspect",
    "tailtag-replica-registry-reconcile",
)
EXECUTION = "tailtag-replica-migrate-x7k2p"
# Cloud Run sends proto3 JSON: a false `reconciling` is omitted, and a condition
# carries more keys than its state.
READY_CONDITION = {
    "type": "Ready",
    "state": "CONDITION_SUCCEEDED",
    "lastTransitionTime": "2026-10-25T00:00:00Z",
}
PRIVATE = (PROJECT, PROJECT_NUMBER, HOST, TOKEN, "googleapis", "pkg.dev")


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "fake", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]


def _without_name(template: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in template.items() if key != "revision"}


class FakeGcp:
    """One replica project: a service with revisions, six jobs and registry tags."""

    def __init__(self) -> None:
        self.clock = 0.0
        self.requests: list[dict[str, Any]] = []
        self.subprocess_calls: list[list[str]] = []
        self.tags = {SOURCE_SHA: DIGEST}
        self.digest_sha = {
            DIGEST: SOURCE_SHA,
            BUILT_DIGEST: SOURCE_SHA,
            OLD_DIGEST: OLD_SHA,
        }
        self.generation = 5
        self.template: dict[str, Any] = {
            "revision": PREVIOUS,
            "serviceAccount": "tt-runtime",
            "containers": [
                {"image": f"{IMAGE}@{OLD_DIGEST}", "ports": [{"containerPort": 8000}]}
            ],
        }
        self.traffic: list[dict[str, Any]] = [
            {"type": REVISION_TYPE, "revision": PREVIOUS, "percent": 100}
        ]
        self.revisions: dict[str, dict[str, Any]] = {
            PREVIOUS: {"image": f"{IMAGE}@{OLD_DIGEST}", "starts": True}
        }
        self.latest_created = PREVIOUS
        self.jobs: dict[str, dict[str, Any]] = {
            name: {"generation": 2, "image": f"{IMAGE}@{OLD_DIGEST}"} for name in JOBS
        }
        self.execution_succeeds = True
        self.run_lost = False
        self.patch_lost: str | None = None
        self.foreign_update: str | None = None
        self.shared_identity: dict[str, Any] | None = None
        self.gate: dict[str, dict[str, Any]] = {}

    # --- HTTP boundary -------------------------------------------------
    def open(self, request: urllib.request.Request, *_: object, **__: object) -> Any:
        url = request.full_url
        method = request.get_method()
        body = json.loads(cast(bytes, request.data)) if request.data else None
        self.requests.append({"method": method, "url": url, "body": body})
        if url.startswith(TAG_URL):
            return self._tag(url)
        if url.startswith(f"{RUN_BASE}/services/{SERVICE}"):
            return self.service_route(url, method, body)
        if url.startswith(f"{RUN_BASE}/jobs/"):
            return self._job(url, method, body)
        if url.startswith((f"https://{CANDIDATE_HOST}/", f"https://{HOST}/")):
            return self._gate(url)
        raise AssertionError(f"unexpected request: {method} {url}")

    @staticmethod
    def _json(value: Any) -> FakeResponse:
        return FakeResponse(json.dumps(value).encode())

    def _tag(self, url: str) -> FakeResponse:
        sha = url.removeprefix(TAG_URL)
        if sha not in self.tags:
            raise _http_error(url, 404)
        version = f"projects/{PROJECT}/locations/{REGION}/repositories/tailtag-api/packages/api/versions/{self.tags[sha]}"
        return self._json({"name": url, "version": version})

    def service(self) -> dict[str, Any]:
        return {
            "name": SERVICE_PATH,
            "generation": str(self.generation),
            "etag": f'"e{self.generation}"',
            "invokerIamDisabled": True,
            "latestCreatedRevision": f"{SERVICE_PATH}/revisions/{self.latest_created}",
            "terminalCondition": READY_CONDITION,
            "template": copy.deepcopy(self.template),
            "traffic": copy.deepcopy(self.traffic),
            "trafficStatuses": copy.deepcopy(self.traffic),
        }

    def service_route(self, url: str, method: str, body: Any) -> FakeResponse:
        base = f"{RUN_BASE}/services/{SERVICE}"
        if url.startswith(f"{base}/revisions/"):
            name = url.removeprefix(f"{base}/revisions/")
            if name not in self.revisions:
                raise _http_error(url, 404)
            return self._json(
                {
                    "name": f"{SERVICE_PATH}/revisions/{name}",
                    "labels": self.revisions[name].get("labels", {}),
                    "containers": [{"image": self.revisions[name]["image"]}],
                }
            )
        if url != base:
            raise AssertionError(url)
        if method == "GET":
            return self._json(self.service())
        assert method == "PATCH"
        assert body["invokerIamDisabled"] is True, (
            "the release must send the full service"
        )
        if self.patch_lost == "before":
            raise urllib.error.URLError("lost")
        if self.patch_lost == "refused":
            raise _http_error(url, 403)
        if self.foreign_update in {"revision", "setting"}:
            self.generation += 1
        if self.foreign_update == "revision":
            self.add_foreign_revision()
        # Like Cloud Run: a changed template makes a revision, named by the body
        # or by the service. Reusing a name for another configuration is a 409.
        name = body["template"].get("revision")
        changed = _without_name(body["template"]) != _without_name(self.template)
        if name in self.revisions and changed:
            raise _http_error(url, 409)
        if changed or (name and name not in self.revisions):
            name = name or f"{SERVICE}-{self.generation + 1:05d}-new"
            container = body["template"]["containers"][0]
            self.revisions[name] = {
                "image": container["image"],
                "labels": dict(body["template"].get("labels", {})),
                "starts": container.get("command") != ["false"],
            }
            if self.foreign_update != "revision":
                self.latest_created = name
            if self.foreign_update == "latest":
                self.add_foreign_revision()
            if self.foreign_update == "twin":
                self.add_foreign_revision(container["image"])
            if self.foreign_update == "image":
                self.revisions[name]["image"] = f"{IMAGE}@{OLD_DIGEST}"
        self.template = copy.deepcopy(body["template"])
        self.traffic = copy.deepcopy(body["traffic"])
        self.generation += 1
        if self.patch_lost == "after":
            raise urllib.error.URLError("lost")
        if self.patch_lost == "unavailable":
            raise _http_error(url, 503)
        return self._json({"name": "operations/fake"})

    def add_foreign_revision(self, image: str = f"{IMAGE}@{OLD_DIGEST}") -> None:
        """Someone else's revision: no release label, and by default another image."""
        self.revisions[f"{SERVICE}-foreign"] = {
            "image": image,
            "labels": {},
            "starts": True,
        }
        self.latest_created = f"{SERVICE}-foreign"

    def _job(self, url: str, method: str, body: Any) -> FakeResponse:
        rest = url.removeprefix(f"{RUN_BASE}/jobs/")
        if "/executions/" in rest:
            succeeded = self.execution_succeeds and self._last_run_args is None
            return self._json(
                {
                    "completionTime": "2026-10-25T00:00:00Z",
                    "succeededCount": 1 if succeeded else 0,
                    "failedCount": 0 if succeeded else 1,
                }
            )
        if rest.endswith(":run"):
            name = rest.removesuffix(":run")
            assert method == "POST" and name == "tailtag-replica-migrate"
            if self.run_lost:
                raise urllib.error.URLError("lost")
            container = body["overrides"]["containerOverrides"][0]
            self._last_run_args = container.get("args")
            path = f"projects/{PROJECT}/locations/{REGION}/jobs/{name}/executions/{EXECUTION}"
            return self._json({"metadata": {"name": path}})
        job = self.jobs[rest]
        if method == "PATCH":
            image = body["template"]["template"]["containers"][0]["image"]
            # Like Cloud Run: an update that changes nothing keeps the generation.
            if image != job["image"]:
                job["image"] = image
                job["generation"] += 1
            return self._json({"name": "operations/fake"})
        return self._json(
            {
                "name": f"projects/{PROJECT}/locations/{REGION}/jobs/{rest}",
                "generation": str(job["generation"]),
                "terminalCondition": READY_CONDITION,
                "template": {
                    "template": {
                        "containers": [{"image": job["image"], "command": ["python"]}]
                    }
                },
            }
        )

    _last_run_args: Any = None

    def _gate(self, url: str) -> FakeResponse:
        candidate = url.startswith(f"https://{CANDIDATE_HOST}/")
        path = url.split(".run.app", 1)[1]
        wanted = [
            t["revision"]
            for t in self.traffic
            if (t.get("tag") == "candidate" if candidate else t.get("percent") == 100)
        ]
        if not wanted:
            raise _http_error(url, 404)
        revision = wanted[0]
        state = self.revisions[revision]
        if not state["starts"]:
            raise _http_error(url, 503)
        sha = self.digest_sha[state["image"].split("@", 1)[1]]
        overrides = self.gate.get(revision, {})
        defaults: dict[str, tuple[int, Any]] = {
            "/health/live": (200, {"status": "ok"}),
            "/health/ready": (200, {"status": "ok"}),
            "/health/identity": (
                200,
                {
                    "source_sha": sha,
                    "deployment_id": revision,
                    "environment": "replica",
                },
            ),
            "/api/me/": (
                401,
                {"detail": "Authentication credentials were not provided."},
            ),
        }
        status, payload = overrides.get(path, defaults[path])
        if not candidate and path == "/health/identity" and self.shared_identity:
            status, payload = 200, self.shared_identity
        if status >= 400:
            raise _http_error(url, status)
        return self._json(payload)

    # --- subprocess boundary ------------------------------------------
    def run(
        self, args: Sequence[str], *_: object, **__: object
    ) -> subprocess.CompletedProcess[str]:
        argv = list(args)
        self.subprocess_calls.append(argv)
        if argv[:3] == ["gcloud", "auth", "print-access-token"]:
            return subprocess.CompletedProcess(argv, 0, f"{TOKEN}\n", "")
        if argv[:2] == ["git", "-C"] and argv[3:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, f"{SOURCE_SHA}\n", "")
        if argv[:3] == ["docker", "buildx", "build"]:
            self.tags[SOURCE_SHA] = BUILT_DIGEST
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"unexpected subprocess: {argv}")

    # --- views ---------------------------------------------------------
    def serving(self) -> list[tuple[str, int, str | None]]:
        return [
            (t["revision"], t.get("percent", 0), t.get("tag")) for t in self.traffic
        ]

    def service_patches(self) -> list[dict[str, Any]]:
        return [
            r["body"]
            for r in self.requests
            if r["method"] == "PATCH" and r["url"] == f"{RUN_BASE}/services/{SERVICE}"
        ]

    def runs(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["url"].endswith(":run")]


@pytest.fixture
def release() -> Any:
    import importlib

    return importlib.import_module("scripts.api_replica_release")


@pytest.fixture
def gcp(monkeypatch: pytest.MonkeyPatch) -> FakeGcp:
    fake = FakeGcp()

    def opener_open(
        _opener: object, request: urllib.request.Request, *_: object, **__: object
    ) -> Any:
        return fake.open(request)

    def which(name: str, *_: object, **__: object) -> str:
        return name

    contract.install_replica_pins(monkeypatch)
    from config import replica_binding

    monkeypatch.setattr(
        replica_binding, "_EXPECTED_HOST_DIGEST", contract.host_digest(HOST)
    )
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        opener_open,
    )
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(shutil, "which", which)

    def sleep(seconds: float) -> None:
        fake.clock += max(seconds, 0.001)
        assert fake.clock < 24 * 3600, "release never gives up"

    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(time, "monotonic", lambda: fake.clock)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    return fake


def run_main(module: Any, argv: Sequence[str]) -> tuple[int, dict[str, Any], str]:
    out, err = io.StringIO(), io.StringIO()
    real = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = module.main(list(argv))
    finally:
        sys.stdout, sys.stderr = real
    text = out.getvalue() + err.getvalue()
    for value in PRIVATE:
        assert value not in text, f"private value printed: {value}"
    lines = out.getvalue().splitlines()
    assert len(lines) == 1 and err.getvalue() == ""
    return code, json.loads(lines[0]), text


def release_argv(tmp_path: Path, fault: str = "none", **overrides: str) -> list[str]:
    values = {
        "--project": PROJECT,
        "--project-number": PROJECT_NUMBER,
        "--source-sha": SOURCE_SHA,
        "--source-dir": str(tmp_path / "source"),
        "--ci-run": "991",
        "--run-id": "123456",
        "--run-number": "7",
        "--run-attempt": "1",
        "--fault": fault,
        "--receipt": str(tmp_path / "receipt.json"),
        **overrides,
    }
    return ["release", *[part for pair in values.items() for part in pair]]


def receipt(tmp_path: Path) -> dict[str, Any]:
    text = (tmp_path / "receipt.json").read_text()
    for value in PRIVATE:
        assert value not in text, f"private value in receipt: {value}"
    return json.loads(text)


# --- AC1, AC4, AC5, AC11: the order of a passing release ----------------


@pytest.mark.parametrize(
    "tag_exists", (True, False), ids=("reuse-image", "build-image")
)
def test_release_promotes_only_after_the_candidate_passes_every_gate(
    release: Any, gcp: FakeGcp, tmp_path: Path, tag_exists: bool
) -> None:
    if not tag_exists:
        del gcp.tags[SOURCE_SHA]
    digest = DIGEST if tag_exists else BUILT_DIGEST

    code, line, _ = run_main(release, release_argv(tmp_path))

    assert (code, line["result"]) == (0, "PROMOTED")
    builds = [c for c in gcp.subprocess_calls if c[:2] == ["docker", "buildx"]]
    if tag_exists:
        assert builds == []
    else:
        (build,) = builds
        assert {"--platform", "linux/amd64", "--push"} <= set(build)
        assert f"TAILTAG_SOURCE_SHA={SOURCE_SHA}" in build
        assert f"{IMAGE}:{SOURCE_SHA}" in build
    assert gcp.jobs["tailtag-replica-migrate"]["image"] == f"{IMAGE}@{digest}"
    assert all(gcp.jobs[name]["image"] == f"{IMAGE}@{OLD_DIGEST}" for name in JOBS[1:])
    assert [
        r["body"]["overrides"]["containerOverrides"][0].get("args") for r in gcp.runs()
    ] == [None]

    deploy, tag, promote = gcp.service_patches()
    assert "revision" not in deploy["template"], "Cloud Run names every revision"
    assert deploy["template"]["labels"] == RELEASE_LABEL
    assert deploy["template"]["containers"][0]["image"] == f"{IMAGE}@{digest}"
    assert [t["revision"] for t in deploy["traffic"]] == [PREVIOUS]
    assert [
        (t["revision"], t.get("percent", 0), t.get("tag")) for t in tag["traffic"]
    ] == [(PREVIOUS, 100, None), (CANDIDATE, 0, "candidate")]
    order = [r["url"] for r in gcp.requests]
    first_promotion = next(
        i
        for i, r in enumerate(gcp.requests)
        if r["method"] == "PATCH" and r["body"] is promote
    )
    gate_paths = [
        u for u in order[:first_promotion] if u.startswith(f"https://{CANDIDATE_HOST}")
    ]
    assert [u.removeprefix(f"https://{CANDIDATE_HOST}") for u in gate_paths][-4:] == [
        "/health/live",
        "/health/ready",
        "/health/identity",
        "/api/me/",
    ]
    migrate_run = next(i for i, u in enumerate(order) if u.endswith(":run"))
    first_deploy = next(i for i, r in enumerate(gcp.requests) if r["body"] is deploy)
    assert migrate_run < first_deploy
    assert gcp.serving() == [(CANDIDATE, 100, None)]
    # Terraform can still change the template later: no explicit name is left.
    assert "revision" not in gcp.template

    recorded = receipt(tmp_path)
    assert recorded | {"started_at": None, "finished_at": None} == {
        "schema": "tailtag-replica-release-v1",
        "mode": "release",
        "fault": "none",
        "drill": False,
        "source_sha": SOURCE_SHA,
        "image_digest": digest,
        "ci_run_id": 991,
        "workflow_run": {"id": 123456, "number": 7, "attempt": 1},
        "previous_revision": PREVIOUS,
        "candidate_revision": CANDIDATE,
        "compatibility_ref": None,
        "migration": {"outcome": "PASS", "execution": EXECUTION},
        "gates": {
            "live": "PASS",
            "ready": "PASS",
            "identity": "PASS",
            "anonymous_auth": "PASS",
        },
        "serving_revision": CANDIDATE,
        "jobs": {"migrate": digest, "others": "PENDING_SYNC"},
        "outcome": "PROMOTED",
        "started_at": None,
        "finished_at": None,
    }


# --- AC6, AC16, AC20: a failed candidate never takes traffic -------------


@pytest.mark.parametrize(
    ("fault", "gate", "failed"),
    (
        ("none", {"/health/ready": (503, {"status": "unavailable"})}, "ready"),
        (
            "none",
            {
                "/health/identity": (
                    200,
                    {
                        "source_sha": SOURCE_SHA,
                        "deployment_id": PREVIOUS,
                        "environment": "replica",
                    },
                )
            },
            "identity",
        ),
        (
            "none",
            {
                "/health/identity": (
                    200,
                    {
                        "source_sha": OLD_SHA,
                        "deployment_id": CANDIDATE,
                        "environment": "replica",
                    },
                )
            },
            "identity",
        ),
        ("none", {"/api/me/": (200, {"id": "anonymous"})}, "anonymous_auth"),
        ("candidate", {}, "live"),
    ),
    ids=("not-ready", "other-revision", "other-source", "auth-bypass", "drill-startup"),
)
def test_failed_candidate_leaves_the_previous_revision_serving(
    release: Any,
    gcp: FakeGcp,
    tmp_path: Path,
    fault: str,
    gate: dict[str, Any],
    failed: str,
) -> None:
    gcp.gate[CANDIDATE] = gate

    code, line, _ = run_main(release, release_argv(tmp_path, fault=fault))

    assert (code, line["result"]) == (1, "FAIL_CANDIDATE")
    assert gcp.serving() == [(PREVIOUS, 100, None)]
    assert CANDIDATE in gcp.revisions, "the failed revision stays for diagnosis"
    deploy, _tag, cleanup = gcp.service_patches()
    if fault == "candidate":
        assert deploy["template"]["containers"][0]["command"] == ["false"]
    assert [t.get("tag") for t in cleanup["traffic"]] == [None]
    recorded = receipt(tmp_path)
    assert recorded["gates"][failed] == "FAIL"
    assert (recorded["outcome"], recorded["serving_revision"], recorded["drill"]) == (
        "FAIL_CANDIDATE",
        PREVIOUS,
        fault != "none",
    )


# --- AC4, AC16: migration failure stops before the service changes --------


@pytest.mark.parametrize(
    ("fault", "setup", "outcome"),
    (
        ("none", "fail", "FAIL_MIGRATION"),
        ("migrate", None, "FAIL_MIGRATION"),
        ("none", "lost", "FAIL_MIGRATION_UNKNOWN"),
    ),
    ids=("execution-failed", "drill", "run-response-lost"),
)
def test_migration_failure_stops_before_any_service_change(
    release: Any,
    gcp: FakeGcp,
    tmp_path: Path,
    fault: str,
    setup: str | None,
    outcome: str,
) -> None:
    gcp.execution_succeeds = setup != "fail"
    gcp.run_lost = setup == "lost"

    code, line, _ = run_main(release, release_argv(tmp_path, fault=fault))

    assert (code, line["result"]) == (1, outcome)
    assert len(gcp.runs()) == 1, "a migration run is never retried"
    if fault == "migrate":
        assert gcp.runs()[0]["body"]["overrides"]["containerOverrides"][0]["args"] != [
            "manage.py",
            "replica_migrate",
        ]
    assert gcp.service_patches() == []
    assert gcp.serving() == [(PREVIOUS, 100, None)]
    assert receipt(tmp_path)["migration"]["outcome"] == (
        "UNKNOWN" if setup == "lost" else "FAIL"
    )


# --- AC6, AC17: unexpected state stops with no blind mutation -------------


@pytest.mark.parametrize(
    ("setup", "outcome", "patches"),
    (
        ("stale-tag", "FAIL_PRECHECK", 0),
        ("split", "FAIL_PRECHECK", 0),
        ("foreign-revision", "FAIL_CONCURRENT_RELEASE", 1),
        ("foreign-setting", "FAIL_CONCURRENT_RELEASE", 1),
        ("foreign-latest", "FAIL_CONCURRENT_RELEASE", 1),
        ("foreign-image", "FAIL_CONCURRENT_RELEASE", 1),
        ("foreign-twin", "FAIL_CONCURRENT_RELEASE", 1),
    ),
)
def test_unexpected_service_state_stops_without_further_mutation(
    release: Any, gcp: FakeGcp, tmp_path: Path, setup: str, outcome: str, patches: int
) -> None:
    if setup == "stale-tag":
        gcp.traffic[0]["tag"] = "candidate"
    if setup == "split":
        gcp.traffic = [
            {"type": REVISION_TYPE, "revision": PREVIOUS, "percent": 50},
            {
                "type": REVISION_TYPE,
                "revision": "tailtag-api-replica-old",
                "percent": 50,
            },
        ]
    gcp.foreign_update = (
        setup.removeprefix("foreign-") if setup.startswith("foreign-") else None
    )

    code, line, _ = run_main(release, release_argv(tmp_path))

    assert (code, line["result"]) == (1, outcome)
    assert len(gcp.service_patches()) == patches
    if not setup.startswith("foreign-"):
        assert gcp.runs() == [], "precheck runs before the migration"
    assert not any(
        t.get("percent") == 100 and t["revision"] == CANDIDATE for t in gcp.traffic
    )


@pytest.mark.parametrize(
    ("when", "outcome"),
    (
        ("after", "PROMOTED"),
        ("unavailable", "PROMOTED"),
        ("before", "FAIL_RELEASE_UNKNOWN"),
        ("refused", "FAIL_REFUSED"),
    ),
    ids=("applied-then-lost", "applied-then-503", "lost-before-apply", "refused"),
)
def test_lost_deploy_response_is_read_once_and_never_retried(
    release: Any, gcp: FakeGcp, tmp_path: Path, when: str, outcome: str
) -> None:
    gcp.patch_lost = when
    lost_once = {"done": False}
    original = gcp.service_route

    def lose_first_patch(url: str, method: str, body: Any) -> FakeResponse:
        if method == "PATCH" and lost_once["done"]:
            gcp.patch_lost = None
        if method == "PATCH":
            lost_once["done"] = True
        return original(url, method, body)

    gcp.service_route = lose_first_patch  # type: ignore[method-assign]

    code, line, _ = run_main(release, release_argv(tmp_path))

    assert line["result"] == outcome
    patches = gcp.service_patches()
    revisions = [name for name in gcp.revisions if name != PREVIOUS]
    if outcome == "PROMOTED":
        assert len(patches) == 3, "deploy, tag and promote, with no retried deploy"
        assert revisions == [CANDIDATE] and gcp.serving() == [(CANDIDATE, 100, None)]
    else:
        assert len(patches) == 1
        assert code == 1 and gcp.serving() == [(PREVIOUS, 100, None)]


def test_release_after_a_candidate_drill_deploys_a_clean_candidate(
    release: Any, gcp: FakeGcp, tmp_path: Path
) -> None:
    """A drill's failing command must not stay in the template for the next release."""
    drill, _, _ = run_main(release, release_argv(tmp_path, fault="candidate"))
    code, line, _ = run_main(release, release_argv(tmp_path, **{"--run-number": "8"}))

    assert drill == 1
    assert (code, line["result"]) == (0, "PROMOTED")
    clean = receipt(tmp_path)["serving_revision"]
    assert gcp.revisions[clean]["starts"] and gcp.serving() == [(clean, 100, None)]
    assert "command" not in gcp.template["containers"][0]


def test_rerun_of_the_same_sha_after_a_failed_gate_gets_its_own_revision(
    release: Any, gcp: FakeGcp, tmp_path: Path
) -> None:
    """The run label changes the template, so Cloud Run makes a new revision."""
    gcp.gate[CANDIDATE] = {"/health/ready": (503, {"status": "unavailable"})}
    failed, _, _ = run_main(release, release_argv(tmp_path))
    code, line, _ = run_main(release, release_argv(tmp_path, **{"--run-id": "123457"}))

    assert failed == 1
    assert (code, line["result"]) == (0, "PROMOTED")
    rerun = receipt(tmp_path)["serving_revision"]
    assert rerun != CANDIDATE
    assert gcp.revisions[rerun]["labels"] == {"tailtag-release": "r123457a1"}


def test_promotion_the_service_host_does_not_show_goes_back_once(
    release: Any, gcp: FakeGcp, tmp_path: Path
) -> None:
    gcp.shared_identity = {
        "source_sha": OLD_SHA,
        "deployment_id": PREVIOUS,
        "environment": "replica",
    }

    code, line, _ = run_main(release, release_argv(tmp_path))

    assert (code, line["result"]) == (1, "FAIL_PROMOTION_UNVERIFIED")
    assert gcp.serving() == [(PREVIOUS, 100, None)]
    assert [p["traffic"][0]["revision"] for p in gcp.service_patches()] == [
        PREVIOUS,
        PREVIOUS,
        CANDIDATE,
        PREVIOUS,
    ]
    assert receipt(tmp_path)["serving_revision"] == PREVIOUS


# --- AC12, AC16, AC24: inputs are refused before any cloud call ------------


@pytest.mark.parametrize(
    ("overrides", "event"),
    (
        ({}, "push"),
        ({"--source-sha": "0123456"}, "workflow_dispatch"),
        ({"--fault": "everything"}, "workflow_dispatch"),
    ),
    ids=("fault-on-push", "short-sha", "bad-fault"),
)
def test_bad_inputs_are_refused_before_any_cloud_call(
    release: Any,
    gcp: FakeGcp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, str],
    event: str,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    fault = overrides.pop("--fault", "migrate")

    code, line, _ = run_main(release, release_argv(tmp_path, fault=fault, **overrides))

    assert (code, line["result"]) == (1, "FAIL_INPUT")
    assert gcp.requests == [] and gcp.subprocess_calls == []


# --- AC21: recovery uses a recorded revision and its digest ---------------

TARGET = f"{SERVICE}-00005-old"


def write_receipt(directory: Path, name: str = "100-1", **overrides: Any) -> None:
    directory.mkdir(exist_ok=True)
    value = {
        "schema": "tailtag-replica-release-v1",
        "outcome": "PROMOTED",
        "candidate_revision": TARGET,
        "image_digest": OLD_DIGEST,
        "source_sha": OLD_SHA,
        **overrides,
    }
    (directory / f"{name}.json").write_text(json.dumps(value))


def recover_argv(tmp_path: Path, **overrides: str) -> list[str]:
    values = {
        "--project": PROJECT,
        "--project-number": PROJECT_NUMBER,
        "--revision": TARGET,
        "--compatibility-ref": "https://github.com/TailTag-Game/tailtag/issues/356#issuecomment-1",
        "--receipts-dir": str(tmp_path / "receipts"),
        "--run-id": "123456",
        "--run-number": "8",
        "--run-attempt": "1",
        "--receipt": str(tmp_path / "receipt.json"),
        **overrides,
    }
    return ["recover", *[part for pair in values.items() for part in pair]]


@pytest.mark.parametrize(
    ("setup", "outcome"),
    (
        ("ok", "PROMOTED"),
        ("no-receipt", "FAIL_INPUT"),
        ("failed-receipt", "FAIL_INPUT"),
        ("promoted-then-failed", "PROMOTED"),
        ("digest-changed", "FAIL_PRECHECK"),
        ("no-compatibility-ref", "FAIL_INPUT"),
    ),
)
def test_recovery_moves_traffic_only_to_a_recorded_unchanged_revision(
    release: Any, gcp: FakeGcp, tmp_path: Path, setup: str, outcome: str
) -> None:
    gcp.revisions[TARGET] = {
        "image": f"{IMAGE}@{DIGEST if setup == 'digest-changed' else OLD_DIGEST}",
        "starts": True,
    }
    if setup != "no-receipt":
        write_receipt(
            tmp_path / "receipts",
            **({"outcome": "FAIL_CANDIDATE"} if setup == "failed-receipt" else {}),
        )
    if setup == "promoted-then-failed":
        # A later failed recovery of the same revision keeps its own run file.
        write_receipt(tmp_path / "receipts", "200-1", outcome="FAIL_CANDIDATE")
    overrides = {"--compatibility-ref": ""} if setup == "no-compatibility-ref" else {}

    code, line, _ = run_main(release, recover_argv(tmp_path, **overrides))

    assert line["result"] == outcome
    assert gcp.subprocess_calls == [] or all(
        c[0] == "gcloud" for c in gcp.subprocess_calls
    )
    assert gcp.runs() == [] and all(j["generation"] == 2 for j in gcp.jobs.values())
    if outcome == "PROMOTED":
        assert code == 0 and gcp.serving() == [(TARGET, 100, None)]
        tagged, _promote = gcp.service_patches()
        assert tagged["template"] == FakeGcp().template, (
            "recovery makes no new revision"
        )
        assert ("candidate", TARGET) in [
            (t.get("tag"), t["revision"]) for t in tagged["traffic"]
        ]
        assert receipt(tmp_path)["compatibility_ref"].endswith("issuecomment-1")
    else:
        assert code == 1 and gcp.serving() == [(PREVIOUS, 100, None)]


# --- AC14: the owner moves the other five jobs to a promoted digest --------


@pytest.mark.parametrize("outcome", ("PROMOTED", "FAIL_CANDIDATE"))
def test_jobs_sync_moves_only_the_other_five_jobs_to_a_promoted_digest(
    release: Any, gcp: FakeGcp, tmp_path: Path, outcome: str
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(
            {
                "schema": "tailtag-replica-release-v1",
                "outcome": outcome,
                "image_digest": DIGEST,
                "source_sha": SOURCE_SHA,
                "candidate_revision": CANDIDATE,
            }
        )
    )

    code, line, _ = run_main(
        release, ["sync-jobs", "--project", PROJECT, "--receipt", str(path)]
    )

    synced = {name for name in JOBS if gcp.jobs[name]["image"] == f"{IMAGE}@{DIGEST}"}
    if outcome == "PROMOTED":
        assert (code, line["result"]) == (0, "PASS")
        assert synced == set(JOBS[1:])
    else:
        assert (code, line["result"]) == (1, "FAIL_INPUT")
        assert synced == set()


def job_patches(gcp: FakeGcp) -> list[str]:
    return [
        r["url"].removeprefix(f"{RUN_BASE}/jobs/")
        for r in gcp.requests
        if r["method"] == "PATCH" and r["url"].startswith(f"{RUN_BASE}/jobs/")
    ]


def test_release_migrates_when_the_job_already_runs_the_digest(
    release: Any, gcp: FakeGcp, tmp_path: Path
) -> None:
    """A rerun of a SHA finds the migrate job on its digest and still migrates."""
    gcp.jobs["tailtag-replica-migrate"]["image"] = f"{IMAGE}@{DIGEST}"

    code, line, _ = run_main(release, release_argv(tmp_path))

    assert (code, line["result"]) == (0, "PROMOTED")
    assert job_patches(gcp) == [], "an update that changes nothing is not sent"
    assert len(gcp.runs()) == 1
    assert receipt(tmp_path)["migration"]["outcome"] == "PASS"


def test_jobs_sync_is_safe_to_run_twice(
    release: Any, gcp: FakeGcp, tmp_path: Path
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(
            {
                "schema": "tailtag-replica-release-v1",
                "outcome": "PROMOTED",
                "image_digest": DIGEST,
                "source_sha": SOURCE_SHA,
                "candidate_revision": CANDIDATE,
            }
        )
    )
    argv = ["sync-jobs", "--project", PROJECT, "--receipt", str(path)]

    first, _, _ = run_main(release, argv)
    sent = len(job_patches(gcp))
    second, line, _ = run_main(release, argv)

    assert (first, second, line["result"]) == (0, 0, "PASS")
    assert sent == 5 and len(job_patches(gcp)) == 5, "the second run sends nothing"


# --- AC3, AC12: eligibility reuses the Staging rule with the Actions token --


@pytest.mark.parametrize("eligible", (True, False))
def test_eligibility_reuses_the_staging_rule_with_the_actions_token(
    release: Any, monkeypatch: pytest.MonkeyPatch, eligible: bool
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    seen: list[dict[str, Any]] = []

    def fake_open(
        _opener: object, request: urllib.request.Request, *_: object, **__: object
    ) -> Any:
        seen.append(
            {"url": request.full_url, "auth": request.get_header("Authorization")}
        )
        return FakeResponse(b'{"sha": "x"}')

    def fake_eligible(source_sha: str, fetch: Any) -> tuple[str, dict[str, object]]:
        fetch(f"/repos/TailTag-Game/tailtag/commits/{source_sha}")
        if not eligible:
            raise ValueError
        return "f" * 40, {"id": 991}

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    monkeypatch.setattr(release, "_eligible", fake_eligible)

    code, line, _ = run_main(release, ["eligibility", "--source-sha", SOURCE_SHA])

    assert seen == [
        {
            "url": f"https://api.github.com/repos/TailTag-Game/tailtag/commits/{SOURCE_SHA}",
            "auth": f"Bearer {TOKEN}",
        }
    ]
    if eligible:
        assert (code, line) == (0, {"result": "PASS", "ci_run": 991})
    else:
        assert (code, line) == (1, {"result": "FAIL_ELIGIBILITY"})
