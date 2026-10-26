"""Release one source SHA to the hybrid replica through exact-revision gates (#356).

The GitHub Actions replica release workflow runs `eligibility` without cloud
access, then `release` or `recover` as the deployer in the approved `replica`
environment. The owner runs `sync-jobs` locally. The approved spec is
`.refinement/356.md`.

A release resolves one image digest for the SHA, migrates with the migrate job,
deploys a no-traffic candidate revision tagged `candidate`, and tests it through
the candidate tag host. Only then does it move traffic. A mutation is never
retried: a lost response is read once, and anything unexpected stops the
release with the previous revision still serving.

Every command prints one JSON line. No project ID, project number or host is
printed or written to the receipt, because Actions logs are public (#356 G14).
"""

from __future__ import annotations

import argparse
import copy
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from scripts.api_replica_job import (
    _MAX_RESPONSE_BYTES,  # pyright: ignore[reportPrivateUsage]
    _TOKEN,  # pyright: ignore[reportPrivateUsage]
    REGION,
    Parser,
    _object,  # pyright: ignore[reportPrivateUsage]
    _opener,  # pyright: ignore[reportPrivateUsage]
    _Session,  # pyright: ignore[reportPrivateUsage]
    _start,  # pyright: ignore[reportPrivateUsage]
    _token,  # pyright: ignore[reportPrivateUsage]
    _wait,  # pyright: ignore[reportPrivateUsage]
    valid_target,
)
from scripts.api_staging_promote import (
    _eligible,  # pyright: ignore[reportPrivateUsage]
)

from config.replica_binding import (
    CANDIDATE_TAG,
    SERVICE_NAME,
    validate_candidate_host,
    validate_run_app_host,
)

SCHEMA: Final = "tailtag-replica-release-v1"
_REPOSITORY: Final = "TailTag-Game/tailtag"
_MIGRATE_JOB: Final = "tailtag-replica-migrate"
_OTHER_JOBS: Final = (
    "tailtag-replica-reset",
    "tailtag-replica-fixture",
    "tailtag-replica-pool",
    "tailtag-replica-inspect",
    "tailtag-replica-registry-reconcile",
)
_REVISION_TYPE: Final = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
# The migrate drill replaces `manage.py replica_migrate` with a non-zero exit.
_DRILL_ARGS: Final = ("-c", "raise SystemExit(3)")
_FAULTS: Final = ("none", "migrate", "candidate")
_SOURCE_SHA: Final = re.compile(r"[0-9a-f]{40}")
_PROJECT_NUMBER: Final = re.compile(r"[1-9][0-9]{0,19}")
_RUN_VALUE: Final = re.compile(r"[1-9][0-9]{0,18}")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
_REVISION: Final = re.compile(rf"{SERVICE_NAME}-[a-z0-9](?:[a-z0-9-]{{0,41}}[a-z0-9])?")
_COMPATIBILITY_REF: Final = re.compile(
    rf"https://github\.com/{_REPOSITORY}/(?:issues|pull)/[1-9][0-9]*(?:#[A-Za-z0-9_-]+)?"
)
_GATES: Final = ("live", "ready", "identity", "anonymous_auth")
_HTTP_TIMEOUT_SECONDS: Final = 30
_GATE_TIMEOUT_SECONDS: Final = 60
_RECONCILE_DEADLINE_SECONDS: Final = 600
_GATE_DEADLINE_SECONDS: Final = 180
_SHARED_HOST_DEADLINE_SECONDS: Final = 60
_BUILD_TIMEOUT_SECONDS: Final = 1_800
_POLL_SECONDS: Final = 5
_TRANSIENT_RETRIES: Final = 3


class _Stop(Exception):
    """End the release with a fixed outcome."""

    def __init__(self, outcome: str, *, cleanup: bool = False) -> None:
        super().__init__(outcome)
        self.outcome = outcome
        self.cleanup = cleanup


class _Lost(Exception):
    """A mutation got no definite answer, so it may or may not have applied."""


