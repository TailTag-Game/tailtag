# GCP hosting comparison (#344)

**Status:** research record, dated 2026-10-22

**Related issues:** [#344](https://github.com/TailTag-Game/tailtag/issues/344) (this comparison), parent [#338](https://github.com/TailTag-Game/tailtag/issues/338)

**Decision record:** [ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) (proposed)

This document compares the Google Cloud Platform (GCP) hosting test with current Railway hosting. GCP is a cloud host from Google. The test ran the current API on Cloud Run, the Google service that runs containers, with Cloud SQL, the Google managed PostgreSQL service. The test used synthetic data only. It did not change Railway and it does not start a move.

Measured figures say "measured". Every other figure is an estimate. All prices are monthly US dollars before tax.

## Test results

Each test is PASS, FAIL, or NOT EXERCISED. NOT EXERCISED means that the test did not run, with the reason given. A re-test shows the first result and the later result.

| Issue | Test | Result | Evidence | Limits |
|-------|------|--------|----------|--------|
| #339 | Separate test project, APIs, service accounts | PASS | [#339 results](https://github.com/TailTag-Game/tailtag/issues/339#issuecomment-6329372118) | None. |
| #339 | Runtime account reads only named secrets | PASS | [#339 follow-up](https://github.com/TailTag-Game/tailtag/issues/339#issuecomment-6333501579) | None. |
| #339 | Budget alerts | Configuration PASS. Live alert NOT EXERCISED. | [#339 results](https://github.com/TailTag-Game/tailtag/issues/339#issuecomment-6329372118) | No threshold was reached. The budget counts spend after credits, so it cannot alert during the free trial. |
| #339 | Operator holds Billing Account Viewer | Approved deviation | [#339 follow-up](https://github.com/TailTag-Game/tailtag/issues/339#issuecomment-6333501579) | The operator holds Billing Account Administrator, because the project uses the operator's own billing account. |
| #340 | Image build and storage, port, liveness, identity, logs, startup failure, secrets | PASS | [#340 results](https://github.com/TailTag-Game/tailtag/issues/340#issuecomment-6329380787) | None. |
| #340 | Readiness on Cloud Run | FAIL, as designed | [#340 results](https://github.com/TailTag-Game/tailtag/issues/340#issuecomment-6329380787) | Readiness requires Railway identity variables (#346). |
| #341 | PostgreSQL 17 instance, IAM database login, migration job, repeat run, persistence, connection limit | PASS | [#341 results](https://github.com/TailTag-Game/tailtag/issues/341#issuecomment-6330384817) | No load test. |
| #341 | Database not public | Approved deviation | [#341 closing note](https://github.com/TailTag-Game/tailtag/issues/341#issuecomment-6330459134) | The instance keeps a public endpoint with no authorized networks. Connections use IAM login through the Cloud SQL Auth Proxy. |
| #341 | Readiness with a working database | NOT EXERCISED | [#341 results](https://github.com/TailTag-Game/tailtag/issues/341#issuecomment-6330384817) | Blocked by the identity rule (#346). |
| #342 | Clerk with synthetic users, access rules, private media | PASS | [#342 results](https://github.com/TailTag-Game/tailtag/issues/342#issuecomment-6331112124) | A Clerk session token lasts about 60 seconds. Media ran on Google Cloud Storage through its S3 interface, which needed two checksum settings. |
| #342 | Media deletion check | First run not recorded. Re-test PASS. | [#342 re-test](https://github.com/TailTag-Game/tailtag/issues/342#issuecomment-6346028026) | None. |
| #342 | Deletion permission rules | Not applicable | [#342 follow-up](https://github.com/TailTag-Game/tailtag/issues/342#issuecomment-6333502097) | The fursuit API has no delete route. |
| #342 | `task api-smoke` | FAIL on readiness only | [#342 results](https://github.com/TailTag-Game/tailtag/issues/342#issuecomment-6331112124) | Readiness returns 503 (#346). `task api-auth-smoke` NOT EXERCISED, because its rules allow only an approved Development API. |
| #343 | Normal rollout, application rollback, bounded traffic, measurements | PASS | [#343 results](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6332318517) | 600 requests in 16 seconds. Not a reliability proof. |
| #343 | Authenticated read and API read of restored data | First run NOT EXERCISED, because no Clerk token was available. Follow-up PASS. | [#343 follow-up](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6332623735) | One synthetic user. |
| #343 | Failed revision rejected | First run FAIL: about 8 seconds of live traffic. Re-test PASS after #348. | [#343 results](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6332318517), [#343 re-test](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6346027673) | Proven for a wrong instance name only. |
| #343 | Backup restore to a separate instance | PASS: 14 minutes | [#343 results](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6332318517) | Row counts only. |
| #343 | Automated backups and point-in-time recovery (PITR) | First run used an on-demand backup. Re-test PASS: PITR clone in 25 minutes, all 25 table counts match. | [#343 re-test](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6333501943) | No writes happened between the backup and the restore time. |
| #343 | Simulator traffic | NOT EXERCISED | [#343 follow-up](https://github.com/TailTag-Game/tailtag/issues/343#issuecomment-6333501750) | The simulator allows only local and Staging targets (#199). |
| #348 | Proxy startup probe and container order | PASS | [#348 results](https://github.com/TailTag-Game/tailtag/issues/348#issuecomment-6346027341) | None. |

Measured runtime behavior on GCP:

- A cold start is the time before a new instance serves its first request. It took 6.3 to 14.8 seconds in #343 and 8.1 to 9.1 seconds in #348, with minimum instances set to 0.
- Steady server-side latency was 5 ms at p50 and 15 ms at p95 on the probe paths (#343).
- An application rollback moved traffic in about 4 seconds (#343).

## Workload assumptions

These numbers are assumptions. Real player numbers do not exist yet. The convention peak uses the one measured convention-shaped load: the #229 convention baseline on Railway Staging, at 24.4 requests per second, p95 317 ms, and no errors.

| Setup | Players | Requests | Database | Media |
|-------|---------|----------|----------|-------|
| Small beta | Up to 100 | About 1 per second on average, 5 at peak. About 2.6 million per month. | Under 1 GB | Under 5 GB |
| Convention-ready | 1,000 to 2,000 active during a 3 to 4 day event | Peak about 25 per second. The event adds 1.2 to 2.8 million requests to one month of beta load. | Under 5 GB | 20 to 50 GB |

Other assumptions for both setups:

- Region: GCP us-central1, where the test ran. The Railway region is not confirmed, and Railway prices do not change by region.
- Cloud Run size: the tested shape, an API container with 1 vCPU and 512 MiB plus a proxy container with 0.25 vCPU and 256 MiB. Together that is 1.25 vCPU and 0.75 GiB, or about $0.000032 per active instance-second at request-based prices.
- Instance time: each request keeps an instance active for 0.1 to 0.3 seconds, with little overlap at beta load.
- Logs: under 50 GiB per month on GCP, inside the free allotment.
- Support: neither estimate includes paid support. GCP technical support is a paid add-on, and its price was not checked. Railway Pro offers Business Class Support as an add-on. Railway states no support level for Hobby.

## Service levels compared

Each setup compares a matched pair. The pairs differ in what they include, so the table lists each gap.

| Item | Beta: Railway Hobby | Beta: GCP | Convention: Railway Pro | Convention: GCP |
|------|---------------------|-----------|-------------------------|-----------------|
| Compute | Always-on service | Cloud Run, minimum 0 instances | Always-on service, 2 replicas | Cloud Run, minimum 1 instance |
| Database | One PostgreSQL service on a volume | Cloud SQL shared-core, zonal | One PostgreSQL service on a volume | Cloud SQL 1 vCPU and 3.75 GB, regional high availability (HA) |
| Database failover | None | None | None documented | Automatic failover to a second zone |
| Backups | None on Hobby (September 2026 check, not reconfirmed) | Automated, 7 retained | Scheduled backups (plan not confirmed) | Automated, 7 retained |
| PITR | None | Yes, 7 days of logs | None documented | Yes |
| SLA | None stated | None: shared-core and zonal instances are excluded | None stated | Cloud SQL 99.95% |
| Log history | 7 days | 30 days by default | 30 days | 30 days by default |
| Cold start | None | 6 to 15 seconds after idle | None | None while one instance stays warm |

## Prices used

GCP prices come from the Cloud Billing Catalog API for us-central1, effective 2026-10-22. Railway prices come from the [Railway pricing page](https://railway.com/pricing) and the owner's usage page, read 2026-10-22. R2 prices come from [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/), read 2026-10-22.

| Item | Price |
|------|-------|
| Cloud Run CPU, request-based billing | $0.000024 per vCPU-second |
| Cloud Run memory, request-based billing | $0.0000025 per GiB-second |
| Cloud Run idle minimum instance | $0.0000025 per vCPU-second and per GiB-second |
| Cloud Run requests | First 2 million free, then $0.40 per million |
| Cloud Run internet egress, North America | First 1 GiB free, then $0.105 per GiB |
| Cloud SQL zonal shared-core: micro, small | $0.0105 per hour, $0.035 per hour |
| Cloud SQL zonal dedicated: vCPU, RAM | $0.0413 per vCPU-hour, $0.007 per GiB-hour |
| Cloud SQL regional HA dedicated: vCPU, RAM | $0.0826 per vCPU-hour, $0.014 per GiB-hour |
| Cloud SQL storage: zonal SSD, zonal HDD, regional SSD | $0.17, $0.09, $0.34 per GiB-month |
| Cloud SQL backups | $0.08 per GiB-month |
| Artifact Registry | First 0.5 GiB free, then $0.10 per GiB-month |
| Cloud Logging | First 50 GiB free, then $0.50 per GiB |
| Secret Manager | 6 versions and 10,000 accesses free, then $0.06 per version and $0.03 per 10,000 accesses |
| Railway plans | Hobby $5 with $5 of usage included. Pro $20 with $20 of usage included. |
| Railway usage | $0.000231 per GB-minute of RAM, $0.000463 per vCPU-minute, $0.05 per GB of egress, $0.000003 per GB-minute of volume |
| Cloudflare R2 | $0.015 per GB-month, no egress fee, first 10 GB free |

The Cloud Run free tier for CPU and memory was not confirmed in the catalog. The estimates do not subtract it.

## Measured costs

| Host | Figure | Source |
|------|--------|--------|
| Railway | Development and Staging together: $1.96 of usage from October 7 to 22, and an estimated $3.33 for the full cycle. RAM is 95% of it. The Hobby fee of $5 covers this usage. | Owner's usage page, read 2026-10-22 |
| GCP | Test project, October 1 to 22: $0.13 of usage (Cloud Run $0.07, Cloud SQL $0.06). Free trial credits paid all of it. | Owner's billing report, read 2026-10-22 |

The GCP figure covers about 1 to 2 days of test use, and billing data lags. It is not a monthly figure. Neither figure includes Production, because TailTag has no Production environment.

## Monthly cost estimates

Each estimate covers one Production environment. Media stays on Cloudflare R2 on both hosts, so media costs the same on both: under $1 for the beta and under $1 for the convention month, after the R2 free 10 GB. The GCP test stored media in Google Cloud Storage through its S3 interface, which needed the settings `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` set to `when_required`. R2 was not tested on GCP. Presigned reads go straight to R2, so neither host pays media egress. Clerk and Sentry also cost the same on both hosts and are left out.

### Small beta

| Line | Railway Hobby | GCP |
|------|---------------|-----|
| Compute | RAM 0.35 to 0.8 GB and CPU 0.05 to 0.2 vCPU on average: $5 to $12 | 2.6 million requests at 0.1 to 0.3 seconds of instance time each, for the API and proxy containers: $8 to $25 |
| Requests | Included | $0 to $0.25 |
| Database | Included in compute above. Volume 1 to 5 GB: under $1 | Shared-core micro to small, with 10 GiB storage: $9 to $28 |
| Backups | Not available on Hobby (September 2026 check, not reconfirmed) | Under $0.50 |
| Egress | About 5 GB: $0.25 | About 5 GB: $0 to $0.50 |
| Logs, images, secrets | Included | Under $0.50 |
| Plan fee and credit | $5 fee, with $5 of usage included across the workspace | None. The free trial credit is a one-time $300. |
| Free tiers applied | None | First 2 million requests, first 1 GiB of egress, 50 GiB of logs, 0.5 GiB of images, and 6 secret versions. The Cloud Run CPU and memory free tier is not subtracted. |
| Total | $5 to $13 | $17 to $55 |

### Convention-ready month

| Line | Railway Pro | GCP |
|------|-------------|-----|
| Compute | Two API replicas with 0.5 to 1 GB each, 0.1 to 0.4 vCPU on average: $12 to $28 | One warm minimum instance: $13. Active time of 0.5 to 1.5 million instance-seconds: $16 to $48. |
| Requests | Included | $1 to $1.50 |
| Database | PostgreSQL with 1 to 2 GB RAM and 0.1 to 0.3 vCPU: $12 to $26. Volume 5 to 20 GB: $1 to $3. | Regional HA, 1 vCPU and 3.75 GB: $99. Regional SSD 10 to 20 GiB: $3 to $7. |
| Backups | Price not confirmed. Estimated at the volume rate: $1 to $6 | $1 to $2 |
| Egress | About 10 GB: $0.50 | About 10 GB: $1 |
| Logs, images, secrets | Included | Under $1 |
| Plan fee and credit | $20 fee, with $20 of usage included | None |
| Free tiers applied | None | Same as the beta. The Cloud Run CPU and memory free tier is not subtracted. |
| Total | $27 to $64 | $135 to $173 |

The GCP total buys more. It includes database failover, PITR, and an SLA, and Railway offers none of these. Without HA, a zonal dedicated Cloud SQL instance costs about $51 to $53 for the database line, and the GCP total drops to about $84 to $120.

Non-production environments add cost on both hosts. On Railway, Development and Staging measured an estimated $3.33 for the current cycle. On GCP, each extra environment adds at least one Cloud SQL instance, from about $9 per month.

## Comparison

| Area | Railway | GCP | Unknowns |
|------|---------|-----|----------|
| Security | Workspace-wide access. The Hobby audit log keeps 48 hours. The database password sits in `DATABASE_URL`. | Per-workload service accounts, Secret Manager, and IAM database login with no stored password. Findings: the runtime account also holds `roles/cloudsql.instanceUser`, the migration account can read the Django secret key and both media keys, and the database keeps a public endpoint with no authorized networks. | None. |
| Reliability | No SLA stated. One PostgreSQL service with no documented failover. | Cloud SQL SLA of 99.95% only for regional HA dedicated instances. A failed revision now stops before it takes traffic (#348). | Cloud Run SLA percentage not confirmed. |
| Recovery | Rollback by redeploying an earlier deployment (#206). The full Staging rehearsal is open (#241). Restore proof uses a logical dump over SSH (#207). No PITR. | Traffic rollback in about 4 seconds. Backup restore in 14 minutes. PITR clone in 25 minutes. | Exact restore-to-the-second behavior was not proven. |
| Scaling | Manual replicas. The workspace plan shows up to 8 vCPU and 8 GB. | Automatic scaling from 0 to a set maximum. 3 instances served 600 requests in 16 seconds. | Neither host was tested at convention load. Railway was tested at 24.4 requests per second. |
| Logs | Railway logs plus Sentry (ADR 0007). 7 days on Hobby, 30 on Pro. | Cloud Logging plus Sentry. 30 days by default, 50 GiB free. | None. |
| Maintenance | Few settings. Railway applies platform updates. | Cloud SQL maintenance windows, proxy version updates, IAM review, revision cleanup, and budget care. | None. |
| Operator time, monthly | 1 to 2 hours (estimate) | 2 to 4 hours (estimate) | No time was recorded during operations. |

### Test findings that affect operations

- A Cloud Run revision deployed with no traffic does not start an instance. Cloud Run marks it ready without running the startup probe. A real check needs traffic or a tag.
- A failed revision kept starting new instances about every 30 seconds until it was deleted. Cloud Run does not let an operator delete the latest created revision.
- With the proxy connection test on, a new instance cannot start while Cloud SQL is down. Running instances keep serving.
- The test budget counts spend after credits. During the free trial, it cannot alert.

## Railway features and GCP replacements

| Railway feature in use | GCP replacement | Work (estimate) | Migration risk |
|------------------------|-----------------|-----------------|----------------|
| GitHub autodeploy with Wait for CI (Development) | GitHub Actions builds the image, pushes it to Artifact Registry, and deploys to Cloud Run with workload identity federation. | 12 to 24 hours | A new deploy credential path from GitHub to GCP. |
| Pre-deploy migration command | A Cloud Run job runs migrations before traffic moves. #341 proved the job. The Staging command `config.replacement_migrate` needs Railway variables. | 4 to 8 hours | The deploy script must order the job before the traffic move. |
| Readiness health check as the deploy gate | Cloud Run startup probe, plus a readiness rule that works off Railway (#346). | 4 to 8 hours (#346) | Readiness has never passed on GCP. |
| Railway identity variables | Cloud Run sets `K_SERVICE`, `K_REVISION`, and `K_CONFIGURATION`. A neutral identity source replaces the Railway names (#346). | Included in #346 | Health, identity, target binding, and scripts all read the Railway names. |
| `RAILWAY_GIT_COMMIT_SHA` build argument | A neutral build argument (#347). The test passed the value through the old name. | 1 to 3 hours (#347) | Low. |
| Railway PostgreSQL (the restore drill uses version 18 tools) | Cloud SQL PostgreSQL, with IAM login through the proxy sidecar. The test used version 17. | 4 to 8 hours, plus socket URL support if wanted (#347) | Version 18 on Cloud SQL was not confirmed. A major version change needs its own check. |
| Backups (not on Hobby at the September 2026 check) and the logical-dump restore drill | Cloud SQL automated backups and PITR. | 2 to 4 hours | Low. Proven in #343. |
| Railway logs | Cloud Logging. Sentry stays. | 2 to 4 hours | ADR 0007 names Railway logs, so it needs an update. |
| Development and Staging environments | Separate services and Cloud SQL instances per environment, or one project per environment. | Included in setup below | Each environment adds database cost. |
| Promotion tooling (`scripts/api_staging_promote.py`, Railway GraphQL API) | A rewrite against the Cloud Run Admin API. | 8 to 16 hours | The promotion contract (#202) needs a new proof. |
| Railway SSH for restore, reset, and reseed | Cloud Run jobs, as used in #341 and #343. | 8 to 16 hours | The guarded scripts need new target checks. |
| Public Staging origin | A Cloud Run URL or a mapped domain, with public ingress for player traffic. The test used private IAM access. | 2 to 4 hours | Allowed hosts. Tagged revision URLs stay unsupported (#349). |
| Simulator target rules (#199) | An approved GCP target with the same safety rules as Staging. | 4 to 8 hours | The rules must not get weaker. |
| Project, IAM, secrets, and budget setup for three environments | Repeatable setup from this runbook. | 16 to 32 hours | Manual setup drift. |

One-time migration work totals about 67 to 135 hours (estimate). Media on R2, Clerk, and Sentry need no migration work.

## Recommendation

Keep Railway for V0, including the first Production design. [ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) records the proposal and the triggers that reopen the question.

The reasons, from the evidence above:

- The API runs on GCP with no application change except the readiness identity rule. Compatibility does not decide the question.
- At matched service levels, GCP costs about 2 to 6 times more for the convention month. Its extra cost buys database failover, PITR, and an SLA.
- A move costs about 67 to 135 hours of one-time work, and it replaces delivery, promotion, and recovery tooling that already has proof on Railway.
- Railway lacks PITR, database failover, and a stated SLA. These are real gaps for a convention. Before Production, TailTag needs a plan for them, for example Railway Pro backups and a tested restore drill.

## Open questions

- Railway region: not confirmed. Railway prices do not change by region.
- Railway backups: which plan includes them, and their price. A September 2026 check showed backups as a Pro feature.
- Cloud Run free tier for CPU and memory, and the Cloud Run SLA percentage.
- PostgreSQL 18 on Cloud SQL.
- Real beta and convention numbers. They can replace the workload assumptions above.

## Cleanup

The GCP test project still exists while this document is in review. After owner approval, the operator deletes it with the runbook steps and deletes the Clerk test application. #344 records the result.
