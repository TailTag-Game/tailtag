# Move V0 hosting from Railway to Render

**Status:** proposed (2026-10-29)

This ADR supersedes [ADR 0010](0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) when the owner accepts it. It also replaces the Railway choice in [ADR 0004](0004-use-railway-for-v0-hosting.md).

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

- Move Development and Staging to Render first.
- Design the first Production environment on Render later, under this decision.
- Run the API as a Render web service, a Render service that serves HTTP traffic.
- Use Render Postgres, the managed PostgreSQL service of Render, in the same Render workspace.
- Put all Render resources in the Oregon (US West) region.
- Keep media on private Cloudflare R2 for now. Render Object Storage is in early access ([Render object storage](https://render.com/object-storage), read 2026-10-29). A separate decision can move media to Render after it is generally available.
- Keep Clerk and Sentry as they are.
- Keep each Railway environment until its Render replacement passes parity checks. Parity checks prove that the Render environment does what the Railway one does. Retire the Railway environment after that.

This decision does not choose Render instance plans, the Render workspace plan, the Render Postgres plan, or the service types for operations jobs. The migration work decides them.

Do not start migration work until the owner accepts this ADR and a tracker issue exists for the move.

## Alternatives considered

- Keep Railway, as ADR 0010 decided. The owner did not choose it, because of the repeated outages and the recent security issue.
- Move to the hybrid stack from #352: Cloud Run, Neon, and R2. The owner did not choose it, because it spreads the stack across several provider accounts. That is the opposite of the consolidation goal.
- Move to GCP with Cloud Run and Cloud SQL, as tested in #338. ADR 0010 rejected it. It costs about 2 to 6 times more than Railway at the convention level, by the [GCP hosting comparison](../specs/2026-10-22-gcp-hosting-comparison.md). The same comparison estimates 2 to 4 operator hours per month on GCP, against 1 to 2 on Railway.

## Consequences and risks

- The move replaces Railway-specific tooling that already has proof on Railway. The [GCP hosting comparison](../specs/2026-10-22-gcp-hosting-comparison.md#railway-features-and-gcp-replacements) lists these parts. They include the Wait for CI deploy gate, the pre-deploy migration step, and the promotion script `scripts/api_staging_promote.py`. Wait for CI holds a deploy until the CI checks pass. They also include the restore and reset paths over Railway SSH and the simulator target rules from #199.
- The readiness check, the build argument, and several scripts read Railway identity variables. The owner closed the portability work in #346 and #347 as not planned. The migration work must reopen it or replace it with a Render version.
- [ADR 0007](0007-v0-observability-backend.md) (proposed) names Railway logs. The migration work must update it for Render logs. Sentry stays.
- The region moves from US East (Virginia) to US West (Oregon). Latency, the delay before a response arrives, can rise for players on the US East coast. It can also rise for the simulation host, the machine that sends synthetic player traffic. The migration work must measure it against the #229 convention baseline.
- Render Postgres offers point-in-time recovery (PITR), the restore of a database to an earlier moment. Render gives 3 days on a Hobby workspace and 7 days on a Pro or higher workspace. It gives none on the Free compute plan ([Render backups](https://render.com/docs/postgresql-backups), read 2026-10-29). This can close the PITR gap that ADR 0010 found on Railway. The plan choice decides whether it does.
- Media stays on Cloudflare R2, so consolidation is partial until media moves. The Cloudflare account and the R2 credentials stay in use.
- During the move, Railway and Render both run. Costs overlap until each Railway environment retires.
- A replica lesson can apply again. TLS encrypts database connections and checks the server certificate against trusted certificate authorities (CAs). The psycopg binary package bundles an OpenSSL build without the system CA path, so `sslrootcert=system` failed in the image. Commit `97869d8` set `SSL_CERT_FILE` to fix it. If the API checks Render Postgres TLS against system CAs, the image needs the same setting.

## Open questions

- Which Render workspace plan, web service instance type, and Render Postgres plan TailTag uses, and their monthly cost.
- Whether a convention needs Render Postgres high availability, and which plan includes it. High availability means a standby database that takes over when the primary fails.
- Which Render service types run the operations jobs: migrations, restore, reset, and reseed.
- Whether Render Postgres supports PostgreSQL 18, to match Railway Staging.
- Which checks prove parity for each environment before Railway retires.
- When media moves to Render Object Storage, if it does.
- Whether the ADR links a public record of the Railway security issue.
- The tracker issue for the move. The owner creates it after the review of this ADR.

## Validation and rollback

The tracker issue for the move defines the parity checks for each environment. Each check must pass on Render before the matching Railway environment retires.

Until a Railway environment retires, rollback is simple. The Railway environment keeps running, and its public origin can point back to it. After a Railway environment retires, rollback needs a new Railway setup and a data restore.

When the owner accepts this ADR, change the status here to accepted. Mark ADR 0010 as superseded by this ADR in the same change.