class _Rejected(Exception):
    """The API answered a request with an error status."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def _send(
    token: str, method: str, url: str, body: Mapping[str, object] | None
) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **({} if body is None else {"Content-Type": "application/json"}),
        },
    )
    with _opener().open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise _Rejected(response.status)
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError
    return _object(raw.decode("utf-8"))


class _Cloud:
    """Google Cloud REST calls. Reads retry transient errors; mutations never do."""

    def __init__(self) -> None:
        self._token = _token()

    def get(self, url: str, *, absent_ok: bool = False) -> dict[str, object] | None:
        return self._call("GET", url, None, absent_ok=absent_ok)

    def read(self, url: str) -> dict[str, object]:
        value = self._call("GET", url, None)
        if value is None:
            raise ValueError
        return value

    def mutate(self, method: str, url: str, body: Mapping[str, object]) -> None:
        self._call(method, url, body)

    def _call(
        self,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
        *,
        absent_ok: bool = False,
    ) -> dict[str, object] | None:
        refreshed = False
        failures = 0
        while True:
            try:
                return _send(self._token, method, url, body)
            except urllib.error.HTTPError as error:
                # A 401 is refused before any change, so one refresh is safe.
                if error.code == 401 and not refreshed:
                    refreshed = True
                    self._token = _token()
                    continue
                if error.code == 404 and absent_ok:
                    return None
                transient = error.code == 429 or error.code >= 500
                if method != "GET":
                    # A 5xx or 429 on a mutation may still have applied.
                    raise (_Lost if transient else _Rejected(error.code)) from None
                if not transient:
                    raise _Rejected(error.code) from None
            except (OSError, http.client.HTTPException):
                if method != "GET":
                    raise _Lost from None
            if failures >= _TRANSIENT_RETRIES:
                raise ValueError
            failures += 1
            time.sleep(_POLL_SECONDS)


def _probe(url: str) -> tuple[int, object]:
    """GET one public gate URL and return its status and JSON body, never raising."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with _opener().open(request, timeout=_GATE_TIMEOUT_SECONDS) as response:
            status = cast(int, response.status)
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        return status, json.loads(raw) if len(raw) <= _MAX_RESPONSE_BYTES else None
    except urllib.error.HTTPError as error:
        return error.code, None
    except (OSError, ValueError, http.client.HTTPException):
        return 0, None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _image(project: str) -> str:
    return f"{REGION}-docker.pkg.dev/{project}/tailtag-api/api"


def _run_base(project: str) -> str:
    return f"https://run.googleapis.com/v2/projects/{project}/locations/{REGION}"


def _service_url(project: str) -> str:
    return f"{_run_base(project)}/services/{SERVICE_NAME}"


def _job_url(project: str, job: str) -> str:
    return f"{_run_base(project)}/jobs/{job}"


def _generation(resource: Mapping[str, object]) -> int:
    value = resource.get("generation")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError
    return int(value)


def _last_segment(value: object, collection: str) -> str | None:
    """Return the name from a bare name or a `.../<collection>/<name>` resource name."""
    if not isinstance(value, str):
        return None
    marker = f"/{collection}/"
    return value.rsplit(marker, 1)[1] if marker in value else value


def _traffic(service: Mapping[str, object]) -> list[tuple[str, int, str | None]]:
    """Return the configured traffic as (revision, percent, tag) for named revisions."""
    raw = service.get("traffic")
    if not isinstance(raw, list):
        raise TypeError
    targets: list[tuple[str, int, str | None]] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            raise TypeError
        target = cast(dict[str, object], item)
        revision = target.get("revision")
        percent = target.get("percent", 0)
        tag = target.get("tag")
        if (
            target.get("type") != _REVISION_TYPE
            or not isinstance(revision, str)
            or type(percent) is not int
            or not (tag is None or isinstance(tag, str))
        ):
            raise _Stop("FAIL_PRECHECK")
        targets.append((revision, percent, tag or None))
    return targets


def _target(
    revision: str, percent: int = 0, tag: str | None = None
) -> dict[str, object]:
    target: dict[str, object] = {"type": _REVISION_TYPE, "revision": revision}
    if percent:
        target["percent"] = percent
    if tag is not None:
        target["tag"] = tag
    return target


