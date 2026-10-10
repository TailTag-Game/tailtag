# Simulation performance evidence: Staging proof

Issue: [#229](https://github.com/TailTag-Game/tailtag/issues/229) (AC20). Contract: [implementation contract](2026-10-10-simulation-performance-evidence.md). Operations: [host runbook](../operations/simulation-host.md#backend-context-for-performance-evaluation).

**Checkpoint: 2026-10-10 UTC.** Two authorized normal-profile runs passed on the external simulation host. Run 1 was evaluated and then promoted, with initial thresholds, as the first Staging baseline in [PR #308](https://github.com/TailTag-Game/tailtag/pull/308). After that merged, run 2 was evaluated against the baseline and returned `acceptable`. The run-to-run variation is within the AC15 default tolerances, so no threshold decision was needed.

## Release and execution boundary

Both runs used the same clean, immutable simulator release on the existing DigitalOcean RIC1 host (2 vCPU, 4 GiB, `linux/amd64`) described in the [#228 proof](2026-10-10-external-simulation-host-staging-proof.md). The release was installed through the #228 `install-runtime` flow, and the previous release was kept for rollback.

| Release binding | Verified value |
| --- | --- |
| Simulator source | `711ee7ddbdd4a53731398dc858104c0ebf4d4edb` ([PR #307](https://github.com/TailTag-Game/tailtag/pull/307)) |
| Immutable image | `sha256:1295e4158d59b5adc6e308c3cbfc0ebcabd5725ec8ca4f320d8f02d34afbbb81` |
| Dependency-lock SHA-256 | `c218b2fb441f1016746c100f4b28899b0422585980e934cad5abd76a277dba9f` |
| Archive SHA-256 | `8fd3cdaf4ed56a4a7ec17bf1061424476d66b45635a74db4ef28e7cf7e2755af` (compared on the host before load) |
| Pinned Staging backend | source `e8aedd0d2b4e0e0787edf6bcafc7fbcbb95d4902`, deployment `9359c0a2-4915-42cd-9994-521ce7bc740e` |
| Profile | `tools/simulator/host/normal-profile.json` unchanged: 20 identities, 4 owners/fursuits, ten active actors, 300-second schedule, seed 22801 |
| Comparable key | `convention-baseline` v2, plan `dac260032cf2…`, `staging`, `external_host:linux/amd64` |

Each run used a freshly prepared manifest. Both runs passed:
- the starting target check;
- setup of 20 identities;
- 14 reconciliation checks;
- automatic cleanup of one convention, 20 enrollments, 4 fursuits, 4 activations, 32 catches, 4 sessions, 4 credentials and 4 images;
- lease release.

Host recovery was resolved automatically from the bridge receipt. Neither run left a recovery hold or a task container. Pool `host228` showed 20 available, none leased or quarantined, and no retained or unfinished runs before each run. No attempt failed or was aborted, so nothing needed to be preserved as a failure.

## Runs

| | Run 1 (baseline) | Run 2 (evaluated) |
| --- | --- | --- |
| Run ID | `97847263-7b7e-459b-b7fe-6187096b917a` | `7102939c-ed75-4d38-a8fc-3f1c1068bbab` |
| Started / ended (UTC) | `2026-10-10T21:21:25.790761Z` / `21:29:16.266488Z` | `2026-10-10T21:36:09.438444Z` / `21:43:56.685557Z` |
| Report duration / traffic window | 470.476 / 301.721 seconds | 467.247 / 300.884 seconds |
| Report outcome / correctness | `passed` / `passed` | `passed` / `passed` |
| Workload attempts (all `success`) | 7,360 | 7,941 |
| Generator: peak Docker CPU / memory | 45.42% / 2.66% | 62.08% / 2.72% |
| Generator: scheduling lag / CPU-steal ticks | 0.016 s / 1 | 0.015 s / 0 |
| Host companion samples | 95 | 94 |
| Evaluation (with host companion) | `inconclusive`: `no_baseline`, `no_thresholds` | `acceptable`: 27 checks passed, 0 breached, 0 regressed |

Docker CPU uses its own units, where 200% is both vCPUs. Steal is a raw tick delta, not a percentage.

Every attempt in both runs was a success: there were no expected rejections, client or server errors, timeouts, transport errors or injected faults.

## Latency, throughput and variation

Latency is measured from request issue to the last response byte, in milliseconds, using nearest-rank percentiles. Throughput is attempts per second over the traffic window.

| Operation | Run 1 samples | Run 1 p50 / p95 / p99 | Run 2 samples | Run 2 p50 / p95 / p99 | p95 change | p99 change | Throughput change |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| `resolve` | 2,918 | 197.4 / 316.5 / 378.6 | 3,149 | 161.0 / 274.9 / 328.7 | −13.1% | −13.2% | +8.2% |
| `confirm` | 2,918 | 197.1 / 317.5 / 393.6 | 3,149 | 159.7 / 271.6 / 348.9 | −14.5% | −11.4% | +8.2% |
| `read` | 1,464 | 189.7 / 316.4 / 393.2 | 1,583 | 150.3 / 271.8 / 332.2 | −14.1% | −15.5% | +8.4% |
| `total` | 7,360 | 195.2 / 316.8 / 384.8 | 7,941 | 157.7 / 273.1 / 336.9 | −13.8% | −12.4% | +8.2% |
| `auxiliary` | 60 | 40.0 / 74.0 / 255.1 | 60 | 40.4 / 74.0 / 81.3 | — | — | — |

`auxiliary` includes setup calls made outside the traffic window, so it has no limits and no regression checks. Run 2's highest single latency was a 941.2 ms `confirm`, up from 583.3 ms in run 1. Maximum latency is reported but not checked.

The 27 checks in run 2 were:
- p95 and p99 absolute limits for `resolve`, `confirm`, `read` and `total`;
- error and timeout rates for each of those operations;
- p95 and p99 regression checks against the baseline;
- the three generator saturation limits.

The largest observed change was a 15.5% *improvement* in p99. That is well inside the regression tolerances (+25% for p95, +50% for p99, ignoring changes under 20 ms), and both runs stayed below half of each absolute limit. The variation therefore does not contradict the AC15 defaults. Two runs cannot show how far normal variation extends. A later threshold change still requires its own reviewed PR.

The read-only `report trend` over the private archive shows both runs under the baseline key, with run 1 marked as the active baseline. Earlier #228 schema-4 runs appear under their own keys without percentiles.

## Backend context

The optional backend-context file was not filled in for either run, so every signal counts as `not_observed`. Backend monitoring did not inform these verdicts. The simulator's own latency is the primary measurement.

## Evidence preservation and limits

For each run, the report, stage log and host companion were copied over authenticated SSH into a separate owner-only maintainer archive, and their SHA-256 hashes matched the host inventory. The archive also holds:
- the original manifest, release metadata, private profile and safety copies;
- bridge evidence and the recovery record;
- the evaluation output.

Only the baseline and thresholds files are committed. Raw archives remain private.

| Run | Report SHA-256 | Host companion SHA-256 |
| --- | --- | --- |
| Run 1 `97847263` | `fb52994432fec7b36127c06dc383c3ce9c9d64835067a8cbe264e6b175056950` | `eb983f557d92f8cd58c14959968bcaad31c9fcb7188d5cc2287ba3606c758616` |
| Run 2 `7102939c` | `066d9129d66ef0ece1cc53ad7b95073cb007ebc6cb11148e0176352cbeba60ae` | `85cdc9bd4b7edc7412181c2b46e6a0ef1d3350a6837eaf761b4246d6608f0d49` |

These figures describe two bounded five-minute runs of one profile against one Staging deployment from one host. They are regression evidence, not capacity, throughput limits or a production SLO. Thresholds remain documented assumptions, and changing them requires a reviewed PR.
