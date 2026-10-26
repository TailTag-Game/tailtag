# Hybrid replica delivery proof (#356)

Status: live phase complete on 2026-10-26

Related issues: [#356](https://github.com/TailTag-Game/tailtag/issues/356) (this proof), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352), runtime proof [#355](2026-10-25-hybrid-replica-runtime-proof.md), contract [#353](2026-10-22-hybrid-replica-contract.md)

Runbook: [Hybrid replica release](../development/hybrid-replica-release.md)

This document records the evidence for each #356 acceptance criterion. AC1 to AC10 come from the issue. AC11 to AC24 come from the refinement comment on #356. AC17 follows its amendment comment. Each result is PASS, PARTIAL or NOT_EXERCISED. The closing runs on 2026-10-26 and the owner evidence decision ([comment](https://github.com/TailTag-Game/tailtag/issues/356#issuecomment-6424296448)) moved AC6, AC15 and AC21 to PASS.

## Identities

| Item | Value |
| --- | --- |
| First released source | `8aacf1eb75e287fe9f7d4cbb9b19937af631ab5c` (`8aacf1e`, PR #383) |
| First released image | `sha256:f8839ff0d2cfeef666ab1c6f0d4be4bfcca76dc36029a007c3a64da32529aceb`, created 2026-10-26T17:05:14Z |
| Last released source | `c91ce58523fa0eb32c572545983401c5148c675f` (`c91ce58`, PR #385) |
| Last released image | `sha256:930503c76ccce87a87c574158729ba4bf47d411cbe533a971e649f5180d9699e`, created 2026-10-26T17:59:24Z |
| Service revisions | `tailtag-api-replica-ac7-2f951c` (from #355), then `tailtag-api-replica-00010-m2j` (first release), then `tailtag-api-replica-00012-hwf` (clean release). `00011-jjz` was the failed drill candidate. It is deleted. |
| Workflow | `.github/workflows/replica-release.yml`, `google-github-actions/auth` v3.0.0 pinned by SHA |
| Terraform | 1.17.0 with `hashicorp/google` 8.8.0 |
| UTC window | 2026-10-25 to 2026-10-26 |

This document never records project IDs, project numbers, hosts, account IDs, connection strings or tokens.

## Runs

| Run | Source | Fault | Outcome | Receipt |
| --- | --- | --- | --- | --- |
| 40364981884 | `8aacf1e` | none | `PROMOTED` to `00010-m2j` | [40364981884-1](../development/replica-deployments/40364981884-1.json) |
| 40366458002 | head of `main` (`9febaae`) | migrate | `FAIL_ELIGIBILITY`. The release job did not run. | none (no cloud step) |
| 40367025538 | `8aacf1e` | migrate | `FAIL_MIGRATION_UNKNOWN` before the drill (live finding 4) | [40367025538-1](../development/replica-deployments/40367025538-1.json) |
| 40371803158 | `8aacf1e` | migrate | `FAIL_MIGRATION` | [40371803158-1](../development/replica-deployments/40371803158-1.json) |
| 40372738151 | `8aacf1e` | candidate | `FAIL_CANDIDATE` | [40372738151-1](../development/replica-deployments/40372738151-1.json) |
| 40373525054 | `c91ce58` | none | `PROMOTED` to `00012-hwf` | [40373525054-1](../development/replica-deployments/40373525054-1.json) |
| 40376678986 | `8aacf1e` | recover | `PROMOTED` back to `00010-m2j` | [40376678986-1](../development/replica-deployments/40376678986-1.json) |
| 40377842539 | `c91ce58` | none | `PROMOTED` to `00013-kg5` | [40377842539-1](../development/replica-deployments/40377842539-1.json) |
| 40377849929 | `c91ce58` | none | `PROMOTED` to `00014-wtd`, after it waited for 40377842539 | [40377849929-1](../development/replica-deployments/40377849929-1.json) |

## Results

| AC | Result | Evidence or reason |
| --- | --- | --- |
| AC1 | PASS | Each SHA has one immutable registry tag and one digest: `8aacf1e` to `f8839ff0d2cf` and `c91ce58` to `930503c76ccc`. The first release built `8aacf1e` once. Three later runs of `8aacf1e` reused that digest with no new image. The receipts, `/health/identity` and the revision image bind source, digest and revision. No step uses a tag as proof. |
| AC2 | PASS | The workflow uses GitHub OIDC with Workload Identity Federation (WIF). The provider condition needs the repository, `refs/heads/main`, the environment `replica` and the `replica-release.yml` workflow. Infrastructure (`tf-infra`), delivery (`tt-deployer`), migration (`tt-migrator`), runtime (`tt-runtime`) and reset (`tt-maintainer`) stay separate identities. |
| AC3 | PASS | Branch protection and the required checks did not change. The eligibility job needs the SHA on `main` and a passed `api.yml` push run. Run 40366458002 was refused live with `FAIL_ELIGIBILITY` because the head of `main` had no finished CI run yet. The `replica` environment allows only `main`. |
| AC4 | PASS | The release points the migrate job at the release digest and runs it before it creates the candidate. The migrate drill (run 40371803158) failed the job execution and stopped with `FAIL_MIGRATION`. The service did not change. |
| AC5 | PASS | Before promotion, the release checks the candidate on its tag host. The checks are live, ready, identity (exact revision and SHA) and an anonymous `/api/me/` that must return 401. Both releases passed all four. The candidate drill stopped earlier, on the failed Cloud Run startup probe of the candidate. A shared endpoint or a ready flag alone never promotes. |
| AC6 | PASS | Live: both drills left the last validated revision `00010-m2j` serving at 100%, with no tag left. Live: two releases dispatched seconds apart did not overlap. Run 40377849929 stayed pending until run 40377842539 ended at 18:29:38Z, then started at 18:29:41Z. Offline tests cover lost responses, changes from outside the workflow and unclear attribution, and each stops with no retry. The owner accepted the offline evidence for those cases. |
| AC7 | PASS | Promotion moves traffic to an exact revision with an exact digest and keeps the database. Recovery (`mode=recover`) needs a committed `PROMOTED` receipt, the same digest and a #206 compatibility link. It does no build and no migration. Run 40376678986 proved the mechanism live (AC21). The full recovery proof belongs to Child 6 (#358). |
| AC8 | PASS | The release runbook has an ownership table. Terraform owns shape, env, secrets, scaling and IAM. The release owns image, run label, client, traffic and tags. Cloud Run names revisions. After the first release, the foundation plan showed `No changes` (exit 0). |
| AC9 | PASS | Five runs left receipts with source, digest, CI run, migration result, gate results, serving revision, drill flag and outcome. All five are committed (PRs #384 and #386). The runbook lists each step and who authorizes it. |
| AC10 | PASS | The repository and the organization have 0 Actions secrets. The `replica` environment has only the four replica secrets. The scripts refuse any host that is not the pinned replica host. Railway Staging `/health/identity` read `e8aedd0`, deployment `9359c0a2-4915-42cd-9994-521ce7bc740e`, before and after the first release. |
| AC11 | PASS | The candidate host is `candidate---` plus the pinned host. The API accepts no other added host (offline tests). The gates ran on that host. After each run the tag was gone, and the candidate host answered 404. |
| AC12 | PASS | The workflow starts only through `workflow_dispatch` on `main`. The owner approved each release job in the `replica` environment before migration. The environment requires that review and has admin bypass off. |
| AC13 | PASS | Policy Troubleshooter read the allow policy. The deployer can run, run with overrides and update only the migrate job. It can act only as `tt-runtime` and `tt-migrator`. 23 checks were NOT_GRANTED: the other five jobs, `actAs` on `tt-maintainer`, four secrets, and IAM changes on the service, the migrate job and the project. |
| AC14 | PASS | `task replica-jobs-sync` passed twice. After each run, all six jobs ran the release digest. The reset preflight still refuses a job with another SHA. |
| AC15 | PASS | The provider condition and the only deployer binding (`subject/repo:TailTag-Game@306886193/tailtag@1306048543:environment:replica`) read back as designed. The workflow authenticated live. No live test showed a refused token. Such a test needs a committed test workflow outside the environment. The owner accepted the readback as the evidence. |
| AC16 | PASS | The migrate drill ended `FAIL_MIGRATION`, with execution `tailtag-replica-migrate-crz5t` failed by the drill args. The candidate drill ended `FAIL_CANDIDATE`. Both receipts show `drill: true`. The workflow takes `fault` only from a person who starts it, and offline tests refuse it on other events. |
| AC17 | PASS | Amended AC17. Runs share the `replica-release` concurrency group. Each release labels its template with its run. The live generations moved by exactly one per update: 10 to 13, 13 to 16 and 16 to 19. Offline tests cover a foreign revision, a foreign image, an unlabeled twin, a lost response and a refusal. No mutation is retried. |
| AC18 | PASS | The smoke uses no credential. No Clerk value is stored in GitHub. |
| AC19 | PASS | Each run uploaded its receipt as an artifact and wrote it to the job summary. The workflow has no write access to the repository. Receipts are committed through docs PRs. |
| AC20 | PASS | The candidate drill removed the tag, kept `00010-m2j` at 100% and kept `00011-jjz` for diagnosis. Deleting it right away failed (live finding 5). It was deleted after the clean release. |
| AC21 | PASS | Run 40376678986 recovered `tailtag-api-replica-00010-m2j` with receipt 40364981884-1 and a #206 compatibility note (#356 comment 6423939646). All four gates passed on the tag. Migration NOT_RUN. Generation 19 to 21, with no new revision. |
| AC22 | PASS | The release job has only `contents: read` and `id-token: write`. The eligibility job also has `actions: read` to list CI runs, and it has no cloud identity (approved deviation 2). The AC10 evidence covers the rest. |
| AC23 | PASS | `google-github-actions/auth` is pinned by SHA. It is a verified-creator action, so the `selected` allowlist did not change. Docker buildx and gcloud come from the runner. |
| AC24 | PASS | The four replica values are environment secrets. The run log archive of the first release has 33 files and 3,437 lines. It had no match for the project ID, project number, service host, deployer email, Cloudflare account or Neon project. The only `pkg.dev` match was the public regional registry name in a command line. GitHub masked 70 values. |

## Release effort

Target T-9 in the contract is 15 minutes or less from merge to promoted revision, with no console steps. No release needed a console step.

| Release | Merge | Promoted | Merge to promoted | Dispatch to promoted |
| --- | --- | --- | --- | --- |
| `8aacf1e` | 16:45:47Z (#383) | 17:06:36Z | about 21 minutes | about 4 minutes |
| `c91ce58` | 17:44:24Z (#385) | 18:00:50Z | about 16.5 minutes | about 3 minutes |

Both runs took less than 5 minutes after dispatch. Both merges waited for setup work or a drill before dispatch, so these numbers miss T-9. #361 needs a release that starts right after its merge.

## Live findings

1. The repository uses the GitHub immutable OIDC subject. The `sub` claim carries the owner and repository IDs, so the deployer binding names `repo:TailTag-Game@306886193/tailtag@1306048543:environment:replica`. A review found this before any live use.
2. A fixed revision name in the service template made the first Terraform apply fail with 409. The release script also set a fixed name on every release. Now Cloud Run names revisions, and Terraform no longer ignores `template[0].revision` (#383, AC17 amendment).
3. Cloud Run JSON leaves out `reconciling` when it is false, and its conditions have more keys than `state`. The release reads both as the API sends them.
4. Cloud Run keeps the job generation for an update that changes nothing. The first migrate drill stopped at that update with `FAIL_MIGRATION_UNKNOWN`. #385 skips such an update and needs the job to be ready first.
5. Cloud Run refuses to delete the latest created revision (`FAILED_PRECONDITION`). The runbook now deletes a failed candidate after the next release.
6. Cloud Run started the no-traffic candidate at deploy, and its startup probe failed. So the release stopped before the gates. #348 saw no-traffic revisions report ready without a start. The release catches a failed start either way.
7. The owner organization's Google Cloud session control expires the command-line login (`invalid_rapt`). The owner signs in again with `gcloud auth application-default login` and `gcloud auth login`.

## Approved deviations

1. AC17 lets Cloud Run name revisions, and it attributes a revision by its run label, image and generation. The owner approved this on 2026-10-26, in the #356 amendment comment.
2. The eligibility job has `actions: read` in addition to `contents: read`. It has no cloud identity, environment or secret. The release job has exactly the AC22 permissions.
3. G1 added the candidate tag host to the replica allowed hosts. This is the explicit owner decision that #349 asked for.

## Residual risks and follow-ups

- AC6 and AC17: no live lost response or change from outside the workflow was staged. Offline tests cover them, and the owner accepted that evidence.
- AC15: no live test showed a refused token from another workflow. The owner accepted the readback.
- #358 owns the full recovery proof. This proof only covers the recovery mechanism.
- T-9: measure a release that starts right after its merge in #361.
- `scripts/api_replica_release.py` and `scripts/api_replica_job.py` are not in `BACKEND_RELEVANT_FILES`. A change to only these scripts skips the API CI tests.
- The receipt field `jobs.others` reads `PENDING_SYNC` even when the five jobs already run the digest.
- A later Terraform change to the service carries the release label of the last release into its new revision. The next release replaces the label.