class _Release:
    """One release or recovery, with the receipt it fills in as it goes."""

    def __init__(
        self, project: str, project_number: str, receipt: dict[str, object]
    ) -> None:
        self.project = project
        self.receipt = receipt
        self.host = validate_run_app_host(
            [f"{SERVICE_NAME}-{project_number}.{REGION}.run.app"]
        )
        self.candidate_host = validate_candidate_host(f"{CANDIDATE_TAG}---{self.host}")
        self.cloud = _Cloud()
        self.previous: str | None = None
        self.generation = 0

    # --- service state -------------------------------------------------
    def service(self) -> dict[str, object]:
        return self.cloud.read(_service_url(self.project))

    def precheck(self) -> dict[str, object]:
        """Require one named revision at 100% with no tag, and record it."""
        service = self.service()
        traffic = _traffic(service)
        if (
            service.get("reconciling") is True
            or len(traffic) != 1
            or traffic[0][1:] != (100, None)
            or _REVISION.fullmatch(traffic[0][0]) is None
        ):
            raise _Stop("FAIL_PRECHECK")
        self.previous = traffic[0][0]
        self.generation = _generation(service)
        self.receipt["previous_revision"] = self.previous
        self.receipt["serving_revision"] = self.previous
        return service

    def settled(self) -> dict[str, object]:
        """Poll the service until Cloud Run stops reconciling."""
        deadline = time.monotonic() + _RECONCILE_DEADLINE_SECONDS
        while True:
            service = self.service()
            # proto3 JSON omits a false `reconciling`.
            if not service.get("reconciling"):
                return service
            if time.monotonic() >= deadline:
                raise _Stop("FAIL_RELEASE_UNKNOWN")
            time.sleep(_POLL_SECONDS)

    def update(
        self,
        body: dict[str, object],
        *,
        expected: list[tuple[str, int, str | None]],
        lost: str,
    ) -> dict[str, object]:
        """Send one service update and require exactly the next generation and traffic."""
        try:
            self.cloud.mutate("PATCH", _service_url(self.project), body)
        except _Lost:
            # Read once. Only state that names this update lets the release go on.
            if _traffic(self.settled()) != expected:
                raise _Stop(lost) from None
        except _Rejected as rejected:
            raise _Stop(
                "FAIL_CONCURRENT_RELEASE"
                if rejected.code in {409, 412}
                else "FAIL_REFUSED"
            ) from None
        service = self.settled()
        if _generation(service) != self.generation + 1 or _traffic(service) != expected:
            raise _Stop("FAIL_CONCURRENT_RELEASE")
        self.generation += 1
        return service

    def fresh(self) -> dict[str, object]:
        """Return the service, stopping if anyone changed it since the last update."""
        service = self.service()
        if _generation(service) != self.generation:
            raise _Stop("FAIL_CONCURRENT_RELEASE")
        return service

    # --- gates ---------------------------------------------------------
    def gates(self, source_sha: str, revision: str) -> None:
        """Run the four candidate gates in order; the first failure stops the rest."""
        gates = cast(dict[str, str], self.receipt["gates"])
        base = f"https://{self.candidate_host}"
        checks: tuple[tuple[str, Callable[[], bool]], ...] = (
            ("live", lambda: self._until_ok(f"{base}/health/live")),
            ("ready", lambda: self._until_ok(f"{base}/health/ready")),
            ("identity", lambda: self._identity(base, source_sha, revision)),
            ("anonymous_auth", lambda: _probe(f"{base}/api/me/")[0] == 401),
        )
        for name, check in checks:
            if not check():
                gates[name] = "FAIL"
                raise _Stop("FAIL_CANDIDATE", cleanup=True)
            gates[name] = "PASS"

    @staticmethod
    def _until_ok(url: str) -> bool:
        # A request through the tag starts the candidate, so allow a cold start.
        deadline = time.monotonic() + _GATE_DEADLINE_SECONDS
        while True:
            if _probe(url) == (200, {"status": "ok"}):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(_POLL_SECONDS)

    @staticmethod
    def _identity(base: str, source_sha: str, revision: str) -> bool:
        return _probe(f"{base}/health/identity") == (
            200,
            {
                "source_sha": source_sha,
                "deployment_id": revision,
                "environment": "replica",
            },
        )

    # --- traffic moves -------------------------------------------------
    def tag(self, service: dict[str, object], revision: str) -> None:
        """Tag a revision `candidate` while the previous revision keeps 100%."""
        previous = cast(str, self.previous)
        body = {
            **service,
            "traffic": [_target(previous, 100), _target(revision, tag=CANDIDATE_TAG)],
        }
        self.update(
            body,
            expected=[(previous, 100, None), (revision, 0, CANDIDATE_TAG)],
            lost="FAIL_RELEASE_UNKNOWN",
        )

    def restore(self) -> None:
        """Send all traffic back to the previous revision and drop the tag."""
        previous = cast(str, self.previous)
        try:
            self.update(
                {**self.fresh(), "traffic": [_target(previous, 100)]},
                expected=[(previous, 100, None)],
                lost="FAIL_CLEANUP_UNKNOWN",
            )
        except _Stop as stop:
            if stop.outcome == "FAIL_CONCURRENT_RELEASE":
                raise
            raise _Stop("FAIL_CLEANUP_UNKNOWN") from None
        self.receipt["serving_revision"] = previous

    def promote(self, source_sha: str, revision: str) -> None:
        """Move 100% to the tested revision, drop the tag and prove the shared host."""
        self.update(
            {**self.fresh(), "traffic": [_target(revision, 100)]},
            expected=[(revision, 100, None)],
            lost="FAIL_PROMOTION_UNKNOWN",
        )
        self.receipt["serving_revision"] = revision
        deadline = time.monotonic() + _SHARED_HOST_DEADLINE_SECONDS
        while not self._identity(f"https://{self.host}", source_sha, revision):
            if time.monotonic() >= deadline:
                self.restore()
                raise _Stop("FAIL_PROMOTION_UNVERIFIED")
            time.sleep(_POLL_SECONDS)


