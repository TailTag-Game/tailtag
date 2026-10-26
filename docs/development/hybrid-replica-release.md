# Hybrid replica release runbook

This runbook releases the TailTag API to the hybrid replica with GitHub Actions. The hybrid replica is an isolated copy of Staging on Cloud Run, Neon and Cloudflare R2. The work item is [#356](https://github.com/TailTag-Game/tailtag/issues/356). The parent is [#352](https://github.com/TailTag-Game/tailtag/issues/352).

[ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) stays in force. This runbook does not approve a hosting move. Provisioning is in [the provisioning runbook](hybrid-replica-provisioning.md).

## Boundaries

- The workflow changes only the replica. It holds no Railway credential, and it never calls Railway.
- Only the owner starts a release, and only the owner approves it.
- Every live step needs owner authorization. This includes the Terraform apply, the environment setup and each workflow run.
- Never retry a failed release step by hand. Read the receipt first, then decide.
- Actions logs on this repository are public. Never print a project ID, project number, host or credential in a workflow step.

## Parts

| Part | Purpose |
| --- | --- |
| `.github/workflows/replica-release.yml` | Workflow that releases a `main` SHA or recovers a recorded revision |
| `scripts/api_replica_release.py` | Release logic: eligibility, release, recover and jobs sync |
| `task replica-release` | Runs the release script. The workflow calls it. |
| `task replica-jobs-sync` | Owner command that moves the five other jobs to a released digest |
| `docs/development/replica-deployments/` | Committed release receipts |

A receipt is a sanitized JSON record of one run. A candidate is the new revision that a release tests before it takes traffic.

## Field ownership

Terraform and the release never write the same field.

| Field | Owner |
| --- | --- |
| Service and job shape, env, secrets, probes, scaling, ingress and invoker setting | Terraform |
| Capacity profile | Terraform (`capacity_profile`, #360) |
| Service image, revision name, client, traffic and traffic tags | Release workflow |
| Migrate job image | Release workflow |
| Image of the other five jobs | Owner, with `task replica-jobs-sync` |
| IAM, federation and the registry | Terraform |

## One-time setup

Do these steps once, in order. Each step needs owner authorization.

1. Apply the foundation root from the owner workstation, as in [the provisioning runbook](hybrid-replica-provisioning.md). Make sure that the plan shows only these changes:
   - an in-place update of the federation provider condition
   - a replaced deployer federation binding
   - one new job IAM member on `tailtag-replica-migrate`
   - one new `actAs` member on `tt-migrator`
   - an in-place update of the Artifact Registry repository for immutable tags
   - an in-place update of `DJANGO_ALLOWED_HOSTS` on the service and the five production jobs
2. Make sure that `/health/ready` still answers 200 on the service host after the apply.
3. In the repository settings, create the environment `replica`:
   - Deployment branches: `main` only.
   - Required reviewer: the owner. Allow the reviewer to approve their own runs.
4. Add these environment secrets to `replica`. Take each value from the owner-private setup record.

   | Secret | Value |
   | --- | --- |
   | `REPLICA_PROJECT_ID` | Replica GCP project ID |
   | `REPLICA_PROJECT_NUMBER` | Replica project number |
   | `REPLICA_WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github` |
   | `REPLICA_DEPLOYER_EMAIL` | `tt-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |

5. Make sure that the environment has no other secret or variable.

GitHub masks environment secrets in logs. That is why the project ID and number are secrets and not variables.

## Run a release

1. Merge the change to `main`. Make sure that the `TailTag API` workflow passed for the merge commit.
2. In Actions, open `TailTag replica release` and select `Run workflow` on `main`. Use these inputs:
   - `mode`: `release`
   - `source_sha`: empty for the head of `main`, or a full `main` SHA
   - `fault`: `none`
3. The `eligibility` job runs first. It makes sure that the SHA is on `main` and that its `api.yml` push run passed.
4. Approve the `release` job in the `replica` environment.
5. The release job does these steps in order:
   1. It reads the Artifact Registry tag for the SHA. If the tag is missing, it builds `linux/amd64` and pushes. Tags are immutable, so one SHA has one digest.
   2. It makes sure that one revision has 100% of traffic and that no `candidate` tag exists.
   3. It points the migrate job at the digest and runs it once.
   4. It deploys a candidate revision with no traffic and the tag `candidate`.
   5. It runs four gates on the candidate tag host: `/health/live`, `/health/ready`, `/health/identity` and an anonymous `/api/me/` that must return 401.
   6. It moves 100% of traffic to the candidate, removes the tag, and makes sure that the service host identity names the candidate.
6. Read the receipt in the job summary.
7. Download the receipt artifact. Save it as `docs/development/replica-deployments/<candidate_revision>.json` and commit it in a docs PR.
8. Before the next reset, pool, fixture or inspect run, sync the other jobs from the owner workstation:

   ```sh
   task replica-jobs-sync -- --project <PROJECT_ID> --receipt docs/development/replica-deployments/<candidate_revision>.json
   ```

   The reset preflight refuses a job whose SHA differs from the service.

## Outcomes

Every run ends with one outcome. Only `PROMOTED` moves traffic for good.

| Outcome | Meaning | What to do |
| --- | --- | --- |
| `PROMOTED` | The candidate passed every gate and serves 100% | Commit the receipt. Sync the jobs. |
| `FAIL_INPUT` | An input was refused before any cloud call | Fix the input and start a new run |
| `FAIL_BUILD` | The build, push or digest lookup failed | Read the build step. Nothing changed on Cloud Run. |
| `FAIL_PRECHECK` | Traffic was split, a `candidate` tag existed or the target revision changed | Inspect the service. Remove a stale tag only after you know where it came from. |
| `FAIL_MIGRATION` | The migrate job failed | The service did not change. Read the job logs, then forward-fix. |
| `FAIL_MIGRATION_UNKNOWN` | The migrate job update or run got no clear answer | Check the job executions before any new run |
| `FAIL_CANDIDATE` | A gate failed. The previous revision serves 100% and the tag is gone. | Read the gate results. Diagnose the failed revision, then delete it. |
| `FAIL_RELEASE_UNKNOWN` | A service update got no clear answer, and the revision does not exist | Inspect the service. Start a new run only after the state is clear. |
| `FAIL_CONCURRENT_RELEASE` | Someone else changed the service during the run | Stop. Find the other change. Nothing was retried. |
| `FAIL_CLEANUP_UNKNOWN` | The restore after a failed gate got no clear answer | Inspect the traffic at once. Restore it as below. |
| `FAIL_PROMOTION_UNKNOWN` | The promotion update got no clear answer | Inspect the traffic and the service host identity |
| `FAIL_PROMOTION_UNVERIFIED` | The service host did not show the candidate, so traffic went back | Inspect the service. The previous revision serves. |
| `FAIL_UNKNOWN` | An unexpected error | Inspect the service and the receipt before any new run |

### Inspect and restore by hand

Run these commands only from the owner workstation, never in a workflow step.

```sh
gcloud run services describe tailtag-api-replica --project=<PROJECT_ID> --region=us-east4 --format='yaml(spec.traffic,status.traffic)'
gcloud run services update-traffic tailtag-api-replica --project=<PROJECT_ID> --region=us-east4 --to-revisions=<PREVIOUS_REVISION>=100 --remove-tags=candidate
```

To delete a failed revision after you read its logs:

```sh
gcloud run revisions delete <FAILED_REVISION> --project=<PROJECT_ID> --region=us-east4
```

A failed revision is kept on purpose, so that you can diagnose it. It has no traffic and no tag, so it does not start.

## Run a failure drill

A drill proves that a failed release leaves the previous revision serving. Each drill needs owner authorization.

1. Start the workflow with `mode` `release` and `fault` set to one of these values:
   - `migrate`: the migrate job runs with arguments that exit non-zero
   - `candidate`: the candidate container command is `false`, so the candidate never starts
2. Approve the run.
3. Make sure that the outcome is `FAIL_MIGRATION` or `FAIL_CANDIDATE`, and that `drill` is `true` in the receipt.
4. Make sure that the service host identity still names the previous revision.
5. For the `candidate` drill, delete the failed revision as above.

The workflow refuses `fault` unless a person started the run.

## Recover a revision

Recovery moves traffic back to a revision that a release promoted before. It does no build and no migration. It never reverses a migration. Follow the [#206 rollback contract](../specs/2026-09-22-v0-migration-application-rollback.md).

1. Make sure that the target revision has a committed `PROMOTED` receipt in `docs/development/replica-deployments/`.
2. Record a compatibility review on GitHub. It must show that the target code works with the current schema and data. If compatibility is uncertain, forward-fix instead.
3. Start the workflow with these inputs:
   - `mode`: `recover`
   - `revision`: the target revision name
   - `compatibility_ref`: the link to the review
4. Approve the run. The release job checks that the revision image still has the receipt digest. It tags the revision `candidate`, runs the same four gates and then moves traffic.
5. Commit the new receipt as for a release.

## Prove the privacy and Railway boundaries

Do these checks after the first live release.

1. Download the run log archive. Search it for the project ID, the project number and the service host. Make sure that no match exists.
2. Make sure that the repository and the organization have no Actions secrets, and that `replica` holds only the four secrets above.
3. Read Railway Staging `/health/identity` before and after a release. Make sure that the deployment is the same.
4. Make sure that the release script refuses a target that is not the pinned replica host. The offline tests cover this.

## What never to do

- Never run the workflow from a branch other than `main`.
- Never add a Railway token, a Clerk key or any secret value beyond the four above to the `replica` environment.
- Never change traffic in the console while a run is active.
- Never rerun a failed job without reading its receipt.
- Never delete a persistent resource. Gate G-4 applies.
