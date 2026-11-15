# Catch approval simulation on Render Staging: proof

Issue: [#508](https://github.com/TailTag-Game/tailtag/issues/508). Spec: [refinement comment](https://github.com/TailTag-Game/tailtag/issues/508#issuecomment-6837802460). Contract: [reusable tag and catch request contract](2026-11-09-reusable-tailtag-catch-request-contract.md). Code: [PR #528](https://github.com/TailTag-Game/tailtag/pull/528) (API), [PR #529](https://github.com/TailTag-Game/tailtag/pull/529) (simulator), [PR #530](https://github.com/TailTag-Game/tailtag/pull/530) (gate), and [PR #531](https://github.com/TailTag-Game/tailtag/pull/531) (relay fix).

Checkpoint: 2026-11-14 UTC. The maintainer synced the Blueprint and promoted `150fbe5` to Render Staging. The catch request gate is on. Smoke, the new normal profile, and the limit scenario all passed. The normal run is the first baseline for convention v3. The per-player limit of 30 requests in 600 seconds permits normal play, so no limit change is needed.

## Scenario and environment (AC40)

| Binding | Value |
| --- | --- |
| Environment | Render Staging, `staging.tailtag.app`, Virginia region (ADR 0012) |
| Backend source | `150fbe570699e6fb3a40d6c79994149b4cc5a0aa` ([PR #530](https://github.com/TailTag-Game/tailtag/pull/530)) |
| Staging promotion | `dep-dbs9mgrbc2fs73avsslg`, deployed `2026-11-14T17:32:51Z`, every outcome `SUCCEEDED` ([receipt](../development/staging-deployments/dep-dbs9mgrbc2fs73avsslg.json)) |
| Staging plans | API `0.5c-512mb`, PostgreSQL `0.1c-256mb` |
| Gate | `CATCH_REQUESTS_ENABLED` is `"true"` on `tailtag-api-stg` through `render.yaml` |
| Per-player limit | 30 created requests in a rolling 600 seconds, the `base.py` defaults |
| Simulator release 1 | `150fbe570699e6fb3a40d6c79994149b4cc5a0aa`, image `sha256:af8735ed8e2e3ba839cb0d41b731285144f58d2bb1edaf9545e9194805abef10` |
| Simulator release 2 | `6a2c7769492c3244286a8435475aafcf97a4aaf7`, image `sha256:7fe5e8262c89bfe5af85f29ec8cbb822d8472e57e1025d521e7da1a3edc8c9c6` |
| Host | The external simulation host, DigitalOcean RIC1, `linux/amd64` |

Release 2 adds only the relay fix from [PR #531](https://github.com/TailTag-Game/tailtag/pull/531). It changes no scenario, profile, or API code.

The three scenarios:

| Scenario | Profile | What it does |
| --- | --- | --- |
| `journeys` v2 | `host/smoke-profile.json` | 21 journeys. Each request action runs once: approve, automatic approval, decline, decline with block, undo, restore, withdraw, cooldown, retry, duplicate submission, stopped session, and tag replacement. |
| `convention-baseline` v3 | `host/normal-profile.json` | 4 owners with 1 suit each and 16 catchers for 300 seconds at 10 active. Catchers preview and submit. Owners review and decide. |
| `request-limit` v1 | `host/request-limit-profile.json` with `host/request-limit-safety.json` | 8 owners with 5 suits each and 2 players. Provisioning moves the review deadline 1,200 seconds into the run. |

## Sessions and runs (AC35, AC36)

The maintainer ran two host operator sessions on 2026-11-14. Each session had its own key, registered on Render only for that session. The maintainer removed both keys at session end. Session 1 recorded `FAIL_LAUNCHER` for the first negative control. Session 2 recorded `PASS` for the positive control, with 30 of 50 pool identities available. The other control results were not kept.

| Run | Session, release | Window (UTC) | Result |
| --- | --- | --- | --- |
| `2189940a-2d06-4fa5-abc2-572a21c1eee4`, smoke | 1, release 1 | `19:01:50Z` to `19:04:54Z` | `passed`. All 21 journeys passed. Reconciliation passed 14 checks. |
| `5c76065e-665c-40c5-ae36-fbf5d421c097`, normal | 1, release 1 | `19:37:01Z` to `19:46:14Z` | `failed`. Traffic completed, but reconciliation failed to read the population. See [the failed run](#the-failed-normal-run). |
| `146750de-ea87-4b9e-a99a-bb292487fa12`, normal | 2, release 2 | `21:21:11Z` to `21:30:31Z` | `passed`. Reconciliation passed 17 checks. Cleanup removed every fixture, including 30 catches. |
| `e7029cea-2637-4afd-8e8a-c02e12a71942`, limit | 2, release 2 | `21:34:31Z` to `21:58:00Z` | `passed`. `normal_play`, `abuse_limit`, and `expiry` passed. Reconciliation passed 17 checks. |

`task sim-host-collect` copied every run into the owner-private archive with size and SHA-256 checks. It also evaluated both normal runs.

| Run | Report SHA-256 | Host companion SHA-256 |
| --- | --- | --- |
| `2189940a` | `29acecdb379d3d8f4b90972d6f4769d4db3251334e90ea170f3b65e0a0e8c9dd` | `3bcc5abdcaba934f7714a3fc2b55804e4047f4da6382be5fc7e25e347b0bcb1d` |
| `5c76065e` | `c523db7eb90935b8e6b12f64ba9f333824642ae9b74a5a20ea1cbdc1b39daaa3` | `9e72cbeee495e57ddd4685b3d413e4325c80b8c527519010228dc533ac675024` |
| `146750de` | `59d49bad8d0ff4baeaa3622edc1e05f9738bfa59edd812056e01d87fa6870bfe` | `822798ff4f3dc3fe0b3ecd6f1498dd7fc41ef598f796997c44d7fb7361c41740` |
| `e7029cea` | `350488e7d9e24d04ca680d157171d5dac7ad77ca2e0b545414d5249ef13c43a4` | `cec766a07ffbb3efcd94a505a9fe01fb5ba030feb75a33a7343c029e2f5540ea` |

### The failed normal run

Run `5c76065e` used `inspect-population-v2` for reconciliation. The host bridge recorded `FAIL_LAUNCHER` for that operation. Staging answered correctly. The relay on the host, `scripts/api_sim_inspect_ssh.py`, accepted only the four v1 data keys, so it rejected the new `requests` key. Smoke uses the v1 `inspect` operation, so smoke did not find it.

[PR #531](https://github.com/TailTag-Game/tailtag/pull/531) fixed the relay. The maintainer then settled the run with the runbook recovery steps:

1. The bridge evidence showed an acknowledged release and no uncertain mutation.
2. Staging still served `150fbe5`.
3. `task sim-cleanup` cleaned the run and readmitted its 20 quarantined identities.
4. `host_runner recovery-resolve` cleared the host hold with the receipt the bridge had recorded.

The failed run evaluates as `not_evaluated`, because correctness failed. It promotes nothing.

## Result (AC37)

The Staging run passes. Correctness, reconciliation, and the limit checks passed in every run after the fix. Latency is recorded below, but it does not decide the result (G9).

## Limit behavior (AC31 to AC33)

| Journey | Contract | Result |
| --- | --- | --- |
| `normal_play` | 20 creates, one every 30 seconds for 10 minutes, with no 429 | `passed` |
| `abuse_limit` | A new suit every 2 seconds. Creates 1 to 30 succeed. Create 31 gets 429 `rate_limited` with `Retry-After`. The next create after that wait succeeds. | `passed` |
| `expiry` | After the deadline, the player and owner lists omit the request, and approval is closed | `passed` |

Normal play got no 429 at 30 requests in 600 seconds. AC33 needs no limit change and no settings PR.

## First baseline (AC38)

`task sim-baseline-promote` with `INITIAL_THRESHOLDS=1` promoted run `146750de` as the first baseline for convention v3. Convention v3 has a new comparable key, so no earlier baseline applies.

| Item | Value |
| --- | --- |
| Comparable key | `convention-baseline` v3, plan `b73ad56d829b…`, `staging`, `external_host:linux/amd64` |
| Files | `tools/simulator/baselines/convention-baseline-v3-b73ad56d829b-external_host-linux-amd64.{baseline,thresholds}.json` |
| Re-evaluation | `acceptable`, 31 checks passed, 0 breached, 0 regressed |
| Generator | Peak CPU 67.36%, peak memory 3.33%, 5 steal ticks, lag 0.02 s |

### Baseline metrics

| Operation | Samples | p50 | p95 | p99 | Rate |
| --- | --- | --- | --- | --- | --- |
| total | 6,551 | 294 ms | 604 ms | 806 ms | 21.69 per second |
| preview | 1,941 | 290 ms | 598 ms | 791 ms | 6.43 per second |
| submit | 1,941 | 319 ms | 698 ms | 985 ms | 6.43 per second |
| review | 508 | 302 ms | 687 ms | 795 ms | 1.68 per second |
| decide | 23 | 402 ms | 1,102 ms | 1,299 ms | 0.08 per second |
| read | 2,074 | 211 ms | 498 ms | 694 ms | 6.87 per second |
| auxiliary | 64 | 49 ms | 100 ms | 116 ms | 0.21 per second |

Errors and timeouts were 0 in every operation. The `decide` and `auxiliary` samples are too few for the p95 minimum of 200, so the thresholds file sets no limit for them.

### Proposed thresholds

These are the tool defaults from this run. Every value carries its assumption text.

| Operation | p95 limit | p99 limit | Error and timeout rate |
| --- | --- | --- | --- |
| total | 1,208 ms | 1,613 ms | 0.01 |
| preview | 1,196 ms | 1,583 ms | 0.01 |
| submit | 1,396 ms | 1,971 ms | 0.01 |
| review | 1,374 ms | none, 508 samples | 0.01 |
| read | 997 ms | 1,389 ms | 0.01 |

The regression, saturation, and minimum-sample values are the same defaults as the v2 baseline.

## How to read the aggregate results (AC42)

The run report holds the simulator's view. Sentry holds the API's view. Compare the two for the same window.

In the report, `results.behavior.items` has one counter set per persona. Add the personas together for the run totals. Run `146750de` had these totals:

| Counter | Value | Meaning |
| --- | --- | --- |
| `pending` | 23 | Submissions that created a pending request |
| `automatic` | 9 | Submissions to automatic suits that created a catch at once |
| `approved` | 21 | Owner approvals |
| `declined` | 2 | Owner declines |
| `already_pending` | 116 | Repeat submissions that found the pending request |
| `already_caught` | 1,793 | Repeat submissions after the catch existed |
| `retries` | 0 | Retried requests after a lost response |

In Sentry, open Explore, then Metrics. Choose the counter `tailtag.catches.request_decision`, filter on `environment:staging`, sum the value, and group by `tailtag.outcome` and `tailtag.reason`. Use a 10-minute interval to find each run.

| Window (UTC) | Run | Decisions |
| --- | --- | --- |
| 19:00 to 19:10 | smoke `2189940a` | 11: approved 3, declined 4, declined with `blocked` 1, `decline_undone` 1, `restored` 1, `withdrawn` 1 |
| 19:40 to 19:50 | failed normal `5c76065e` | 23 |
| 21:20 to 21:30 | normal `146750de` | 23: approved 21, declined 2 |
| 21:30 to 22:00 | limit `e7029cea` | 0 |

Read these counts with these rules:

- The normal run has 23 decisions, the same as its 21 approvals and 2 declines in the report. So every owner decision reached the API once.
- Automatic approvals are not decisions. They appear on `tailtag.catches.confirmation` as `created`.
- The limit scenario makes no owner decisions, so 0 is correct. Its 429 responses appear on `tailtag.catches.confirmation` as `rejected` with `rate_limited`.
- Expiry deletes nothing at run time. The daily cleanup job records it later on `tailtag.catches.request_cleanup` with reason `expired`.
- A repeat action and a refused action record nothing (AC7). Use the HTTP request metric for those responses.

The [domain outcomes guide](../operations/backend-domain-outcomes.md#catch-request-decisions) defines each outcome and reason.

## #499 at run time (AC39)

[#499](https://github.com/TailTag-Game/tailtag/issues/499) was open at run time, with no change merged. The API CPU outside the database still limits the request rate on Staging. The normal run reached 21.69 requests per second.

## Limitations (AC41)

- The limit scenario moves the review deadline 1,200 seconds into the run with a fixture-only offset. A real convention closes review at its own deadline.
- The decision mix is an assumption: 25% automatic suits, a 5 to 30 second review delay, and 85% approval. Real owners can behave differently.
- The simulator does not copy or share QR codes. Every submission uses the tag of a suit that the catcher visits.
- The #499 CPU limit applies. The latency numbers measure a CPU-bound API on a `0.5c-512mb` plan.
- Each scenario ran once. One run is a first baseline, not a capacity claim.
- The journeys and limit reports do not record latency. Only the normal run has latency.
- The `decide` operation had 23 samples, so its latency is not a reliable measure.

## Privacy (AC44)

This document, the reports, and the baseline files contain run IDs, commits, image IDs, and aggregate counts. They contain no token, tag payload, or player, suit, or request identifier.