# --- release steps -----------------------------------------------------


def _resolve_digest(
    cloud: _Cloud, project: str, source_sha: str, source_dir: Path
) -> str:
    """Return the registry digest of the SHA tag, building and pushing it if absent."""
    url = (
        f"https://artifactregistry.googleapis.com/v1/projects/{project}/locations/{REGION}"
        f"/repositories/tailtag-api/packages/api/tags/{source_sha}"
    )
    tag = cloud.get(url, absent_ok=True)
    if tag is None:
        _build(project, source_sha, source_dir)
        tag = cloud.get(url, absent_ok=True)
    version = None if tag is None else tag.get("version")
    digest = _last_segment(version, "versions")
    if digest is None or _DIGEST.fullmatch(digest) is None:
        raise _Stop("FAIL_BUILD")
    return digest


def _build(project: str, source_sha: str, source_dir: Path) -> None:
    git = shutil.which("git")
    docker = shutil.which("docker")
    if git is None or docker is None:
        raise _Stop("FAIL_BUILD")
    head = subprocess.run(
        [git, "-C", str(source_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=_HTTP_TIMEOUT_SECONDS,
        check=False,
    )
    if head.returncode != 0 or head.stdout.strip() != source_sha:
        raise _Stop("FAIL_BUILD")
    api = source_dir / "services" / "api"
    # Provenance off keeps the pushed digest a plain image manifest. The output is
    # captured and dropped, because it names the private registry path.
    built = subprocess.run(
        [
            docker,
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--provenance=false",
            "--build-arg",
            f"TAILTAG_SOURCE_SHA={source_sha}",
            "--label",
            f"org.opencontainers.image.revision={source_sha}",
            "--tag",
            f"{_image(project)}:{source_sha}",
            "--file",
            str(api / "Dockerfile"),
            "--push",
            str(api),
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=_BUILD_TIMEOUT_SECONDS,
        check=False,
    )
    if built.returncode != 0:
        raise _Stop("FAIL_BUILD")


def _update_job(cloud: _Cloud, project: str, job: str, image: str) -> None:
    """Point one job at the image by digest and wait for exactly that generation."""
    url = _job_url(project, job)
    current = cloud.read(url)
    generation = _generation(current)
    body = copy.deepcopy(current)
    containers = cast(
        dict[str, object], cast(dict[str, object], body["template"])["template"]
    )["containers"]
    cast(list[dict[str, object]], containers)[0]["image"] = image
    cloud.mutate("PATCH", url, body)
    deadline = time.monotonic() + _RECONCILE_DEADLINE_SECONDS
    while True:
        state = cloud.read(url)
        if not state.get("reconciling"):
            break
        if time.monotonic() >= deadline:
            raise ValueError
        time.sleep(_POLL_SECONDS)
    template = cast(
        dict[str, object], cast(dict[str, object], state["template"])["template"]
    )
    if (
        _generation(state) != generation + 1
        or cast(list[dict[str, object]], template["containers"])[0].get("image")
        != image
    ):
        raise ValueError


def _migrate(
    cloud: _Cloud,
    project: str,
    source_sha: str,
    image: str,
    fault: str,
    receipt: dict[str, object],
) -> None:
    migration = cast(dict[str, object], receipt["migration"])
    try:
        _update_job(cloud, project, _MIGRATE_JOB, image)
    except (_Lost, _Rejected, ValueError):
        migration["outcome"] = "UNKNOWN"
        raise _Stop("FAIL_MIGRATION_UNKNOWN") from None
    receipt["jobs"] = {"migrate": image.rsplit("@", 1)[1], "others": "PENDING_SYNC"}
    request = json.dumps(
        {"identity": {"source_sha": source_sha, "environment": "replica"}},
        separators=(",", ":"),
    )
    session = _Session()
    try:
        execution = _start(
            session,
            project,
            _MIGRATE_JOB,
            request,
            _DRILL_ARGS if fault == "migrate" else None,
        )
    except Exception:  # noqa: BLE001
        migration["outcome"] = "UNKNOWN"
        raise _Stop("FAIL_MIGRATION_UNKNOWN") from None
    migration["execution"] = execution
    try:
        succeeded = _wait(session, project, _MIGRATE_JOB, execution)
    except Exception:  # noqa: BLE001
        migration["outcome"] = "UNKNOWN"
        raise _Stop("FAIL_MIGRATION_UNKNOWN") from None
    migration["outcome"] = "PASS" if succeeded else "FAIL"
    if not succeeded:
        raise _Stop("FAIL_MIGRATION")


def _deploy(release: _Release, digest: str, revision: str, fault: str) -> None:
    """Create the no-traffic candidate revision with the tag, in one update."""
    service = copy.deepcopy(release.fresh())
    template = cast(dict[str, object], service["template"])
    template["revision"] = revision
    container = cast(list[dict[str, object]], template["containers"])[0]
    container["image"] = f"{_image(release.project)}@{digest}"
    if fault == "candidate":
        container["command"] = ["false"]
    else:
        # Terraform sets no command. Drop one that a drill left in the template.
        container.pop("command", None)
    release.receipt["candidate_revision"] = revision
    release.tag(service, revision)
    state = release.service()
    if _last_segment(state.get("latestCreatedRevision"), "revisions") != revision:
        raise _Stop("FAIL_CONCURRENT_RELEASE")
    created = release.cloud.read(
        f"{_service_url(release.project)}/revisions/{revision}"
    )
    images = cast(list[dict[str, object]], created.get("containers", []))
    if not images or images[0].get("image") != container["image"]:
        raise _Stop("FAIL_CONCURRENT_RELEASE")


# --- receipts and commands ----------------------------------------------


def _receipt(mode: str, fault: str, run: Mapping[str, int]) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "mode": mode,
        "fault": fault,
        "drill": fault != "none",
        "source_sha": None,
        "image_digest": None,
        "ci_run_id": None,
        "workflow_run": dict(run),
        "previous_revision": None,
        "candidate_revision": None,
        "compatibility_ref": None,
        "migration": {"outcome": "NOT_RUN", "execution": None},
        "gates": dict.fromkeys(_GATES, "NOT_RUN"),
        "serving_revision": None,
        "jobs": {"migrate": None, "others": "UNCHANGED"},
        "outcome": "PENDING",
        "started_at": _now(),
        "finished_at": None,
    }


def _finish(receipt: dict[str, object], path: Path, outcome: str) -> int:
    receipt["outcome"] = outcome
    receipt["finished_at"] = _now()
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"result": outcome}))
    return 0 if outcome == "PROMOTED" else 1


