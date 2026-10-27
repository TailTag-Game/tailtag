# Hybrid replica trust proof (#357)

Status: live phase complete on 2026-10-27

Related issues: [#357](https://github.com/TailTag-Game/tailtag/issues/357) (this proof), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352), delivery proof [#356](2026-10-26-hybrid-replica-delivery-proof.md), runtime proof [#355](2026-10-25-hybrid-replica-runtime-proof.md), contract [#353](2026-10-22-hybrid-replica-contract.md)

Runbook: [Hybrid replica trust](../development/hybrid-replica-trust.md)

This document records the evidence for each #357 acceptance criterion. AC1 to AC9 come from the issue. AC10 to AC21 come from the refinement comment on #357. Each result is PASS, PARTIAL or NOT_EXERCISED. All 21 criteria pass. Some checks inside a criterion stay NOT_EXERCISED by design, and the evidence column names them.

## Identities

| Item | Value |
| --- | --- |
| Tooling source | `2fb1c1a` (PR #389) for every live check |
| Served source | `c91ce58523fa0eb32c572545983401c5148c675f` (`c91ce58`) |
| Served image | `sha256:930503c76ccce87a87c574158729ba4bf47d411cbe533a971e649f5180d9699e`, unchanged through the run |
| Service revisions | `tailtag-api-replica-00014-wtd` until the release, then `tailtag-api-replica-00016-fh9`. `00015-khj` was the Clerk drill revision, and the agent deleted it. |
| libpq | 18.0 in the image and on the owner workstation |
| UTC window | 2026-10-26 to 2026-10-27 |

This document never records project IDs, project numbers, hosts, account IDs, connection strings, tokens or object keys.

## Runs

| Run | Source | Purpose | Outcome | Receipt |
| --- | --- | --- | --- | --- |
| 40553127918 | `c91ce58` | Fresh instances after the AC19 rotations | `PROMOTED` to `00016-fh9`, migration `PASS`, all four gates `PASS` | [40553127918-1](../development/replica-deployments/40553127918-1.json) |

## Results

| AC | Result | Evidence |
| --- | --- | --- |
| AC1 | PASS | The replica Clerk application and its two synthetic users came from #355 AC18. AC11 and AC12 show that valid auth works and that the API denies every negative with no bypass. |
| AC2 | PASS | The trust matrix in the runbook has one row per connection with every AC17 column. The Sentry row is NOT_EXERCISED until #358, because the replica has no Sentry key. |
| AC3 | PASS | AC14 proves the TLS controlled failure. AC13 proves the role grant sets. AC20 shows that `tt-migrator` reads only its own secret. |
| AC4 | PASS | AC15 proves bucket and credential isolation and that anonymous reads fail. AC16 proves the authenticated upload, read and replace paths through the existing API. |
| AC5 | PASS | The media smoke proves the signed read, the byte-for-byte read, the delete and the absence check. Unit tests prove cleanup after a failure. The AC16 probe deleted its own last object and confirmed it gone. The baseline object kept the same SHA-256 before and after. |
| AC6 | PASS | AC20: 200 Policy Troubleshooter checks and the binding readback match Terraform, including the #356 deployer identity. |
| AC7 | PASS | AC18: no secret value in any surface. The one unavoidable exposure stays the Neon admin password in Terraform state, readable only by the owner and `tf-infra`. |
| AC8 | PASS | The runbook names the owner as operator and gives the revocation order for each credential. AC19 ran two live rotations. The Clerk key and the deployer are NOT_EXERCISED by design. |
| AC9 | PASS | AC21: three provider faults, each fail-closed, with correct catch state after each restore. |
| AC10 | PASS | No drill changed a template environment value. The Clerk fault ran on a drill revision made with the release helpers. Traffic stayed pinned until the planned release. The restore checklist passed before that release. |
| AC11 | PASS | Probe, 13 of 13. Valid token 200. No header, `Bearer not.a.jwt`, `Token abc`, a changed signature and an expired token (after `exp` plus 5 seconds) each got 401. Wrong issuer, audience and authorized party cite the offline tests, including the #389 `aud` test. |
| AC12 | PASS | The catcher got 404 for `GET`, `PATCH` and photo `PUT` on the owner's fursuit. The catcher's list held none of the owner's 2 fursuits. |
| AC13 | PASS | `--limits`: 33 of 33 cells ok, before and after the AC19 rotation. The admin report was NOT_EXERCISED, because no admin URL was set in the session shell. |
| AC14 | PASS | Migrate job `lgbfk` with a CA file without ISRG Root X1 and `wzhvv` with `PGHOSTADDR` at a `us-east-2` proxy each ended `FAIL_MIGRATION`. The control `vrkxg` ended `PASS`. Traffic did not move. |
| AC15 | PASS | R2 denied `ListBuckets`, and `PUT` and `GET` on a second bucket, for the runtime keys. Every unsigned request got R2's 400 `InvalidArgument` "Authorization", which the owner accepted as a refusal. The owner confirmed the token scope and that r2.dev access is off. |
| AC16 | PASS | The smoke passed: upload, 600-second presigned read byte for byte, delete and absence. A temporary probe, run 2, passed 9 of 9 through the API. It made a fursuit with a photo (201), and `photo_url` returned that image. It replaced the photo (200), the new URL returned the new image, and the old URL returned 404. A reset then removed the probe rows. |
| AC17 | PASS | The runbook `docs/development/hybrid-replica-trust.md` holds the matrix, grant sets, rotation and compromise steps, drills and restore checklist. This proof cites it. |
| AC18 | PASS | The canary scan of 6 secrets found 0 matches. It covered 998 log entries (31 days), 9 release runs and their artifacts, and issues and pull requests #352 to #389. It also covered git history, Terraform outputs and the serving image. The agent opened 5 closed image blobs and scanned them too: 0 matches. |
| AC19 | PASS | Neon: `--rotate` ran, Neon refused the old runtime password, the new one worked, and the release started fresh instances. R2: after the roll, the old key failed at upload and the new key passed. |
| AC20 | PASS | Policy Troubleshooter: 200 checks, 0 mismatches. The overall answer read `UNKNOWN_INFO`, because the owner cannot read organization deny policies. The binding readback matches Terraform. The test added no grant. |
| AC21 | PASS | Wrong Clerk key: 401 on the drill revision. Neon disabled: 500. R2 revoked: the catch still returned 201. After each restore, there was no phantom catch, a retry returned 201 and a repeat returned `already_caught`. A reset restored the baseline. |

## Fault and drill timeline

All times are UTC on 2026-10-27.

| Step | Window | Detail |
| --- | --- | --- |
| A, wrong Clerk key | 17:32:40 to 17:33:48 | Version 2 added, drill revision `00015-khj` tagged `candidate`. Restore: the good key added again as version 3, version 2 disabled, tag removed. |
| B, Neon disabled | 17:34:07 to 17:34:13 | The replica's default read-write endpoint. A catch attempt got 500. |
| R1, reset | 17:34:30 | Baseline version 1 restored. |
| C, R2 roll | about 17:37 to the release | The owner rolled the token, so the access key ID stayed the same. `media-secret-access-key` version 2 holds the new value. |
| D, Neon rotation | 17:38:13 to the release | All three role passwords rotated. |
| E, release | 17:42:34 to 17:46:42 | Run 40553127918. |
| F, checks and reset | 17:47:50 to 17:49:08 | Media smoke, `--limits`, drill revision deleted, final reset `jw9cg`. |
| AC16 probe and reset | to 18:11:35 | Two probe runs, then a reset that removed both probe fursuit rows. |

During step A, any instance of the serving revision that started in the window got the wrong key. The main URL accepted the catcher right after the restore, so the drill saw no such instance. From step C until the release, the serving revision had no working media key. From step D until the release, it had no working database password. The replica has no players.

## Pre-checks

| Fact | Result |
| --- | --- |
| A `PGHOSTADDR` mismatch fails host name verification | PASS offline. The certificate for `*.us-east-2.aws.neon.tech` did not match, before any password was sent. A `us-east-1` control failed only at the password. |
| R2's answer to an unsigned request | HTTP 400, `InvalidArgument`, "Authorization", for a random key, a bucket listing and another bucket |
| A disabled Neon endpoint comes back | PASS on a temporary branch. Queries failed 2 seconds after the disable and worked 2 seconds after the re-enable. |
| A token that carries `aud` fails | PASS offline, from the new test in #389 |

## Live findings

1. R2 answers every unsigned S3 request with 400 `InvalidArgument` "Authorization", not 401 or 403. PR 2 teaches the media smoke this exact answer. Any other 400 still fails.
2. The migrate job refuses a run without the `TAILTAG_JOB_REQUEST` identity (`FAIL_REQUEST`). The runbook commands now send it.
3. The job runner prints one fixed result line, so job logs never name a libpq error.
4. Neon hosts carry a cell label. A hand-built host reached a proxy that answered "password authentication failed". Take connection URIs from Neon.
5. On a temporary Neon branch, the copied `runtime` role refused its password. The cause is not known. The replica's own branch was not affected.
6. Policy Troubleshooter answered HTTP 429 on 57 of 200 calls with 8 parallel workers. Two workers with backoff finished cleanly.
7. The replica image holds closed blobs that the canary scan does not open: xz apt logs and a nested `zoneinfo` tarball.
8. A first request after a scale to zero can take more than 20 seconds.
9. The same image normalizes to different PNG bytes on macOS and on the Linux image, because the Pillow wheels ship different zlib builds. The first AC16 probe run compared bytes with a local normalization and failed 2 checks for that reason. Run 2 compared decoded pixels. A probe that checks an API image has to decode it.

## Residual risks and follow-ups

- `maintainer` owns the database and the `public` schema, so it can create and drop tables. This is by design for reset, and two controls bound it.
- Every runtime secret uses the `latest` version, so a new value reaches only new instances. This finding stays recorded, not changed.
- The Neon admin password stays in Terraform state.
- Clerk documents no rotation of the instance signing key. A compromise needs a new Clerk application.
- The owner reported the post-drill foundation plan as done with no change. The plan output is not in this proof.
