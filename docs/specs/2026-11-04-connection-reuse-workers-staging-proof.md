# Connection reuse and Gunicorn workers: Render Staging proof

Issue: [#448](https://github.com/TailTag-Game/tailtag/issues/448). Spec: [refinement comment](https://github.com/TailTag-Game/tailtag/issues/448#issuecomment-6616464702). Code: [PR #449](https://github.com/TailTag-Game/tailtag/pull/449). Operations: [backend dependency health](../operations/backend-dependency-health.md#connection-capacity).

Checkpoint: 2026-11-04 UTC. The maintainer promoted `d98dc3b` to Render Staging and ran two `normal-profile` runs from the simulation host. Both runs passed every stage. Both runs returned the verdict `breached` against the Railway baseline `dac260032cf2`. Throughput rose about four times compared with the last run before #448.

## Release and target

| Binding | Value |
| --- | --- |
| Backend source | `d98dc3b90c41c91c95a325e2647330fc19617a59` (PR #449) |
| Staging promotion | `dep-dbl6smajnfac73ernir0`, deployed `2026-11-03T23:29:29Z`, every outcome `SUCCEEDED` ([receipt](../development/staging-deployments/dep-dbl6smajnfac73ernir0.json)) |
| Staging plans | API `0.5c-512mb`, PostgreSQL `0.1c-256mb`, both in Oregon |
| API runtime | 1 instance, 3 sync workers, `CONN_MAX_AGE` 60 with health checks, `tini` as PID 1 |
| Simulator release | `6b2301b0583d7156eb13ac87bbc47a0c7e2d087b`, image `sha256:0dc5ba0576a97051957fec64d8f0e2b1df93b39b2d3575ee493db9caf7e567b9` |
| Simulation host | DigitalOcean RIC1 (Richmond, Virginia), 2 vCPU, 4 GiB, `linux/amd64` |
| Profile | `tools/simulator/host/normal-profile.json`, unchanged |
| Comparable key | `convention-baseline` v2, plan `dac260032cf2…`, `staging`, `external_host:linux/amd64` |

## Live process checks (AC7)

- The pre-deploy log shows the `PASS` line at `23:30:11Z`.
- In a `render ssh` session on Staging, `/proc/1/comm` printed `tini`. The process list showed one Gunicorn master and three workers of about 105 MB resident memory each.
- After that session ended, a search of the service logs from the promotion until the search found 0 lines with `exited with code`. A control search over the same window found the `PASS` line once, so the search worked.
- PR #449 proved the graceful SIGTERM shutdown under `tini` in a local Docker run. This checkpoint did not observe a live shutdown. The next Staging deploy does that.

## Session controls

The session used one new ed25519 key in `/dev/shm`, named `tailtag-sim-2026-11-03` in the Render Dashboard.

| Control | Condition | Result |
| --- | --- | --- |
| A | No `Host` block | `FAIL_LAUNCHER` |
| B | `Host` block, key not registered | `FAIL_LAUNCHER` |
| C | Key registered | `PASS`, instance `srv-dbhuq2g473hc73967m5g-689b44fb75-nvpw7`, pool `host228` 50 available, 0 leased, 0 quarantined |
| End | Key removed from the Dashboard, `Host` block still present | `FAIL_LAUNCHER` |

At session end the maintainer shredded the key, removed the `Host` block, and made sure that the Dashboard showed no `tailtag-sim-` key.

## Runs (AC8)

`task sim-host-collect` copied both runs into the owner-private archive with size and SHA-256 checks, and wrote both evaluations.

| | Run 1 | Run 2 | Last run before #448 | Railway baseline |
| --- | --- | --- | --- | --- |
| Run ID | `c75e0335-41cc-4871-ae1e-57980a914932` | `5e598978-9ed9-497a-b742-7e18c482ba95` | `be5637e9-532b-4bc3-9619-5b1657f7a667` | `dac260032cf2` |
| Window (UTC) | `01:22:38Z` to `01:31:43Z` | `01:41:27Z` to `01:51:58Z` | | |
| Outcome / correctness | `passed` / `passed` | `passed` / `passed` | `passed` / `passed` | |
| Requests | 6,587 | 6,487 | 1,835 | |
| Rate, total | 21.02 per second | 20.66 per second | 5.22 per second | 24.39 per second |
| p95, total | 525.4 ms | 550.7 ms | 2,555.3 ms | 316.8 ms |
| p99, total | 797.2 ms | 776.4 ms | 3,375.5 ms | 384.8 ms |
| p99, resolve | 824.1 ms | 879.5 ms | 3,375.5 ms | 378.6 ms |
| Error and timeout rate | 0 | 0 | 0 | |
| Verdict | `breached` | `breached` | `inconclusive` | |

Each run broke two absolute limits: the total p99 (limit 770 ms) and the resolve p99 (limit 758 ms). Every p95 stayed inside its absolute limit. Every p95 and p99 regression check returned `regressed`. The generator saturation checks passed, with a peak of about 52% CPU. Both evaluations carry the caveats `image_differs` and `simulator_sha_differs`, because the baseline used an older simulator release.

## Memory (AC4, amended)

The maintainer amended AC4 on 2026-11-04. The 410 MB limit applies to the steady memory of the API workers. Short spikes from simulator relay processes are recorded, not counted as a failure. The API keeps 3 workers.

The Render Dashboard labels its memory unit `MB`. Its grid lines sit at whole hundreds of millions of bytes, so the values are MiB. Values read from the chart are accurate to about 5 MiB.

| Reading | Value |
| --- | --- |
| Container `memory.current` before the runs | 265,564,160 bytes (253 MiB) of 536,870,912 |
| Container `memory.current` after run 1, with an operator shell open | 374,706,176 bytes (357 MiB) |
| Dashboard, idle before the runs | about 248 MiB |
| Dashboard, steady level during and after the runs | about 334 MiB |
| Dashboard, single-sample spikes | about 401 MiB at 01:29Z, 414 MiB at 01:46Z, 418 MiB at 01:52Z |
| Render Events, both run windows | No events: no out-of-memory kill and no restart |

Each relay stage runs `manage.py` over `render ssh`, as a separate Python process in the API container. The spikes match those stages. Two more spikes at 01:39Z and 01:40Z, between the runs, match the operator's own `manage.py shell` calls. Player traffic starts no such process.

## Connections

After run 1, `pg_stat_activity` showed 4 connections to the Staging database. That count includes the counting shell, so the API held 3, one for each worker. The limit is 100.

## Where the time goes

Sentry recorded a transaction for almost every request in both runs. The span data below covers both runs.

| Endpoint | Transactions | Server average | Server p95 | Queries per request | Database time per request | `authenticate` |
| --- | --- | --- | --- | --- | --- | --- |
| `resolve` | 4,982 | 108.6 ms | 286.8 ms | 9.0 | 52.5 ms | 14.9 ms |
| `confirm` | 4,982 | 69.4 ms | 189.5 ms | 5.2 | 28.9 ms | 15.4 ms |
| `GET /api/catches/` | 2,542 | 58.7 ms | 166.2 ms | 4.0 | 22.0 ms | 14.1 ms |

Each query took about 5.6 ms on average.

Five `curl` calls from the simulation host to `/health/identity` measured the network cost. TCP connect took about 5 ms and TLS about 19 ms in total, because both end at a nearby edge. The full request took 131 ms to 199 ms. Sentry shows about 6 ms of server time for that endpoint. So each request from this host carries about 110 ms to 180 ms of travel to Oregon. The Railway baseline ran in Virginia, near the host, without that cost.

The API CPU stayed at its 0.5 CPU limit during both runs. Requests therefore waited for a free worker. The gap between the client p95 and the server p95 for `resolve` is about 310 ms. About half of it is network travel, and the rest is that wait.

## Outcome (AC9)

Neither run is `acceptable`. A follow-up issue covers the `resolve` query count and the `authenticate` cost. [#411](https://github.com/TailTag-Game/tailtag/issues/411) AC13 returns to the maintainer for the plan decision.

On 2026-11-04 the maintainer chose to move Staging and Production to an eastern Render region and to keep Development in Oregon. A separate issue covers that move and the ADR that supersedes the Oregon clause of [ADR 0011](../adrs/0011-move-v0-hosting-from-railway-to-render.md). The new Render baseline for #411 AC14 waits for that move.