def _drive(release: _Release, body: Callable[[], None]) -> str:
    """Run the steps; on a failed candidate, restore the previous revision once."""
    try:
        body()
    except _Stop as stop:
        if stop.cleanup:
            try:
                release.restore()
            except _Stop as cleanup:
                return cleanup.outcome
        return stop.outcome
    return "PROMOTED"


def _release(arguments: argparse.Namespace) -> int:
    fault = arguments.fault
    run = _run_numbers(arguments)
    if (
        _SOURCE_SHA.fullmatch(arguments.source_sha) is None
        or _PROJECT_NUMBER.fullmatch(arguments.project_number) is None
        or _RUN_VALUE.fullmatch(arguments.ci_run) is None
        or fault not in _FAULTS
        or (
            fault != "none"
            and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        )
    ):
        raise ValueError
    valid_target(arguments.project, arguments.source_sha)
    receipt = _receipt("release", fault, run)
    receipt["source_sha"] = arguments.source_sha
    receipt["ci_run_id"] = int(arguments.ci_run)
    revision = (
        f"{SERVICE_NAME}-{arguments.source_sha[:12]}-r{run['number']}a{run['attempt']}"
    )
    if _REVISION.fullmatch(revision) is None:
        raise ValueError
    path = Path(arguments.receipt)
    try:
        release = _Release(arguments.project, arguments.project_number, receipt)
    except Exception:  # noqa: BLE001
        return _finish(receipt, path, "FAIL_UNKNOWN")

    def steps() -> None:
        digest = _resolve_digest(
            release.cloud,
            arguments.project,
            arguments.source_sha,
            Path(arguments.source_dir),
        )
        receipt["image_digest"] = digest
        release.precheck()
        _migrate(
            release.cloud,
            arguments.project,
            arguments.source_sha,
            f"{_image(arguments.project)}@{digest}",
            fault,
            receipt,
        )
        _deploy(release, digest, revision, fault)
        condition = release.service().get("terminalCondition")
        if (
            not isinstance(condition, dict)
            or cast(dict[str, object], condition).get("state") != "CONDITION_SUCCEEDED"
        ):
            raise _Stop("FAIL_CANDIDATE", cleanup=True)
        release.gates(arguments.source_sha, revision)
        release.promote(arguments.source_sha, revision)

    return _finish(receipt, path, _guarded(release, steps))


