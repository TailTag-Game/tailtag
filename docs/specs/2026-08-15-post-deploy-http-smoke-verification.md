# Post-deploy HTTP smoke verification

Date: 2026-08-15

## Goal

After Railway reports a successful deployment of the shared TailTag development
API to GitHub, run the established real-HTTP smoke contract and visibly fail
the GitHub Actions verification run when that contract is not satisfied.

## Scope and boundaries

Issue #77 owns the post-deploy verification control point only. It does not
start or configure a Railway deployment, run migrations, provision PostgreSQL,
run pre-merge validation, or recover from a failed verification. Those
responsibilities remain with #75, #76, #74, #78, or later operational work as
appropriate.

A smoke failure must fail the GitHub Actions job with endpoint-level output. It
must not roll back, redeploy, stop the service, revert a commit, or mutate the
database.

## Trigger and filtering

The repository will have a dedicated GitHub Actions workflow with both
`deployment_status` and `workflow_dispatch` triggers.

For `deployment_status`, the workflow must run smoke verification only for the
observed shared Railway development deployment shape:

- `github.event.deployment_status.state` is `success`;
- `github.event.deployment.environment` is exactly `TailTag / development`;
- `github.event.deployment.creator.login` is exactly `railway-app[bot]`.

These values come from observed Railway-generated GitHub deployment records.
Any event that does not satisfy every predicate is ignored with a concise,
sanitized skip reason. The workflow must not print the raw GitHub event payload.

`workflow_dispatch` is a manual operational rerun of the same smoke path. It
does not initiate a Railway deployment.

## Verification execution

`TAILTAG_DEVELOPMENT_API_BASE_URL` is a non-secret repository Actions variable
containing the public shared development API base URL. The workflow must not
use the Railway deployment-status `environment_url` as the API target: observed
events provide a Railway dashboard URL there, rather than the public API URL.
No Railway token is required or introduced.

For a relevant event, the job reports only the deployment ID, deployment-status
ID, commit SHA/ref, environment, and target API base URL. It checks out the
event deployment SHA, installs only the tooling required for the canonical
smoke command, and runs:

```text
API_BASE_URL=<shared development URL> make api-smoke
```

For a manual run, the same command and target are used. The workflow does not
provision PostgreSQL and does not invoke `make api-check`.

The existing `make api-smoke` contract remains the sole HTTP verification
definition. It checks `/health/live`, `/health/ready`, `/api/schema/`, and
`/api/docs/` against an already-running service. Its endpoint-level output
distinguishes an unreachable application from a reachable application whose
readiness check returns a failure such as PostgreSQL unavailability.

## Correlation limit

The triggering deployment event identifies the Railway deployment that caused
verification, and the smoke run establishes that the shared development endpoint
satisfied the smoke contract after that event. A request to the stable endpoint
does not by itself prove that each HTTP response was served by the event's exact
commit SHA. Issue #77 must not claim stronger revision correlation. Any need for
stronger end-to-end delivery or active-revision correlation is a #78 handoff.

## Verification requirements

- Focused tests cover the workflow trigger/filtering contract and shared smoke
  command without creating a general GitHub-event framework.
- A healthy smoke run against the real Railway development API passes through
  the Actions verifier.
- A safe failure run against an unreachable or controlled unsuitable URL exits
  non-zero and produces a failed Actions run with actionable endpoint output.
- Repository validation includes the required `./scripts/doctor.sh` and
  `git diff --check`, plus the narrowest relevant checks for the workflow and
  documentation changes.
