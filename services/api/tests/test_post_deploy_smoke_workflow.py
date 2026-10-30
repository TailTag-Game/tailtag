"""Post-deploy HTTP smoke workflow contract."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

from tests.process_support import skip_on_windows

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "post-deploy-smoke.yml"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

PROJECT = "a1111111-1111-4111-8111-111111111111"
DEVELOPMENT = "22222222-2222-4222-8222-222222222222"
STAGING = "33333333-3333-4333-8333-333333333333"
OLD_PROJECT = "66666666-6666-4666-8666-666666666666"
SOURCE_SHA = "a" * 40
PRIVATE_EVENT_VALUE = "private-event-payload-must-not-appear"


@pytest.fixture
def delivery_event() -> ModuleType:
    return importlib.import_module("scripts.api_development_delivery_event")


def generation_digest(project: str, environment: str) -> str:
    return hashlib.sha256(
        f"tailtag-rebuild-event-v1\0development\0{project}\0{environment}".encode()
    ).hexdigest()


def railway_link(project: str = PROJECT, environment: str = DEVELOPMENT) -> str:
    return f"https://railway.com/project/{project}?environmentId={environment}"


def development_event() -> dict[str, object]:
    return {
        "deployment": {
            "id": 123,
            "environment": "TailTag / development",
            "creator": {"login": "railway-app[bot]"},
            "sha": SOURCE_SHA,
            "ref": SOURCE_SHA,
            "payload": {"environmentId": DEVELOPMENT},
        },
        "deployment_status": {
            "id": 456,
            "state": "success",
            "environment": "TailTag / development",
            "creator": {"login": "railway-app[bot]"},
            "target_url": railway_link(),
            "environment_url": railway_link(),
        },
    }


def install_event_pin(delivery_event: ModuleType, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        delivery_event,
        "_EXPECTED_GENERATION_DIGEST",
        generation_digest(PROJECT, DEVELOPMENT),
    )


def event_field(event: dict[str, object], field: str, value: object) -> None:
    cursor: dict[str, object] = event
    names = field.split(".")
    for name in names[:-1]:
        cursor = cursor[name]  # type: ignore[assignment]
    cursor[names[-1]] = value


def step_script(workflow: str, name: str) -> str:
    """Return the Bash script from one uniquely named workflow step."""
    step = re.search(
        rf"^      - name: {re.escape(name)}\n(?P<contents>.*?)(?=^      - name:|^  \w+:|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert step, f"workflow must define the {name!r} step"

    marker = "        run: |\n"
    assert marker in step.group("contents"), f"workflow step {name!r} must run Bash"
    return textwrap.dedent(step.group("contents").split(marker, maxsplit=1)[1])


def run_classifier(
    tmp_path: Path, *, event_name: str, deployment_sha: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Execute the classifier with controlled GitHub event values."""
    output = tmp_path / "github-output"
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "deployment": {
                    "environment": "TailTag / development",
                    "creator": {"login": "railway-app[bot]"},
                    "sha": deployment_sha,
                    "ref": deployment_sha,
                },
                "deployment_status": {"state": "success"},
            }
        )
    )
    workflow = WORKFLOW.read_text()
    completed = subprocess.run(
        ["bash", "-c", step_script(workflow, "Classify the trigger")],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "EVENT_NAME": event_name,
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_SHA": "workflow-revision",
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    values = (
        dict(line.split("=", maxsplit=1) for line in output.read_text().splitlines())
        if output.exists()
        else {}
    )
    return completed, values


def test_development_event_fingerprint_uses_reviewed_generation_framing(
    delivery_event: ModuleType,
) -> None:
    """D-3: the event pin commits to both canonical replacement UUIDs."""
    assert delivery_event.fingerprint_development_generation(
        PROJECT, DEVELOPMENT
    ) == generation_digest(PROJECT, DEVELOPMENT)
    assert delivery_event.fingerprint_development_generation(
        OLD_PROJECT, DEVELOPMENT
    ) != generation_digest(PROJECT, DEVELOPMENT)
    assert delivery_event.fingerprint_development_generation(
        PROJECT, STAGING
    ) != generation_digest(PROJECT, DEVELOPMENT)


@pytest.mark.parametrize(
    ("project", "environment"),
    (
        (PROJECT.upper(), DEVELOPMENT),
        (PROJECT, "not-a-uuid"),
        (PROJECT, "abcdefab-cdef-4abc-8abc-abcdefabcdef".upper()),
    ),
)
def test_development_event_fingerprint_rejects_noncanonical_ids(
    delivery_event: ModuleType, project: str, environment: str
) -> None:
    """D-3: uppercase or malformed IDs cannot match the code-owned pin."""
    with pytest.raises(ValueError):
        delivery_event.fingerprint_development_generation(project, environment)


def test_matching_replacement_event_returns_only_canonical_source_sha(
    delivery_event: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """D-3: a complete reviewed Railway event is eligible for public verification."""
    install_event_pin(delivery_event, monkeypatch)
    assert (
        delivery_event.classify_development_deployment_event(development_event())
        == SOURCE_SHA
    )


def test_matching_replacement_event_allows_main_ref(
    delivery_event: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """A branch ref remains eligible when all pinned bindings also match."""
    install_event_pin(delivery_event, monkeypatch)
    event = development_event()
    event_field(event, "deployment.ref", "main")
    assert delivery_event.classify_development_deployment_event(event) == SOURCE_SHA


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("deployment.environment", "TailTag Rebuild / development"),
        ("deployment.creator.login", "someone-else"),
        ("deployment_status.creator.login", "someone-else"),
        ("deployment_status.environment", "TailTag Rebuild / development"),
        ("deployment.ref", "feature"),
        ("deployment.sha", "A" * 40),
        ("deployment.sha", "a" * 39),
        ("deployment.sha", None),
        ("deployment.payload", {}),
        ("deployment.payload.environmentId", STAGING),
        ("deployment_status.state", "failure"),
        ("deployment_status.environment_url", railway_link(OLD_PROJECT)),
        ("deployment_status.target_url", railway_link(PROJECT, STAGING)),
        ("deployment_status.target_url", "http://" + railway_link()[8:]),
        ("deployment_status.target_url", railway_link() + "&extra=1"),
        (
            "deployment_status.target_url",
            railway_link() + f"&environmentId={DEVELOPMENT}",
        ),
        ("deployment_status.target_url", railway_link() + "#fragment"),
        ("deployment_status.target_url", railway_link() + "#"),
        ("deployment_status.target_url", " " + railway_link()),
        ("deployment_status.target_url", "\x1f" + railway_link()),
        (
            "deployment_status.target_url",
            railway_link().replace("railway.com", "railway.\tcom"),
        ),
        (
            "deployment_status.target_url",
            railway_link().replace("railway.com", "railway.\rcom"),
        ),
        ("deployment_status.target_url", "HTTPS://" + railway_link()[8:]),
        (
            "deployment_status.target_url",
            railway_link().replace("railway.com", "railway.com:443"),
        ),
        (
            "deployment_status.target_url",
            railway_link().replace("railway.com", "user@railway.com"),
        ),
        (
            "deployment_status.target_url",
            railway_link().replace("/project/", "/other/"),
        ),
        ("deployment_status.target_url", None),
        ("deployment_status.environment_url", None),
    ),
    ids=(
        "wrong-label",
        "wrong-creator",
        "wrong-status-creator",
        "wrong-status-label",
        "wrong-ref",
        "uppercase-sha",
        "short-sha",
        "missing-sha",
        "missing-payload-binding",
        "payload-link-mismatch",
        "non-success-status",
        "environment-link-project-mismatch",
        "status-link-environment-mismatch",
        "insecure-link",
        "extra-query",
        "duplicate-environment-query",
        "link-fragment",
        "empty-fragment",
        "leading-space",
        "leading-c0",
        "embedded-tab",
        "embedded-carriage-return",
        "uppercase-scheme",
        "link-port",
        "link-userinfo",
        "wrong-link-path",
        "missing-target-link",
        "missing-environment-link",
    ),
)
def test_development_event_rejects_ineligible_or_inconsistent_status(
    delivery_event: ModuleType,
    monkeypatch: MonkeyPatch,
    field: str,
    value: object,
) -> None:
    """D-3: label/SHA matches cannot override missing or mismatched bindings."""
    install_event_pin(delivery_event, monkeypatch)
    event = development_event()
    event_field(event, field, value)
    assert delivery_event.classify_development_deployment_event(event) is None


@pytest.mark.parametrize(
    ("project", "environment"),
    ((OLD_PROJECT, DEVELOPMENT), (PROJECT, STAGING)),
    ids=("old-project", "staging-environment"),
)
def test_development_event_rejects_coherent_other_generation(
    delivery_event: ModuleType,
    monkeypatch: MonkeyPatch,
    project: str,
    environment: str,
) -> None:
    """D-3: internally consistent old-generation events still fail the code pin."""
    install_event_pin(delivery_event, monkeypatch)
    event = development_event()
    event_field(event, "deployment.payload.environmentId", environment)
    event_field(
        event, "deployment_status.target_url", railway_link(project, environment)
    )
    event_field(
        event, "deployment_status.environment_url", railway_link(project, environment)
    )
    assert delivery_event.classify_development_deployment_event(event) is None


def test_development_event_skip_and_cli_do_not_emit_raw_event_values(
    delivery_event: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """D-3: malformed provider data yields only a safe skip classification."""
    install_event_pin(delivery_event, monkeypatch)
    event = development_event()
    event_field(event, "deployment_status.target_url", PRIVATE_EVENT_VALUE)
    assert delivery_event.classify_development_deployment_event(event) is None
    assert capsys.readouterr() == ("", "")

    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github-output"))
    assert delivery_event.main() == 0
    captured = capsys.readouterr()
    assert "skip" in captured.out.lower()
    assert PRIVATE_EVENT_VALUE not in captured.out + captured.err
    assert SOURCE_SHA not in captured.out + captured.err


def test_workflow_classifies_file_event_before_source_checkout_or_smoke() -> None:
    """D-3/D-4: workflow consumes the pinned event result before public checks."""
    workflow = WORKFLOW.read_text()
    classify = step_script(workflow, "Classify the trigger")
    assert "python -m scripts.api_development_delivery_event" in classify
    assert workflow.index("actions/checkout@") < workflow.index(
        "python -m scripts.api_development_delivery_event"
    )
    assert workflow.index("python -m scripts.api_development_delivery_event") < (
        workflow.index("--development-candidate")
    )
    assert workflow.index("--development-candidate") < workflow.index(
        "Check out verifier revision"
    )
    assert workflow.index("Check out verifier revision") < workflow.index(
        "Run canonical HTTP smoke verification"
    )
    assert "--render-development-current" in workflow


@skip_on_windows("Runs the workflow's bash step, which only runs on Linux runners.")
def test_display_label_and_sha_alone_cannot_trigger_attributed_smoke(
    tmp_path: Path,
) -> None:
    """D-3: the superseded display-only filter cannot authorize a deployment."""
    completed, values = run_classifier(
        tmp_path, event_name="deployment_status", deployment_sha=SOURCE_SHA
    )

    assert completed.returncode == 0, completed.stderr
    assert values.get("should_verify") == "false"
    assert values.get("checkout_ref") == ""


@skip_on_windows("Runs the workflow's bash step, which only runs on Linux runners.")
def test_manual_dispatch_does_not_label_the_workflow_revision_as_a_deployment(
    tmp_path: Path,
) -> None:
    """Manual smoke checks use the workflow revision only to check out tooling."""
    completed, values = run_classifier(
        tmp_path, event_name="workflow_dispatch", deployment_sha="ignored-event-sha"
    )

    assert completed.returncode == 0, completed.stderr
    assert values["should_verify"] == "true"
    assert values["checkout_ref"] == "workflow-revision"
    assert values["deployment_id"] == "manual"
    assert values["deployment_status_id"] == "manual"
    assert values["deployment_sha"] == "not-applicable"
    assert values["deployment_ref"] == "not-applicable"
    assert values["target"] == "render"


def test_missing_api_url_fails_development_preflight_before_smoke(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-4: missing configured origin fails the manual preflight CLI offline."""
    workflow = WORKFLOW.read_text()
    smoke = step_script(workflow, "Run canonical HTTP smoke verification")

    preflight = importlib.import_module("scripts.api_staging_preflight")
    monkeypatch.delenv("TAILTAG_DEVELOPMENT_API_BASE_URL", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["api_staging_preflight.py", "--development-current"]
    )

    def unexpected_fetch(_: str) -> NoReturn:
        raise AssertionError("missing Development origin reached HTTP transport")

    monkeypatch.setattr(preflight, "_fetch_json", unexpected_fetch)
    assert preflight.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "development preflight unavailable" in captured.err.lower()
    assert "TAILTAG_DEVELOPMENT_API_BASE_URL" in workflow
    assert workflow.index("--development-candidate") < workflow.index(
        "Run canonical HTTP smoke verification"
    )
    assert 'API_BASE_URL="$API_BASE_URL" task api-smoke' in smoke


def test_post_deploy_smoke_workflow_uses_the_approved_contract() -> None:
    """The workflow retains its triggers, filters, bounds, and least privilege."""
    workflow = WORKFLOW.read_text()

    for required in (
        "deployment_status:",
        "workflow_dispatch:",
        "python -m scripts.api_development_delivery_event",
        "python -m scripts.api_staging_preflight --development-candidate",
        "python -m scripts.api_staging_preflight --render-development-candidate",
        "python -m scripts.api_staging_preflight --render-development-current",
        "timeout-minutes: 10",
        "persist-credentials: false",
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
        "astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78",
    ):
        assert required in workflow

    for forbidden in (
        "railway up",
        "railway deploy",
        "railway run",
        "railway login",
        "task api-check",
        "manage.py migrate",
        "postgres:",
    ):
        assert forbidden not in workflow.lower()


RENDER_SERVICE = "srv-d0development00000000"
RENDER_HOST = "tailtag-api-development.onrender.com"
RENDER_APP = {"id": 14658, "slug": "render"}


def render_target(service: str = RENDER_SERVICE) -> str:
    return f"https://dashboard.render.com/web/{service}/deploys/dep-d0deploy0000000000"


def render_event() -> dict[str, object]:
    return {
        "deployment": {
            "id": 789,
            "environment": "main - tailtag-api-development",
            "creator": {"login": "maintainer"},
            "performed_via_github_app": dict(RENDER_APP),
            "sha": SOURCE_SHA,
            "ref": "main",
            "payload": {},
        },
        "deployment_status": {
            "id": 790,
            "state": "success",
            "environment": "main - tailtag-api-development",
            "creator": {"login": "maintainer"},
            "performed_via_github_app": dict(RENDER_APP),
            "target_url": render_target(),
            "environment_url": f"https://{RENDER_HOST}",
        },
    }


@pytest.fixture
def render_pins(monkeypatch: MonkeyPatch) -> None:
    binding = importlib.import_module("config.replacement_target_binding")
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            "development": binding.fingerprint_render_service(
                "development", RENDER_SERVICE
            )
        },
    )
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_HOST_DIGESTS",
        {
            "development": binding.fingerprint_render_hostname(
                "development", RENDER_HOST
            )
        },
    )


def test_pinned_render_event_returns_only_its_source_sha(
    delivery_event: ModuleType, render_pins: None
) -> None:
    """#408 AC11: a Render App deploy of the pinned service is eligible."""
    assert (
        delivery_event.classify_render_development_deployment_event(render_event())
        == SOURCE_SHA
    )
    assert delivery_event.classify_development_deployment_event(render_event()) is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("deployment.performed_via_github_app", None),
        (
            "deployment_status.performed_via_github_app",
            {"id": 15368, "slug": "github-actions"},
        ),
        ("deployment_status.performed_via_github_app.id", "14658"),
        ("deployment.environment", "main - tailtag-api-staging"),
        ("deployment_status.environment", "feature - tailtag-api-development"),
        ("deployment.ref", "feature"),
        ("deployment.payload", {"serviceId": RENDER_SERVICE}),
        ("deployment.sha", "A" * 40),
        ("deployment_status.state", "failure"),
        ("deployment_status.target_url", render_target("srv-d0other000000000000")),
        ("deployment_status.target_url", render_target() + "?x=1"),
        ("deployment_status.target_url", "http" + render_target()[5:]),
        (
            "deployment_status.environment_url",
            "https://tailtag-api-staging.onrender.com",
        ),
        ("deployment_status.environment_url", f"https://{RENDER_HOST}/"),
        ("deployment_status.environment_url", None),
    ),
    ids=(
        "deployment-not-render-app",
        "status-other-app",
        "string-app-id",
        "staging-label",
        "branch-label",
        "branch-ref",
        "unexpected-payload",
        "uppercase-sha",
        "failed-status",
        "unpinned-service",
        "target-query",
        "insecure-target",
        "unpinned-host",
        "host-with-path",
        "missing-host",
    ),
)
def test_render_event_rejects_unbound_or_unsuccessful_deploys(
    delivery_event: ModuleType, render_pins: None, field: str, value: object
) -> None:
    """#408 AC11: only the Render App identity and both pins authorize smoke."""
    event = render_event()
    event_field(event, field, value)
    assert delivery_event.classify_render_development_deployment_event(event) is None


def test_classifier_cli_names_the_host_of_each_eligible_event(
    delivery_event: ModuleType,
    render_pins: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """#408 AC11/AC12: the workflow learns which pinned origin to verify."""
    install_event_pin(delivery_event, monkeypatch)
    for event, target in ((development_event(), "railway"), (render_event(), "render")):
        path = tmp_path / f"{target}.json"
        output = tmp_path / f"{target}-output"
        path.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        assert delivery_event.main() == 0
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["target"] == target
        assert values["deployment_sha"] == SOURCE_SHA


def test_railway_job_never_reads_the_render_repository_variable() -> None:
    """#408 AC7/AC12: only Render events and manual runs use the variable."""
    workflow = WORKFLOW.read_text()
    selector = (
        "${{ needs.classify.outputs.target == 'railway' && 'https://dev.tailtag.app'"
        " || vars.TAILTAG_DEVELOPMENT_API_BASE_URL }}"
    )
    assert workflow.count("vars.TAILTAG_DEVELOPMENT_API_BASE_URL") == 2
    assert workflow.count(selector) == 2
    check = step_script(workflow, "Check pinned public Development identity")
    assert (
        "railway/event)\n    python -m scripts.api_staging_preflight --development-candidate"
        in check
    )
    assert (
        "render/event)\n    python -m scripts.api_staging_preflight --render-development-candidate"
        in check
    )
    assert (
        "render/manual)\n    python -m scripts.api_staging_preflight --render-development-current"
        in check
    )