def _guarded(release: _Release, steps: Callable[[], None]) -> str:
    try:
        return _drive(release, steps)
    except Exception:  # noqa: BLE001
        return "FAIL_UNKNOWN"


def _recover(arguments: argparse.Namespace) -> int:
    run = _run_numbers(arguments)
    revision = arguments.revision
    if (
        _PROJECT_NUMBER.fullmatch(arguments.project_number) is None
        or _REVISION.fullmatch(revision) is None
        or _COMPATIBILITY_REF.fullmatch(arguments.compatibility_ref) is None
    ):
        raise ValueError
    recorded = _promoted_receipt(Path(arguments.receipts_dir) / f"{revision}.json")
    if recorded.get("candidate_revision") != revision:
        raise ValueError
    source_sha = cast(str, recorded["source_sha"])
    digest = cast(str, recorded["image_digest"])
    valid_target(arguments.project, source_sha)
    receipt = _receipt("recover", "none", run)
    receipt.update(
        source_sha=source_sha,
        image_digest=digest,
        candidate_revision=revision,
        compatibility_ref=arguments.compatibility_ref,
    )
    path = Path(arguments.receipt)
    try:
        release = _Release(arguments.project, arguments.project_number, receipt)
    except Exception:  # noqa: BLE001
        return _finish(receipt, path, "FAIL_UNKNOWN")

    def steps() -> None:
        service = release.precheck()
        if revision == release.previous:
            raise _Stop("FAIL_PRECHECK")
        target = release.cloud.read(
            f"{_service_url(arguments.project)}/revisions/{revision}"
        )
        images = cast(list[dict[str, object]], target.get("containers", []))
        if (
            not images
            or images[0].get("image") != f"{_image(arguments.project)}@{digest}"
        ):
            raise _Stop("FAIL_PRECHECK")
        release.tag(service, revision)
        release.gates(source_sha, revision)
        release.promote(source_sha, revision)

    return _finish(receipt, path, _guarded(release, steps))


