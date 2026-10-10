# External simulation host: native Staging proof

Issue: [#228](https://github.com/TailTag-Game/tailtag/issues/228). Contract: [approved spec](2026-10-08-external-simulation-host.md). Operations: [host runbook](../operations/simulation-host.md).

**Checkpoint: 2026-10-10 UTC.** The authorized normal workload, separate controlled stop and public-path observation are complete. Exact-run recovery restored the full twenty-identity pool. Private provider inventory confirmation remains pending before issue closeout.

## Release and execution boundary

Both milestones used the same clean immutable simulator release on the provisioned DigitalOcean RIC1 v5 host: 2 vCPU, 4 GiB RAM, 30 GiB disk, `linux/amd64`. The maintainer's override is US$0.052/hour with a US$40/month before-tax operating budget. These quoted amounts are not a verified bill or transfer allowance.

| Release binding | Verified value |
| --- | --- |
| Simulator source | `28c0799f8a3eea49477e8459587a90178e027503` ([PR #305](https://github.com/TailTag-Game/tailtag/pull/305)) |
| Immutable image | `sha256:d18403c388a55ca8e5b267cf8c5b2353a51396a4dd58dea4c44a1b726cb73945` |
| Dependency-lock SHA-256 | `c218b2fb441f1016746c100f4b28899b0422585980e934cad5abd76a277dba9f` |
| Archive SHA-256 | `c0942c8b116a367b1f6aa55c329057a20dad2c39d0907b3f42cfbfcfd21f56e3` |
| Pinned Staging backend source | `e8aedd0d2b4e0e0787edf6bcafc7fbcbb95d4902` |
| Runtime | Host-control Python 3.13.11; container Python 3.13.15; httpx 0.28.1; uv 0.9.17; Docker 29.9.0 |

Archive/image/platform/source/lock bindings were checked before execution. The original private manifests preserve the exact Staging source/deployment/environment tuple. Gameplay and Clerk traffic used the container's public HTTPS path; privileged fixture/pool orchestration used the finite maintainer bridge. No production workload, new provider setting, scheduled load or automatic restart was introduced.

Native bootstrap evidence records Ubuntu 24.04 LTS amd64, the five pinned Docker package versions and holds, disabled swap/core dumps, owner-private files and nonroot runtime. Independent forwarding evidence proved two private Unix forwards and refused remote/local TCP forwarding. Host addresses, keys, allowed source addresses and provider account/billing identifiers remain in private operator inventory.

## Normal milestone

Run `1e6d6fed-124a-4826-9f2c-090b3b37c017` ran from `2026-10-10T04:47:20.603189Z` to `04:55:20.766283Z`. The foreground command exited zero. Schema-4 report outcome and correctness are `passed`, with fourteen reconciliation checks passed, clean source attribution and the original pinned Staging identity verified. No safety abort occurred.

The normal profile used twenty identities, four owners/fursuits, ten active actors and the unchanged 300-second schedule. The separately approved generation ceiling was 360 seconds; owner preparation shares that ceiling with traffic. Setup pacing adds 76 seconds between twenty identity attempts, outside the traffic schedule.

| Normal accounting | Observed |
| --- | ---: |
| Total report duration | 480.163 seconds |
| Setup phase | 139.318 seconds |
| Traffic generation / drain | 300.000 / 1.102 seconds |
| Offered / admitted / completed / skipped entries | 1,680 / 1,653 / 1,653 / 27 |
| Workload request attempts / ceiling | 8,303 / 9,000 |
| Peak active actors / ordinary in-flight requests | 10 / 10 |
| Scheduling lag | 0.025775 seconds |
| Unresolved / exhausted / retries / transient failures | 0 / 0 / 0 / 0 |
| Safety execution requests / ceiling | 8,538 / 10,000 |
| Safety execution time / ceiling | 472.635 / 900 seconds |
| Finalization requests / ceiling | 9 / 1,000 |
| Finalization time / ceiling | 7.483 / 600 seconds |

The host companion contains 97 resource samples: peak Docker-reported CPU 64.42%, peak memory 2.65%, and a cumulative CPU-steal tick counter moving from 6 to 7. The CPU value is the raw Docker percentage; the steal counter is not a percentage. Backend resource observations were unavailable. These measurements describe this bounded run and do not establish capacity, throughput limits or an SLO.

Automatic cleanup acknowledged one convention, twenty enrollments, four fursuits, four activations, thirty-two catches, four sessions, four credentials and four images. Clerk closure and lease release passed. Actual maintainer bridge evidence acknowledged cleanup/release with zero pending operations and no mutation uncertainty or target veto. Independent pool/fixture checks and authenticated host recovery resolution subsequently confirmed twenty available identities, zero leased/quarantined, zero retained/unfinished runs, zero host holds and zero task containers.

The original host companion's recovery snapshot was `uncertain` before outer resolution. It remains unmodified; the separate bridge and recovery records establish final settlement. Public peer observation was not captured during this normal run; the separate stop milestone below supplies that observation for the shared host/image execution path.

## Controlled-stop milestone and public path

Run `5013b648-9de3-4333-8f67-b399f411313e` ran from `2026-10-10T05:28:17.956856Z` to `05:29:21.458711Z`, with four identities, two owners/fursuits and two active actors. After setup, a second trusted session observed the exact workload container and invoked the repository's exact-run stop command. That command exited zero; the container exited 130. The foreground Make command exited 2 with `FAIL_INTERRUPTED`, as expected for intentional SIGINT. No hard stop occurred and traffic recorded an external stop.

| Stop accounting | Observed |
| --- | ---: |
| Total report duration | 63.502 seconds |
| Traffic generation | 11.083 seconds |
| Offered / admitted / completed / skipped entries | 19 / 19 / 19 / 0 |
| Workload request attempts | 93 |
| Peak active actors / ordinary in-flight requests | 2 / 2 |
| Scheduling lag | 0.003099 seconds |
| Safety execution requests / time | 136 / 54.349 seconds |
| Finalization requests / time | 15 / 9.095 seconds |
| Host resource samples | 13 |

At `2026-10-10T05:29:12.172195+00:00`, the private observation bound the full stored Docker CID, run UUID, immutable image and original manifest to the running workload container. It observed four already-established container connections to a DNS-matched public IPv4 peer on port 443 **before** making a separate probe. An unauthenticated identity GET in that container's network namespace then verified the default TLS certificate chain and hostname, negotiated TLS 1.3 and matched the original Staging backend identity. This was one additional observation request outside the workload report counters. Endpoint addresses, raw connection details and the certificate record remain private. This proves actual public connections during execution; it does not trace every Internet hop or attribute that observation to the earlier normal run.

The stop report's correctness and final report identity are `not_observed`, consistent with interrupted execution. The original starting/safety/bridge identity, separate public probe and fresh recovery target checks bound recovery to the original Staging tuple; no final reconciliation PASS is claimed for the interrupted run.

Bounded finalization acknowledged retention, Clerk session closure and lease release. Four identities were quarantined for exact-run recovery. Subsequent cleanup acknowledged one convention, four enrollments, two fursuits, two activations, three catches, two sessions, two credentials and two images, then readmitted four identities. Independent checks confirmed twenty available identities, zero leases/quarantine, zero retained/unfinished fixtures, zero host holds and zero task containers. The recovery receipt was derived from actual bridge acknowledgements and matched the original manifest. Original report/stage/host evidence remained unchanged.

## Evidence preservation and remaining limits

Authenticated SSH retrieval and SHA-256 comparison preserved each milestone in a separate owner-only archive (directory 0700, files 0600). Archives include the original schema-4 report, host companion, stages, immutable launch/release metadata, private profile/safety, actual bridge evidence, recovery receipts and final verification. The stop archive additionally contains the bounded observation and exact-run operator helper. Raw archives are private; this document is the sanitized durable record.

| Run | Original report SHA-256 | Original host companion SHA-256 |
| --- | --- | --- |
| Normal `1e6d6fed` | `fefca6e21dab311b0a69439577ed8c42f59c8aee9f7bc2287af92ac0e34f4306` | `a9fad90a1662a2b331d60d6b843dac782a4538b141414165f38a09296387c2d8` |
| Stop `5013b648` | `97e75a8504db59e396a88236cbbc8778f0aa98b882a3c9c1dd482d21e34ce927` | `8a436af5f90d5076099fef4ee975fefe32a07fca34821641e9203df9197dee69` |

Earlier failures remain preserved as failures. Run `129007b8-53be-40b8-8ba6-5c935dd14f7c` consumed the former 300-second generation ceiling during owner preparation and ended traffic early; it motivated the approved 360-second preparation margin. Run `7146bb54-7ab4-45a1-87e5-2949aa71f741` reached its generation ceiling before manual interruption and is not a controlled-stop proof. Both received exact-run cleanup/readmission and host resolution before later admission. Consumed manifests are never reused, and previous immutable releases remain available for rollback.

Four-second setup pacing avoided the previously observed HTTP 429 in these two milestones. It does not identify Clerk's rejecting limiter/window or guarantee future admission. No provider limit change or credential retry was made. Backend monitoring and latency percentiles were unavailable; long-duration endurance and expiration/pruning over retention windows were not observed live.

Before closing #228, confirm private provider plan class, included monthly transfer, current usage/overage and project/billing ownership, plus absence of paid add-ons or automatic resizing. Do not infer those facts from the v5 label or quoted hourly rate. Publication of this record and tracker updates remain separate authorized actions; no additional live workload is required to establish the completed milestones.
