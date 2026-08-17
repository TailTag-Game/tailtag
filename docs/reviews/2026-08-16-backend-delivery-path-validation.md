# Backend delivery path validation

Date: 2026-08-16 (validation events are recorded in UTC on 2026-08-17)

Issue: [#80](https://github.com/TailTag-Game/tailtag/issues/80)

## Scope

This review is the final Stage 1 validation of the TailTag V0 backend delivery
foundation. It consolidates durable evidence produced by issues
[#74](https://github.com/TailTag-Game/tailtag/issues/74) through
[#79](https://github.com/TailTag-Game/tailtag/issues/79) and the controlled
exercises in [#88](https://github.com/TailTag-Game/tailtag/issues/88). It does
not repeat the live delivery exercise because the existing evidence supports
every #80 acceptance criterion.

The review covers the shared, explicitly non-production Railway development
environment. It does not validate production delivery, preview environments,
Clerk, product APIs, application-level revision reporting, or automatic
rollback. No Railway configuration, deployment, migration, database, or other
runtime mutation was performed for this consolidation.

## Evidence sources

| Work | Evidence reused |
| --- | --- |
| [#74](https://github.com/TailTag-Game/tailtag/issues/74) | The stable `API foundation checks` workflow and canonical PostgreSQL-backed `make api-check` contract. |
| [#75 and #76 review](2026-08-13-railway-development-environment.md) | Railway service, PostgreSQL, runtime, readiness, pre-deploy migration, successful deployment, and controlled migration-failure evidence. |
| [#77](https://github.com/TailTag-Game/tailtag/issues/77) and its [review](2026-08-15-post-deploy-http-smoke-verification.md) | Deployment-event filtering, canonical real-HTTP smoke behavior, successful remote verification, and visible smoke failure signaling. |
| [#78 review](2026-08-16-main-to-railway-development-delivery.md) | Protected-main, Railway source/trigger, Wait for CI, watch-path, failure-surface, and revision-correlation contracts. |
| [#79](https://github.com/TailTag-Game/tailtag/issues/79) and the [operations guide](../development/backend-delivery-operations.md) | Live non-mutating walkthrough of deployment state, logs, variables, recovery controls, and maintainer diagnostic paths. |
| [#88 runtime evidence](https://github.com/TailTag-Game/tailtag/issues/88#issuecomment-5311087222) | Exact-SHA PR, merge, main CI, Railway execution, migration, readiness, deployment-status, and HTTP smoke evidence. |
| [#88 irrelevant-change evidence](https://github.com/TailTag-Game/tailtag/issues/88#issuecomment-5310605510) | Exact-SHA Railway `SKIPPED` evaluation with no executable delivery for a change outside `services/api/**`. |

## Validation revision and environment

| Item | Validated value |
| --- | --- |
| Repository | `TailTag-Game/tailtag` |
| GitHub pull request | [#91](https://github.com/TailTag-Game/tailtag/pull/91) |
| PR head SHA | `338d4b9aac1c67b6258c461e71ca95da71ae8e5a` |
| Expected deployed revision | `bf4646cb891532eff71275d487cdd7bae3ebc81b` |
| Railway workspace | `Finn the Panther's Projects` |
| Railway project / environment | `TailTag` / `development` |
| Railway service | `api`, sourced from `TailTag-Game/tailtag` on `main` with root `/services/api` |
| Railway candidate / deployment | `b45c17a9-510e-4c1b-adad-b948afa87291` |
| GitHub deployment | `5937916158`, environment `TailTag / development`, created by `railway-app[bot]` |
| Public smoke target | `https://api-development-8fa7.up.railway.app` |

## Acceptance matrix

| #80 acceptance criterion | Result | Evidence | Limitation or gap |
| --- | --- | --- | --- |
| A safe controlled validation proves backend PR CI runs and required checks pass. | **PASS** | PR #91's [API foundation checks run](https://github.com/TailTag-Game/tailtag/actions/runs/31986019974) completed successfully for head SHA `338d4b9aac1c67b6258c461e71ca95da71ae8e5a` before merge and ran the canonical API validation. | None. |
| The human review and merge workflow remains intact. | **PASS WITH LIMITATION** | The active `Protect main` ruleset, ID `19518919`, was inspected during #88 and again during this consolidation. It applies to the default branch and requires a pull request, the stable `API foundation checks`, one approving review, resolved review conversations, strict status checks, and squash merge. The [#88 runtime record](https://github.com/TailTag-Game/tailtag/issues/88#issuecomment-5311087222) records zero unresolved conversations and the squash merge. | PR #91 had no human approval and used the documented repository-owner `pull_request` administrative bypass. The exercise proves delivery mechanics, while ruleset inspection separately proves the normal-contributor governance boundary. |
| A merge to `main` triggers the intended Railway development deployment using the expected service/configuration. | **PASS** | The PR #91 squash-merge SHA `bf4646cb891532eff71275d487cdd7bae3ebc81b` became a same-SHA `main` push and Railway candidate `b45c17a9-510e-4c1b-adad-b948afa87291` for the configured `TailTag` / `development` / `api` service. The expected source, branch, root, watch path, migration command, and readiness path are recorded in the [#78 review](2026-08-16-main-to-railway-development-delivery.md). | None. |
| Migrations execute through the intended controlled mechanism and the application becomes healthy and ready. | **PASS** | #88 records successful Railway pre-deploy migration from `02:23:30.574Z` to `02:23:36.922Z`, followed by container creation, a successful Railway `/health/ready` check, and readiness promotion. The [#75/#76 review](2026-08-13-railway-development-environment.md) establishes that this is the configured pre-deploy command and is separate from Gunicorn startup. | None. |
| Post-deploy real-HTTP smoke checks pass against the deployed revision. | **PASS WITH LIMITATION** | GitHub deployment `5937916158` reported `success` for the expected SHA/ref, which triggered [post-deploy run 31987849183](https://github.com/TailTag-Game/tailtag/actions/runs/31987849183). Its classification and `Verify development API over HTTP` jobs succeeded, including the canonical HTTP smoke step. | Smoke passed after the successful deployment event for the expected SHA. The stable endpoint's HTTP response does not independently carry an application-level build identifier. |
| CI, deployment, migration, and smoke failures/logs are discoverable enough for a maintainer to diagnose. | **PASS** | The [operations guide](../development/backend-delivery-operations.md) maps each failure class to its GitHub or Railway diagnostic surface and was produced after a live non-mutating #79 walkthrough. The #75/#76 review records discoverable Railway startup and pre-deploy failures. #77 records a clearly failed [remote verifier run](https://github.com/TailTag-Game/tailtag/actions/runs/31897703004) for missing smoke configuration, while #88 demonstrates the corresponding successful CI, Railway event, and smoke surfaces. | No new failure was deliberately introduced for #80; existing controlled failures and the verified operational walkthrough satisfy this criterion. |
| The deployed revision is verified against the expected commit. | **PASS WITH LIMITATION** | The squash-merge SHA, same-SHA [main push CI](https://github.com/TailTag-Game/tailtag/actions/runs/31987790283), Railway candidate/deployment SHA, GitHub deployment SHA/ref, and [#77 verifier run](https://github.com/TailTag-Game/tailtag/actions/runs/31987849183) head SHA all match `bf4646cb891532eff71275d487cdd7bae3ebc81b`. | This is direct infrastructure-level correlation. It is not cryptographic, response-level proof that every HTTP response was generated by that SHA. |
| Durable validation evidence records actions, outcomes, limitations, and any small fixes or follow-up issues. | **PASS** | This report consolidates the Stage 1 evidence and states the observation and attribution limits without changing runtime behavior. | No functional gap or follow-up exercise was identified. |

## End-to-end delivery chain

The controlled runtime-relevant exercise followed this sequence:

| Stage | Observed evidence |
| --- | --- |
| Pull request | [PR #91](https://github.com/TailTag-Game/tailtag/pull/91), head `338d4b9aac1c67b6258c461e71ca95da71ae8e5a`. |
| PR validation | [Run 31986019974](https://github.com/TailTag-Game/tailtag/actions/runs/31986019974) completed `API foundation checks` successfully before merge. |
| Squash merge | GitHub created `bf4646cb891532eff71275d487cdd7bae3ebc81b` on `main` at `2026-08-17T02:22:34Z`. |
| Railway candidate | Candidate `b45c17a9-510e-4c1b-adad-b948afa87291` was created for the exact merge SHA at `02:22:36.502Z`. |
| Main validation | [Run 31987790283](https://github.com/TailTag-Game/tailtag/actions/runs/31987790283) validated the exact merge SHA successfully by `02:23:13Z`. |
| CI gate | The first retained Railway execution event, `SNAPSHOT_CODE`, began at `02:23:15.574Z`, after same-SHA main CI succeeded. No build or promotion activity was recorded before that result. |
| Build | Railway image build began at `02:23:16.537Z`. |
| Controlled migration | The configured pre-deploy migration ran successfully from `02:23:30.574Z` through `02:23:36.922Z`. |
| Container and readiness | Container creation succeeded from `02:23:37.027Z` through `02:23:41.266Z`; the Railway health check succeeded from `02:23:41.511Z` through `02:23:42.553Z`; network/readiness promotion completed at `02:23:44.023Z`. |
| Deployment success | Railway reported the candidate `SUCCESS`. GitHub deployment `5937916158`, created by `railway-app[bot]` for `TailTag / development` and the exact merge SHA/ref, reported `success` at `02:23:46Z`. |
| Real-HTTP smoke | The qualifying event triggered [run 31987849183](https://github.com/TailTag-Game/tailtag/actions/runs/31987849183); classification and canonical HTTP smoke against the stable development endpoint succeeded. |

The transient Railway `WAITING` label was not directly sampled, but
deployment-event timing shows the candidate was created before CI completed
and no build or deployment execution began until after the same-SHA CI
succeeded. This timing is consistent with the Wait for CI gate holding
execution until CI succeeded; neither the transient label nor a direct gate
evaluation was observed.

## Governance boundary

The runtime validation was owner-operated using the documented administrative
override. PR #91 did not receive a recorded human approval and must not be
represented as a reviewed contributor merge.

The active protected-main ruleset, ID `19518919`, was separately verified to
require normal contributors to use a pull request with:

- the stable `API foundation checks` required status check;
- one human approval;
- resolved review conversations; and
- squash merge.

The ruleset retains one repository-user `pull_request` bypass for the owner.
That exceptional, auditable administrative path is outside routine contributor
delivery. The owner-operated exercise validates delivery mechanics; the active
ruleset establishes that the human-review workflow remains intact for normal
contributors.

## Revision attribution

Infrastructure metadata supplies the Stage 1 revision boundary:

| Surface | Revision |
| --- | --- |
| PR #91 squash-merge commit | `bf4646cb891532eff71275d487cdd7bae3ebc81b` |
| Main push API workflow head | `bf4646cb891532eff71275d487cdd7bae3ebc81b` |
| Railway candidate/deployment commit and branch | `bf4646cb891532eff71275d487cdd7bae3ebc81b` on `main` |
| GitHub deployment SHA/ref | `bf4646cb891532eff71275d487cdd7bae3ebc81b` |
| Post-deploy verifier workflow head | `bf4646cb891532eff71275d487cdd7bae3ebc81b` |

Railway and GitHub deployment metadata therefore identify the deployed
revision as the expected commit, and the post-deploy smoke workflow was
triggered by the successful deployment event for that same SHA. The HTTP
response itself does not contain an application-level build identifier, so the
smoke request is not cryptographic proof that each response was generated by
that SHA. Stage 1 accepts this limitation and does not add a version endpoint,
build-information endpoint, or commit response header.

## Diagnostic discoverability

The [backend delivery operations guide](../development/backend-delivery-operations.md)
is the current maintainer entry point. It directs maintainers to:

- the PR or same-SHA main `API foundation checks` run for CI and Wait for CI;
- Railway build logs for image/build failures;
- Railway pre-deploy logs and state for migration failures;
- Railway deployment/runtime logs and the `Postgres` service for startup or
  readiness failures; and
- the qualifying `Post-deploy development smoke` Actions run for public HTTP
  verification failures.

The #79 walkthrough verified that the deployment records, build and deployment
logs, variable ownership, access model, and redeploy/rollback controls exist in
the shared environment. Earlier Stage 1 validation supplied controlled failure
evidence without requiring #80 to disrupt CI, PostgreSQL, Railway, or smoke:
the #75/#76 review records failed startup and pre-deploy attempts with visible
Railway state/logs, and #77 records a failed remote verifier with a precise
missing-configuration diagnostic.

## Report verification

The consolidation used read-only GitHub inspection of issues #74 through #80
and #88, PRs #90 through #92, ruleset `19518919`, and the cited Actions runs.
The retrieved PR, workflow, review, merge, and ruleset metadata agreed with the
existing durable Stage 1 records. Railway evidence was reused from the
sanitized #75/#76, #78, and #88 records; Railway was not mutated or re-exercised.

Repository verification for this documentation change:

- `git diff --check` — passed;
- `./scripts/doctor.sh` — passed; during pre-commit validation it reported the
  expected uncommitted-working-tree warning; and
- every relative documentation link in this report was resolved to an existing
  repository file.

## Limitations

- The transient Railway `WAITING` label was inferred from retained event timing
  rather than directly sampled. The timing is consistent with execution being
  held until same-SHA CI succeeded, but no direct gate evaluation was observed.
- Real-HTTP smoke targets the stable development endpoint after the qualifying
  deployment event. The response does not independently identify the serving
  application revision.
- The runtime exercise used the repository-owner administrative override and
  was not a human-approved contributor merge. Normal-contributor review
  requirements were established separately through the active ruleset.

## Follow-ups

No #80 acceptance criterion remains unsupported, and no new controlled
exercise is required. No small functional or documentation defect was found
during consolidation. Future work should create a follow-up issue only if new
evidence contradicts this record or the approved Stage 1 delivery contract
changes.
