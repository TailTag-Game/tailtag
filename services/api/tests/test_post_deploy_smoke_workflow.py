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
            "environment": "TailTag Rebuild / development",
            "creator": {"login": "railway-app[bot]"},
            "sha": SOURCE_SHA,
            "ref": "main",
            "payload": {"environmentId": DEVELOPMENT},
        },
        "deployment_status": {
            "id": 456,
            "state": "success",
            "environment": "TailTag Rebuild / development",
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
                    "environment": "TailTag Rebuild / development",
                    "creator": {"login": "railway-app[bot]"},
                    "sha": deployment_sha,
                    "ref": "main",
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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("deployment.environment", "TailTag / development"),
        ("deployment.creator.login", "someone-else"),
        ("deployment_status.creator.login", "someone-else"),
        ("deployment_status.environment", "TailTag / development"),
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
    assert "--development-current" in workflow


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
    assert 'API_BASE_URL="$API_BASE_URL" make api-smoke' in smoke


def test_post_deploy_smoke_workflow_uses_the_approved_contract() -> None:
    """The workflow retains its triggers, filters, bounds, and least privilege."""
    workflow = WORKFLOW.read_text()

    for required in (
        "deployment_status:",
        "workflow_dispatch:",
        "python -m scripts.api_development_delivery_event",
        "python -m scripts.api_staging_preflight --development-candidate",
        "--development-current",
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
        "make api-check",
        "manage.py migrate",
        "postgres:",
    ):
        assert forbidden not in workflow.lower()