def _promoted_receipt(path: Path) -> dict[str, object]:
    recorded = _object(path.read_text(encoding="utf-8"))
    digest = recorded.get("image_digest")
    source_sha = recorded.get("source_sha")
    if (
        recorded.get("schema") != SCHEMA
        or recorded.get("outcome") != "PROMOTED"
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
        or not isinstance(source_sha, str)
        or _SOURCE_SHA.fullmatch(source_sha) is None
    ):
        raise ValueError
    return recorded


def _sync_jobs(arguments: argparse.Namespace) -> int:
    recorded = _promoted_receipt(Path(arguments.receipt))
    valid_target(arguments.project, cast(str, recorded["source_sha"]))
    image = f"{_image(arguments.project)}@{recorded['image_digest']}"
    try:
        cloud = _Cloud()
        for job in _OTHER_JOBS:
            _update_job(cloud, arguments.project, job, image)
    except Exception:  # noqa: BLE001
        print(json.dumps({"result": "FAIL_SYNC"}))
        return 1
    print(json.dumps({"result": "PASS", "jobs": len(_OTHER_JOBS)}))
    return 0


def _eligibility(arguments: argparse.Namespace) -> int:
    if _SOURCE_SHA.fullmatch(arguments.source_sha) is None:
        raise ValueError
    token = os.environ.get("GITHUB_TOKEN", "")
    if _TOKEN.fullmatch(token) is None:
        raise ValueError

    def fetch(endpoint: str) -> Mapping[str, object]:
        request = urllib.request.Request(
            f"https://api.github.com{endpoint}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with _opener().open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError
        return _object(raw.decode("utf-8"))

    try:
        _, run = _eligible(arguments.source_sha, fetch)
        ci_run = run.get("id")
        if type(ci_run) is not int:
            raise ValueError
    except Exception:  # noqa: BLE001
        print(json.dumps({"result": "FAIL_ELIGIBILITY"}))
        return 1
    print(json.dumps({"result": "PASS", "ci_run": ci_run}))
    return 0


def _run_numbers(arguments: argparse.Namespace) -> dict[str, int]:
    values = (arguments.run_id, arguments.run_number, arguments.run_attempt)
    if any(_RUN_VALUE.fullmatch(value) is None for value in values):
        raise ValueError
    return {"id": int(values[0]), "number": int(values[1]), "attempt": int(values[2])}


def _parser() -> Parser:
    parser = Parser(add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    eligibility = commands.add_parser("eligibility", add_help=False)
    eligibility.add_argument("--source-sha", required=True)
    for name in ("release", "recover"):
        command = commands.add_parser(name, add_help=False)
        for option in (
            "--project",
            "--project-number",
            "--run-id",
            "--run-number",
            "--run-attempt",
            "--receipt",
        ):
            command.add_argument(option, required=True)
        if name == "release":
            for option in ("--source-sha", "--source-dir", "--ci-run", "--fault"):
                command.add_argument(option, required=True)
        else:
            for option in ("--revision", "--compatibility-ref", "--receipts-dir"):
                command.add_argument(option, required=True)
    sync = commands.add_parser("sync-jobs", add_help=False)
    sync.add_argument("--project", required=True)
    sync.add_argument("--receipt", required=True)
    return parser


_COMMANDS: Final[dict[str, Callable[[argparse.Namespace], int]]] = {
    "eligibility": _eligibility,
    "release": _release,
    "recover": _recover,
    "sync-jobs": _sync_jobs,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and print its one JSON result line."""
    try:
        arguments = _parser().parse_args(argv)
        command = _COMMANDS[arguments.command]
    except Exception:  # noqa: BLE001
        return _input_failure()
    try:
        return command(arguments)
    except (ValueError, TypeError, KeyError, OSError):
        return _input_failure()


def _input_failure() -> int:
    print(json.dumps({"result": "FAIL_INPUT"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
