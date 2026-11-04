# Run Staging and Production in the Render Virginia region

**Status:** accepted (2026-11-04)

This ADR supersedes the region clause of [ADR 0011](0011-move-v0-hosting-from-railway-to-render.md). The rest of ADR 0011 stays in force.

## Context and constraints

[ADR 0011](0011-move-v0-hosting-from-railway-to-render.md) moved V0 hosting to Render and put all Render resources in Oregon (US West). It warned that latency can rise for players on the US East coast and for the simulation host. Latency is the delay before a response arrives. The simulation host is the machine that sends synthetic player traffic. It runs in DigitalOcean RIC1, in Richmond, Virginia.

The [#448 Staging proof](../specs/2026-11-04-connection-reuse-workers-staging-proof.md) measured that cost. Each request from the simulation host to Oregon carries about 110 ms to 180 ms of travel. Railway Staging ran in Virginia without that cost.

The largest US furry conventions are in Pittsburgh, Atlanta, Chicago, Orlando, and Dallas. All five are east of the Rocky Mountains. On 2026-11-04 the owner chose an eastern region for Staging and Production. Development stays in Oregon, near the owner.

Render offers two eastern US regions: Ohio and Virginia. Render does not change the region of an existing service or database ([Render regions](https://render.com/docs/regions), read 2026-11-04). Each region has its own private network.

Constraints that this decision keeps:

- The plans, the PostgreSQL version, and the operations model from ADR 0011 stay the same.
- Media stays on Cloudflare R2. Clerk and Sentry stay as they are.
- The Production design still decides the Production plans and high availability.

## Region probe

The owner approved the comparison method and the decision rule before the probe ran ([#452 refinement](https://github.com/TailTag-Game/tailtag/issues/452#issuecomment-6622142436)). The rule picks the region with the lower median across the five convention cities. A difference of 5 ms or less counts as a tie, and a tie goes to Virginia.

Method:

- One temporary free Render web service ran in each region. Each served `traefik/whoami:v1.12.0`.
- The probe ran from 2026-11-04 04:09Z to 06:04Z. Both services were deleted at 06:10Z.
- Each sample is the time from the end of the TLS setup to the first response byte. Render web services sit behind the Cloudflare edge. A plain connect time measures only the nearest edge, so this value measures the trip to the region.
- The Mac and the simulation host sent 50 warm requests per region over one kept-alive connection.
- [Globalping](https://globalping.io) probes in the five cities sent 52 requests per city and region. Each probe opened a new connection, but the timing starts after TLS.
- The simulation host also timed 50 TCP connects to each Render SSH gateway, `ssh.<region>.render.com`.

Medians in milliseconds:

| Source | Ohio | Virginia |
|--------|------|----------|
| Pittsburgh | 177.5 | 50.5 |
| Atlanta | 102.0 | 53.0 |
| Chicago | 187.0 | 83.5 |
| Orlando | 206.5 | 86.5 |
| Dallas | 141.5 | 91.0 |
| Five-city median | 177.5 | 83.5 |
| Simulation host, warm request | 50.5 | 19.8 |
| Owner Mac, warm request | 83.0 | 103.5 |

| Simulation host to SSH gateway | Oregon | Ohio | Virginia |
|--------------------------------|--------|------|----------|
| TCP connect median (ms) | 67.6 | 17.1 | 6.2 |

Under the rule, Virginia wins.

The Ohio city results overstate the gap. Ohio alternated between fast and slow periods. In a slow period, every city was slow at the same time. Virginia stayed steady through the whole run. The round medians show the pattern:

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|-------|---|---|---|---|---|---|---|---|---|----|----|----|----|
| Ohio (ms) | 110 | 276 | 286 | 78 | 72 | 89 | 112 | 262 | 286 | 76 | 614 | 345 | 192 |
| Virginia (ms) | 77 | 60 | 69 | 70 | 62 | 79 | 116 | 62 | 66 | 64 | 55 | 69 | 69 |

The slow periods most likely came from the free Ohio instance or the edge path to Ohio, not from distance. If only the Ohio samples under 150 ms count, the five-city medians are 72 ms for Ohio and 66 ms for Virginia. Virginia still wins four of the five cities. Chicago favors Ohio. The simulation host favors Virginia by about 30 ms per request in every comparison.

## Decision

- Run Render Staging in the Virginia region (`virginia` in `render.yaml`).
- Create Render Production in the Virginia region when the Production design starts.
- Keep Render Development in the Oregon region.

Everything else in ADR 0011 stays the same.

## Alternatives considered

- Ohio. It is closer to Chicago and Pittsburgh on a map. It lost under the agreed rule. It also loses about 30 ms per request for the simulation host.
- Keep Staging in Oregon. Every request from the simulation host keeps about 110 ms to 180 ms of travel. Load results stay hard to compare with the Railway baseline from Virginia.
- Move Development to Virginia too. The owner keeps Development in Oregon, near the owner. Development has no player traffic.

## Consequences and risks

- Development and Staging run in different regions, so they cannot share a private network. Each environment already uses network isolation, so nothing depends on that today.
- Staging needs new resources. [#452](https://github.com/TailTag-Game/tailtag/issues/452) creates a new API service and a new database in Virginia, rebuilds the Staging data, moves `staging.tailtag.app`, and removes the Oregon resources.
- Every Staging pin that fails closed changes. The pins cover the service, its host name, the database, the reset settings, and the SSH gateway with its host key. The Virginia gateway key fingerprint is `SHA256:NCpSwboPnqL/Nvyy2Qc8Kgzpc3P/f3w5wDphhc+UZO0` ([Render SSH](https://render.com/docs/ssh), read 2026-11-04).
- Staging point-in-time recovery history starts again at the creation of the new database.
- Hosting cost rises for a short time. Both regions run until the rollback window in #452 ends. The overlap costs about $13 per month, prorated.
- The owner sees more latency on Staging from the US West coast. The probe measured about 20 ms more from the owner Mac to Virginia than to Ohio.
- Load results from the simulation host against Virginia Staging become comparable with the Railway baseline, which also ran in Virginia.

## Validation and rollback

The [#452](https://github.com/TailTag-Game/tailtag/issues/452) acceptance criteria hold the exact checks. Staging in Virginia must pass these checks before the Oregon resources go away:

- A promotion succeeds, and `/health/ready` returns 200 on `staging.tailtag.app`.
- The rebuilt data matches the Oregon row counts, and the reconcile check passes.
- The simulator relays and a host session work against Virginia.
- The record shows the network cost from the simulation host to Virginia.

Until the Oregon Staging resources go away, rollback is to point `staging.tailtag.app` back at the Oregon service. After their removal, a return to Oregon needs new resources and a data rebuild.
