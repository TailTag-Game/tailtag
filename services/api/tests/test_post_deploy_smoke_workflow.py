"""Post-deploy HTTP smoke workflow contract."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "post-deploy-smoke.yml"


def test_post_deploy_smoke_workflow_uses_the_approved_contract() -> None:
    """The verifier accepts only the observed Railway event shape and smoke command."""
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
        "github.event.deployment.sha",
        "Skipping post-deploy smoke:",
        "TAILTAG_DEVELOPMENT_API_BASE_URL",
        'API_BASE_URL="$API_BASE_URL" make api-smoke',
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
