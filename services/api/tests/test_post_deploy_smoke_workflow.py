"""Post-deploy HTTP smoke workflow contract."""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "post-deploy-smoke.yml"


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
    workflow = WORKFLOW.read_text()
    completed = subprocess.run(
        ["bash", "-c", step_script(workflow, "Classify the trigger")],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "EVENT_NAME": event_name,
            "DEPLOYMENT_STATE": "success",
            "DEPLOYMENT_ENVIRONMENT": "TailTag / development",
            "DEPLOYMENT_CREATOR": "railway-app[bot]",
            "DEPLOYMENT_ID": "123",
            "DEPLOYMENT_STATUS_ID": "456",
            "DEPLOYMENT_SHA": deployment_sha,
            "DEPLOYMENT_REF": "main",
            "GITHUB_SHA": "workflow-revision",
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    values = dict(
        line.split("=", maxsplit=1) for line in output.read_text().splitlines()
    )
    return completed, values


def test_accepted_railway_deployment_checks_out_the_deployment_sha(
    tmp_path: Path,
) -> None:
    """A matching Railway event uses its deployment SHA as the checkout revision."""
    _, values = run_classifier(
        tmp_path, event_name="deployment_status", deployment_sha="deployment-revision"
    )

    assert values["should_verify"] == "true"
    assert values["checkout_ref"] == "deployment-revision"
    assert values["deployment_sha"] == "deployment-revision"


def test_manual_dispatch_does_not_label_the_workflow_revision_as_a_deployment(
    tmp_path: Path,
) -> None:
    """Manual smoke checks use the workflow revision only to check out tooling."""
    _, values = run_classifier(
        tmp_path, event_name="workflow_dispatch", deployment_sha="ignored-event-sha"
    )

    assert values["should_verify"] == "true"
    assert values["checkout_ref"] == "workflow-revision"
    assert values["deployment_id"] == "manual"
    assert values["deployment_status_id"] == "manual"
    assert values["deployment_sha"] == "not-applicable"
    assert values["deployment_ref"] == "not-applicable"


def test_missing_api_url_fails_before_the_smoke_step(tmp_path: Path) -> None:
    """A missing API URL stops verification before the canonical smoke command."""
    workflow = WORKFLOW.read_text()
    reporting = step_script(workflow, "Report verification context")
    smoke = step_script(workflow, "Run canonical HTTP smoke verification")
    completed = subprocess.run(
        ["bash", "-c", reporting],
        cwd=tmp_path,
        env={
            **os.environ,
            "DEPLOYMENT_ID": "123",
            "DEPLOYMENT_STATUS_ID": "456",
            "DEPLOYMENT_SHA": "deployment-revision",
            "DEPLOYMENT_REF": "main",
            "DEPLOYMENT_ENVIRONMENT": "TailTag / development",
            "API_BASE_URL": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Missing development API URL" in completed.stdout
    assert "make api-smoke" not in reporting
    assert 'API_BASE_URL="$API_BASE_URL" make api-smoke' in smoke
    assert workflow.index("Report verification context") < workflow.index(
        "Run canonical HTTP smoke verification"
    )


def test_post_deploy_smoke_workflow_uses_the_approved_contract() -> None:
    """The workflow retains its triggers, filters, bounds, and least privilege."""
    workflow = WORKFLOW.read_text()

    for required in (
        "deployment_status:",
        "workflow_dispatch:",
        "DEPLOYMENT_STATE: ${{ github.event.deployment_status.state }}",
        "DEPLOYMENT_ENVIRONMENT: ${{ github.event.deployment.environment }}",
        "DEPLOYMENT_CREATOR: ${{ github.event.deployment.creator.login }}",
        '"$DEPLOYMENT_STATE" != "success"',
        '"$DEPLOYMENT_ENVIRONMENT" != "TailTag / development"',
        '"$DEPLOYMENT_CREATOR" != "railway-app[bot]"',
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
