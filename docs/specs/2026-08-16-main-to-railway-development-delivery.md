# Main-to-Railway development delivery

Issue: [#78](https://github.com/TailTag-Game/tailtag/issues/78)

## Goal

Establish an enforceable normal-contributor delivery path from a protected,
reviewed backend pull request through a successful `main` validation to the
shared Railway development API, its controlled migration step, readiness check,
and post-deploy HTTP smoke verification.

## Delivery invariant

A normal backend deployment to the shared Railway development environment must
originate from a commit on `main` that passed the repository's enforced
pull-request/review gate. Railway must not promote a backend deployment when
the applicable post-merge CI for that commit fails.

This is a compositional guarantee:

1. GitHub protects `main` with pull requests, one approval, resolved review
   conversations, squash merges, and the required `API foundation checks`
   status check.
2. Railway's development `api` service deploys only from `main`.
3. Railway's native Wait for CI behavior waits for the push-to-`main`
   validation before deploying.

Railway does not inspect pull-request reviews; GitHub protections remain the
authority for that part of the invariant.

## GitHub Actions

The existing `.github/workflows/api.yml` workflow remains the only backend
validation workflow. It must trigger for pull requests and pushes to `main`
while retaining the stable `API foundation checks` job name.

Both event paths use the same `make api-check` command. Pull requests retain
the existing authoritative relevance classifier:

- a backend-relevant change runs the full PostgreSQL-backed validation suite;
- an irrelevant change completes the same stable job through its explicit
  success/skip path.

For pushes to `main`, the existing non-pull-request force-run behavior
validates the exact commit Railway is considering. The change must not create a
second workflow or duplicate validation commands.

The active `Protect main` ruleset must require `API foundation checks` in
addition to its current pull-request, one-approval, review-conversation, and
squash-merge requirements. The check name must not change.

## Railway delivery

The existing Railway `TailTag / development` `api` service remains connected
to `TailTag-Game/tailtag` on `main`, with normal GitHub autodeploy enabled.
Enable Railway's native Wait for CI/check-suite behavior when the live service
integration supports it.

Use runtime/deployment relevance rather than the broader CI relevance contract.
The minimum Railway watch path is:

\`\`\`text
services/api/**
\`\`\`

Only add a root or shared path when the live Railway build/runtime configuration
directly consumes it. In particular, do not redeploy the API solely for changes
to `Makefile`, `scripts/api_smoke.py`, `.github/workflows/api.yml`,
documentation, or frontend code.

The existing pre-deploy migration command and `/health/ready` Railway health
check remain unchanged. The existing post-deploy `deployment_status` smoke
workflow remains independent: it verifies the shared endpoint only after
Railway reports a successful deployment; it does not deploy, migrate, or
control Railway.

## Failure model

| Failure | Expected control | Primary surface |
| --- | --- | --- |
| Pre-merge backend CI | PR cannot normally merge | GitHub `API foundation checks` |
| Missing review or unresolved conversation | PR cannot normally merge | GitHub ruleset / PR merge requirements |
| Post-merge backend CI | Railway candidate is held then skipped; no promotion | GitHub Actions and observed Railway Wait for CI state |
| Migration | Candidate fails before application promotion | Railway pre-deploy deployment log/status |
| Build, deploy, or readiness | Candidate fails in Railway | Railway deployment state/logs |
| HTTP smoke | Railway deployment succeeded but broader API verification failed | #77 post-deploy smoke workflow |

This issue adds no automatic rollback behavior.

## Privileged bypass boundary

The repository-owner pull-request bypass is retained as an exceptional,
auditable administrative/recovery override. It is outside the normal contributor
delivery path and must not be used for routine development, delivery, or the
#78/#80 validation. GitHub history must make any exceptional use visible.

The guarantee is therefore about normal contributors: they cannot make Railway
development delivery bypass required pull-request CI and review. This design
does not claim that a deliberately privileged administrator can never override
repository protections.

## Revision attribution

Stage 1 uses infrastructure metadata, not a new API version endpoint:

\`\`\`text
merged main SHA
  = push workflow SHA
  = Railway Git-triggered deployment commit metadata
  = Railway GitHub deployment event SHA used by the #77 verifier
\`\`\`

`RAILWAY_GIT_COMMIT_SHA`, Railway deployment records, and the GitHub
`deployment_status` event provide the relevant correlation where exposed.
The smoke result proves the stable shared endpoint satisfied the smoke contract
after the successful deployment; it does not cryptographically bind each HTTP
response to that SHA. If a later deployment supersedes the candidate before
smoke runs, record the limitation rather than adding application versioning.

## Verification

Before closing #78, inspect and record:

- the active GitHub ruleset, including its required check, preserved review
  rules, and documented bypass actor;
- pull-request and push-to-`main` API workflow behavior, job name, relevance
  behavior, and shared `make api-check` contract;
- Railway source branch, autodeploy, Wait for CI, watch paths, migration
  setting, readiness path, and #77 deployment-status integration;
- a real, sanitized deployment correlation from `main` SHA through Railway
  deployment metadata and the smoke verifier result where practical.

#80 performs the final controlled end-to-end proof. #78 establishes the
configuration and evidence path needed for it.

