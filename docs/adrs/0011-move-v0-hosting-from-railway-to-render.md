# Move V0 hosting from Railway to Render

**Status:** accepted (2026-10-29)

This ADR supersedes [ADR 0010](0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md). It also replaces the Railway choice in [ADR 0004](0004-use-railway-for-v0-hosting.md).

## Context and constraints

[ADR 0004](0004-use-railway-for-v0-hosting.md) chose Railway for V0 hosting. [ADR 0010](0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) kept Railway after the GCP evaluation in [#338](https://github.com/TailTag-Game/tailtag/issues/338). TailTag runs Development and Staging on Railway in the US East (Virginia) region. It has no Production environment yet.

ADR 0010 reopens the decision when Railway reliability changes in a way that removes its advantage. The owner reports that this happened:

- Railway went down many times while the team developed TailTag.
- A recent Railway security issue brought these concerns to a head.

The owner wants a host that stays consolidated like Railway. Consolidated means that one provider account holds the API and its database. The team then does not manage a separate account for each part of the stack.

The cancelled hybrid replica in [#352](https://github.com/TailTag-Game/tailtag/issues/352) tested the other direction. It ran the API on Cloud Run, PostgreSQL on Neon, and media on Cloudflare R2. Terraform, a tool that creates cloud resources from code, set them up. The owner stopped it on 2026-10-29 in favor of Render. PR #403 reverted its code. Its lessons stay in the Git history, in commits `7e71e21` to `6096fbd`.

Current constraints that the move must keep:

- Business rules stay server-controlled in the Django modular monolith ([ADR 0005](0005-use-modular-monolith-for-v0.md)).
- PostgreSQL stays the primary database ([ADR 0002](0002-use-postgresql-as-primary-database.md)). Railway Staging runs PostgreSQL 18.
- Clerk stays the player authentication authority ([ADR 0003](0003-use-clerk-for-player-authentication.md)).
- Each environment keeps its own private media bucket and its own media credential.
- Staging stays a controlled production rehearsal, as the [Staging runbook](../development/staging.md) describes.

## Decision

Move TailTag V0 backend hosting from Railway to Render.

Scope and region:

- Move Development and Staging to Render first.
- Design the first Production environment on Render later, under this decision.
- Put all Render resources in the Oregon (US West) region.

Services and plans:

- Use the Render Pro workspace plan.
- Run the API as a Render web service, a Render service that serves HTTP traffic. Use the `0.5c-512mb` plan in Development and in Staging.
- Use Render Postgres, the managed PostgreSQL service of Render, in the same workspace. Use the `0.1c-256mb` plan with PostgreSQL 18 in Development and in Staging.
- Do not turn on Render Postgres high availability in Development or Staging. High availability means a standby database that takes over when the primary fails.

Operations jobs:

- Run migrations as the pre-deploy command of the web service. Render runs this command after the build and before the new version takes traffic.
- Run restore, reset, and reseed as Render one-off jobs. A one-off job is a short task that Render starts through its API, with the build and settings of the web service.
- Use Render cron jobs, the Render service type for scheduled tasks, only after a separate decision. [#336](https://github.com/TailTag-Game/tailtag/issues/336) covers scheduled simulation work.

Other providers:

- Keep media on private Cloudflare R2. TailTag does not plan to move media to Render.
- Keep Clerk and Sentry as they are.

Railway retirement:

- Keep each Railway environment until its Render replacement passes parity checks. Parity checks prove that the Render environment does what the Railway one does. Retire the Railway environment after that.
- Do not start migration work until a tracker issue exists for the move. The first migration task creates it.

The Production design decides the Production plans and whether Production needs high availability.

## Alternatives considered

- Keep Railway, as ADR 0010 decided. The owner did not choose it, because of the repeated outages and the recent security issue.
- Move to the hybrid stack from #352: Cloud Run, Neon, and R2. The owner did not choose it, because it spreads the stack across several provider accounts. That is the opposite of the consolidation goal.
- Move to GCP with Cloud Run and Cloud SQL, as tested in #338. ADR 0010 rejected it. It costs about 2 to 6 times more than Railway at the convention level, by the [GCP hosting comparison](../specs/2026-10-22-gcp-hosting-comparison.md). The same comparison estimates 2 to 4 operator hours per month on GCP, against 1 to 2 on Railway.
- Use the Render Hobby workspace plan. The owner did not choose it. It allows one team member and gives 3 days of PITR and 7 days of logs. It also lacks isolated environments and workspace audit logs.
- Use larger Staging plans to match the #229 baseline from the start. The owner chose the smallest paid plans first.

## Consequences and risks

- Hosting cost rises. Railway Development and Staging used an estimated $3.33 for one cycle, inside the $5 Hobby fee. Render costs about $51 per month: the $25 Pro fee, plus $13 per environment for the web service and the database. Extra database storage costs $0.30 per GB after 1 GB. Bandwidth past the included 25 GB costs $0.15 per GB. Builds and pre-deploy commands use pipeline minutes, the Render measure of build time, and extra minutes cost $5 per 1,000. Prices come from [Render pricing](https://render.com/pricing), read 2026-10-29.
- Point-in-time recovery (PITR) restores a database to an earlier moment. Render Postgres on the Pro workspace keeps 7 days of PITR ([Render backups](https://render.com/docs/postgresql-backups), read 2026-10-29). This closes the PITR gap that ADR 0010 found on Railway.
- Only the Render Enterprise plan offers a contractual uptime SLA, a written promise of service availability. Development and Staging have no SLA. The Production design must decide whether a convention needs one.
- High availability needs a database plan with at least 1 CPU. The standby uses the same plan and storage as the primary, so it about doubles the database cost. Asynchronous copying means a failover can lose a few seconds of writes ([Render high availability](https://render.com/docs/postgresql-high-availability), read 2026-10-29).
- The smallest Staging plans can fall short of the #229 convention baseline of 24.4 requests per second. If the load and tooling check fails, the owner decides whether to raise the Staging plans.
- The move replaces Railway-specific tooling that already has proof on Railway. The [GCP hosting comparison](../specs/2026-10-22-gcp-hosting-comparison.md#railway-features-and-gcp-replacements) lists these parts. They include the Wait for CI deploy gate, the pre-deploy migration step, and the promotion script `scripts/api_staging_promote.py`. They also include the restore and reset paths over Railway SSH and the simulator target rules from #199.
- Render auto-deploy has an "After CI Checks Pass" mode. It replaces Railway Wait for CI, which holds a deploy until the CI checks pass. Render counts a skipped check as passed ([Render deploys](https://render.com/docs/deploys), read 2026-10-29). The API workflow reports a skip for changes that do not affect the backend. The migration work must make sure that Render does not deploy on that skip alone.
- The pre-deploy command runs on its own instance with a 30-minute limit. If it fails, the deploy fails and the previous version keeps serving.
- The readiness check at `/health/ready` tells the host that the API can take traffic. The readiness check, the build argument, and several scripts read Railway identity variables. The owner closed the portability work in #346 and #347 as not planned. The migration work must reopen it or replace it with a Render version.
- [ADR 0007](0007-v0-observability-backend.md) (proposed) names Railway logs. The migration work must update it for Render logs. The Pro workspace keeps logs for 14 days. Sentry stays.
- The region moves from US East (Virginia) to US West (Oregon). Latency, the delay before a response arrives, can rise for players on the US East coast. It can also rise for the simulation host, the machine that sends synthetic player traffic. The load and tooling check measures it.
- Media stays on Cloudflare R2, so Cloudflare stays a separate provider account for media. Consolidation covers the API and the database only.
- During the move, Railway and Render both run. Costs overlap until each Railway environment retires.
- A replica lesson can apply again. TLS encrypts database connections. It also proves the server identity with a certificate from a trusted certificate authority (CA). The psycopg binary package bundles an OpenSSL build without the system CA path, so `sslrootcert=system` failed in the image. Commit `97869d8` set `SSL_CERT_FILE` to fix it. If the API trusts only the system CAs for Render Postgres TLS, the image needs the same setting.

## Validation and rollback

Each environment must pass these parity checks on Render before its Railway environment retires. The tracker issue for the move holds the exact steps.

| Check | What must pass |
|-------|----------------|
| Delivery | A merge to `main` deploys through "After CI Checks Pass". The pre-deploy migration runs. The readiness check and the smoke checks, short end-to-end API tests, pass. |
| Auth and media | The Clerk authenticated smoke passes. A private R2 media upload and read work. |
| Recovery | A practice PITR restore and an application rollback pass on Render Staging. |
| Load and tooling | The simulator reaches Render Staging under the #199 rules. The team measures a load run like the #229 baseline. |

Until a Railway environment retires, rollback is simple. The Railway environment keeps running, and its public address, such as `https://staging.tailtag.app`, can point back to it. After a Railway environment retires, rollback needs a new Railway setup and a data restore.
