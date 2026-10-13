# Simulation operations: Staging proof

Issue: [#230](https://github.com/TailTag-Game/tailtag/issues/230) (AC20, AC23, AC25, AC26). Contract: [simulation operations](2026-10-10-simulation-operations.md). Operations: [operator guide](../operations/simulation-operations.md) and [host runbook](../operations/simulation-host.md).

**Checkpoint: 2026-10-13 UTC.** All attended operations proofs passed on the external simulation host against Staging:

- the host smoke;
- one nightly cycle: smoke gate, normal and hotspot;
- one weekend run;
- first runs of the other rotating families.

Soak and weekend have their first baselines. Hotspot, post-event and retry are too small to support thresholds under the #229 rules. The one-time 12-hour natural-expiration proof (AC25) was attempted twice. It is deferred to [#316](https://github.com/TailTag-Game/tailtag/issues/316) with the maintainer's approval.

These runs are regression and correctness evidence. They make no capacity, SLO or production-readiness claim.

## Verified prerequisites

Verified on 2026-10-13 against GitHub. Every prerequisite was closed as completed by 2026-10-01T01:46:26Z, so every run below counts as readiness evidence (AC23). No code or schema marker records this.

| Issue | Prerequisite | Closed (UTC) | Merge evidence |
| --- | --- | --- | --- |
| [#200](https://github.com/TailTag-Game/tailtag/issues/200) | V0 Railway Staging environment | 2026-09-17T00:02:57Z | [#231](https://github.com/TailTag-Game/tailtag/pull/231) `eb518d3` |
| [#201](https://github.com/TailTag-Game/tailtag/issues/201) | Immutable backend build and deployment identity | 2026-09-17T03:50:08Z | [#232](https://github.com/TailTag-Game/tailtag/pull/232) `2586ade` |
| [#203](https://github.com/TailTag-Game/tailtag/issues/203) | Liveness, readiness and environment safety contracts | 2026-09-21T23:08:06Z | [#235](https://github.com/TailTag-Game/tailtag/pull/235) `04f8383`, [#236](https://github.com/TailTag-Game/tailtag/pull/236) `a42dc3a` |
| [#204](https://github.com/TailTag-Game/tailtag/issues/204) | Repeatable Staging synthetic-state reset and reseed | 2026-09-17T19:28:23Z | [#237](https://github.com/TailTag-Game/tailtag/pull/237) `77b6c55` |
| [#210](https://github.com/TailTag-Game/tailtag/issues/210) | Structured backend logging and request correlation | 2026-09-29T20:31:05Z | [#256](https://github.com/TailTag-Game/tailtag/pull/256) `2416110`, [#258](https://github.com/TailTag-Game/tailtag/pull/258) `c242f6e` |
| [#212](https://github.com/TailTag-Game/tailtag/issues/212) | HTTP and backend runtime telemetry | 2026-09-30T06:29:51Z | [#261](https://github.com/TailTag-Game/tailtag/pull/261) `8593b60`, [#263](https://github.com/TailTag-Game/tailtag/pull/263) `25f9c6c` |
| [#213](https://github.com/TailTag-Game/tailtag/issues/213) | Field-beta domain outcomes | 2026-09-30T20:08:33Z | [#266](https://github.com/TailTag-Game/tailtag/pull/266) `f8eb380`, [#269](https://github.com/TailTag-Game/tailtag/pull/269) `38358e3` |
| [#214](https://github.com/TailTag-Game/tailtag/issues/214) | Database and external dependency health | 2026-10-01T01:46:26Z | [#270](https://github.com/TailTag-Game/tailtag/pull/270) `68f8aca`, [#271](https://github.com/TailTag-Game/tailtag/pull/271) `dbf2da9` |

## Releases and boundary

Every run used the existing DigitalOcean RIC1 host (2 vCPU, 4 GiB, `linux/amd64`) described in the [#228 proof](2026-10-10-external-simulation-host-staging-proof.md). Each release was installed through `install-runtime`, and every previous release was kept for rollback.

| Release | Simulator source | Image | Archive SHA-256 |
| --- | --- | --- | --- |
| 1 | `49ee1f4a120c24df23f366c88627742c657bc8c7` ([#310](https://github.com/TailTag-Game/tailtag/pull/310)) | `sha256:c7b8f871908e74378e54555e7c8c68aadbbb6e8ed5ebdcce136ccdc8a51f586b` | `e6ba6c2ec812af096104dfea9ba507b59d36777baa13693fe491f0aef9bda3d7` |
| 2 | `3d5a8ddfa2ba042c86698ad31a22ee29ca0d9a5b` ([#313](https://github.com/TailTag-Game/tailtag/pull/313)) | `sha256:e3ff492ad10052695c93a4155166f8dabe70c60d8359b91bdbf97bc138d7e006` | `02ab5fb4b7a3754a5b91f5c97594651f11fe007ae1ff434a20ec1bd30e2e21e3` |

- **Dependency lock:** `c218b2fb441f1016746c100f4b28899b0422585980e934cad5abd76a277dba9f` for both releases.
- **Staging:** every run pinned and verified source `e8aedd0d2b4e0e0787edf6bcafc7fbcbb95d4902`, deployment `9359c0a2-4915-42cd-9994-521ce7bc740e`.
- **Profiles and safety files:** these reach the host only through the prepared manifest. Profile fixes therefore needed no new release.
- **Execution:** every run was attended. The maintainer launched it from the Mac through the bridge, entered the Clerk secret at a hidden prompt, and kept the Railway CLI on the approved account.
- **Pool:** `host228` was expanded from 20 to 50 identities with `sim-pool-provision` (`created=30`) before the weekend run, under its own authorization.

## Runs

All times are UTC. The run window is 08:00–10:00. The nightly cycle and the weekend run were launched off-window, about 05:30–07:20 on 2026-10-11, with the maintainer's approval. "Collected" means `sim-host-collect` copied the run with size and SHA-256 verification and wrote an evaluation.

| Run | Profile | Release | Started | Result | Evaluation | Report SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `ede2b4ee-2f0c-4e59-9a87-3c40e5aadeb1` | host smoke (`journeys`) | 1 | 2026-10-11 01:01 | passed | correctness only | `b9ff4979b24ce60d82a06ca317ead955de7a3ba61e5833cca1811ea2682492ca` |
| `aee0d2b3-eae9-4e5c-936a-f1ac35939c59` | nightly smoke gate | 1 | 2026-10-11 05:31 | passed | correctness only | `fd991a93e9321d8058c84234c8e3ec5c55757c0f2d696778216ca8b047270529` |
| `e15e681f-01c6-4bba-bb33-9b759293ea48` | normal | 1 | 2026-10-11 05:49 | interrupted (`supervision_lost`), recovered | not evaluated | `9c098a5dacab51121be9721fb63343b014763541da8390d2564578ec0d1d6d74` |
| `c9ef1e6e-f783-4bdc-b257-22143c240abe` | normal (retry) | 1 | 2026-10-11 06:04 | passed | `acceptable` | `5e96fb5508c89f97023e0f87d57614875979810753befc527535b657d506ee1d` |
| `5e7bf54a-d946-443b-a05e-b8fd42d77a1c` | hotspot (cycle family) | 1 | 2026-10-11 06:13 | passed | `inconclusive` | `b16cd5c76938b39297665112b3c1a8f54fcf77e0dc5c1834c6d27e105c32bda4` |
| `8c4d5fcc-1a74-4d29-9809-bb266b37c258` | weekend (480 s) | 1 | 2026-10-11 06:21 | failed (`FAIL_SIMULATION`), recovered | not evaluated | `e0c97c22c8997453d047cbf34594cb065474de8ac7b85ac0c42c3810f586df00` |
| `85f19b2e-4e01-49be-8cc7-52286e43f88e` | weekend (300 s) | 1 | 2026-10-11 06:48 | passed | `inconclusive`, then baseline | `6b757a482ed08b0bd55f22798759aeecf582094f8f417b729efaece66118f728` |
| `72752bdd-cade-415e-86c7-daab6034237e` | post-event | 1 | 2026-10-11 07:18 | passed | `inconclusive` | `596c4f4dd76a184424d3ce8e408d6041968f36655b61093559606c2f66284343` |
| `e175315d-b909-4b4c-88d5-cb6a2cbb689d` | retry (5 attempts) | 1 | 2026-10-11 16:44 | passed | `inconclusive` | `a1990381ba3f074d601b82193e2e8d805266f3ab01660a35260256b445d43c56` |
| `5ce93331-42f3-47a7-aca5-6fd0cd3523c6` | soak | 1 | 2026-10-11 16:53 | passed | `inconclusive`, then baseline | `8d81f042d3926153489040246d4cc75151a80ff3fc74e65a4f860b8c1ff0abc8` |
| `86b9d15b-e2ba-414b-b5d6-2816f7162a72` | host smoke (`journeys`) | 2 | 2026-10-11 20:28 | passed | correctness only | `ae8afb9b600c34279c349dac0acea271fc7f5094b65b44e0e3d3e7078d96739d` |
| `eb53db23-7aa7-4f05-a066-aedeabce6a0d` | expiration | 2 | 2026-10-12 05:47 | aborted (`request_ceiling`), recovered | not evaluated | `5916efbeb2f9ce7791726e8ce8dcdf35443d18ea03b999424b176093b3fd166b` |
| `3ec1520d-2576-48f3-b977-7c96cd8f3454` | expiration | 2 | 2026-10-13 02:57 | failed (`FAIL_LEASE`), recovered | not evaluated | `74a9afd95e1e1dc3fa0b14bc67ad168b211c2a553d33b5de815e4fdc780fbf16` |

Every passing run met all of the following:

- setup passed;
- reconciliation passed 14 checks, and smoke passed all 13 journeys;
- automatic cleanup and lease release passed;
- the container exited 0 with matching report attribution;
- host recovery resolved to `released` automatically, leaving no hold or task container;
- the bridge evidence showed every dispatch `PASS`, no pending mutations and no target veto;
- the pool returned to fully available, with no retained runs.

Passing convention runs had 0 server errors, 0 client errors and 0 timeouts. The normal retry evaluated `acceptable` against the #229 baseline. The image and simulator-SHA caveats were expected, because that baseline came from release 711ee7d. Its total p95 was 258 ms (limit 396) and p99 313 ms (limit 577).

### Weekend

- The 480 s profile spent its 9,000-attempt budget 369 s into the traffic window, and a traffic stop makes a run non-passing. Staging was healthy throughout: 8,996 successes and 0 errors.
- The profile was shortened to 300 s in [#311](https://github.com/TailTag-Game/tailtag/pull/311), with limits unchanged.
- The rerun `85f19b2e` passed with 50 identities and 12 fursuits:
  - 7,006 attempts (78% of the budget), all successful;
  - p95 276 ms and p99 407 ms;
  - execution 731.7 s of the 900 s ceiling.
- The `weekend-profile.json` on main is byte-identical to the one this run used.

### Rotating families

- **Hotspot:** 100 attempts, p95 confirm 411 ms.
- **Post-event:** 124 attempts, p95 502 ms.
- **Soak:** 882 attempts, p95 310 ms and p99 520 ms.
- **Retry:** 151 sends, 18 injected pre-send failures retried, 0 calls out of attempts.
  - Before any run, the retry profile was found to fail by chance about 35–40% of the time, because any exhausted retry fails the run. Its per-call attempts were raised from 3 to 5, the fix from #312 that this change folds in. Run `e175315d` used that profile.

## Recoveries

Every failed or interrupted run kept its recovery hold and blocked admission until it was recovered. For each one, the maintainer authorized the following:

1. **Preserve:** the held report, stage log, host companion and (from release 2) `control/health.json` were copied off the host and hash-verified.
2. **Check identity:** the live Staging identity was confirmed against the run's manifest.
3. **Clean up the exact run** with `sim-cleanup`, which readmitted every quarantined identity.
4. **Resolve the hold** with a `released` receipt. Each receipt was built from the original manifest tuple and the bridge evidence (release acknowledged, 0 pending, no veto) and sent to `host_runner recovery-resolve`.
5. **Collect:** the collected copy matched the preserved hashes.

Nothing resolved a hold automatically.

| Run | Cause | Follow-up |
| --- | --- | --- |
| `e15e681f` | No live health reply for 30 s. The kernel's TCP summary of the operator SSH session showed 0 retransmissions, so the network did not stall. The cause was never isolated. | Bounded bridge closes and health diagnostics ([#313](https://github.com/TailTag-Game/tailtag/pull/313)), then release 2. Supervision did not fail again: the later runs logged 5,807/5,808 and 6,755/6,755 live checks. |
| `8c4d5fcc` | Weekend attempt budget (above). | [#311](https://github.com/TailTag-Game/tailtag/pull/311) |
| `eb53db23` | Staging safety checks (3 requests each, per poll and per 60 s lease heartbeat) reached the 10,000-request ceiling at 8.07 h. | Expiration poll changed from 10 s to 30 s, plus a guard test on every committed safety file ([#314](https://github.com/TailTag-Game/tailtag/pull/314)). |
| `3ec1520d` | One of 537 lease-heartbeat relays returned `FAIL_LAUNCHER` at 9.39 h. Any single heartbeat failure is fatal. | Transient-failure tolerance is in scope for [#316](https://github.com/TailTag-Game/tailtag/issues/316). |

## Baselines (AC20)

| Profile | Run | Result |
| --- | --- | --- |
| Soak | `5ce93331` | Promoted with initial thresholds: p95 limits for confirm, resolve and total. |
| Weekend | `85f19b2e` | Promoted with initial thresholds: p95 limits for confirm, read, resolve and total; p99 limits for confirm, resolve and total. |
| Hotspot | `5e7bf54a` | Refused: fewer than 200 latency samples in every operation (100 in total). |
| Post-event | `72752bdd` | Refused: fewer than 200 latency samples in every operation (124 in total). |
| Retry | `e175315d` | Refused: fewer than 200 latency samples in every operation (144 in total). |

- **Initial thresholds:** derived only where an operation has at least 200 samples (p95) or 1,000 (p99). An empty thresholds file would still evaluate as `inconclusive`. So the three small families stay correctness-gated with `inconclusive` evaluations, as AC20 and the #229 refusal rules allow.
- **Self-check:** before committing, both promoted runs were re-evaluated against their new baselines and came out `acceptable` (15/15 and 25/25 checks passed).

## Natural-expiration proof (AC25): deferred

Two attended attempts used `expiration-profile.json` with `expiration-safety.json`:

- one owner and one casual attendee;
- the session is started once and never refreshed;
- the confirmation is scheduled after the server's real `expires_at`.

Both nights skipped the nightly cycle, as the guide requires.

| | `eb53db23` | `3ec1520d` |
| --- | --- | --- |
| Poll interval | 10 s | 30 s |
| Stopped at | 29,049 s (8.07 h) | 33,801 s (9.39 h) |
| Stop | `request_ceiling` | `FAIL_LEASE` |
| Requests used | 10,000 / 10,000 | 4,974 / 10,000 |
| Supervision health checks live | 5,807 / 5,808 | 6,755 / 6,755 |
| Longest gap between live replies | 6.2 s | 5.3 s |
| Probes / preflight checks passed | 2,873 / 462 | 1,122 / 536 |
| Bridge health refused / close timeouts | 0 / 0 | 0 / 0 |

In both runs, Staging probes, supervision and finalization held for the whole run, and both were recovered (above). Backend tests already cover the 12-hour expiry semantics. This proof adds the real-clock check on Staging.

With the maintainer's approval, AC25 and its AC26 line move to [#316](https://github.com/TailTag-Game/tailtag/issues/316). That issue also carries heartbeat-failure tolerance and the AC14 unattended-scheduling follow-up.

## Evidence preservation and limits

- **Where evidence lives:** reports, evaluations, host companions and stage logs stay in the maintainer's owner-private archive. Held-run copies are kept separately with host-side SHA-256 inventories. This document contains no credentials, host address, account identifiers or other private inventory.
- **Run 8d8666e4:** this run, prepared on 2026-10-09 but never launched, still appears as `incomplete` in collection. It has no reports and no hold.
- **Nature of the evidence:** these are single attended runs of each profile. They show that the profiles, admission, safety ceilings, recovery and collection work end to end. They do not establish variance, capacity or production behavior.
