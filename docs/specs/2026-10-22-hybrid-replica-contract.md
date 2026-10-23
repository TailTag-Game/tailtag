# Hybrid replica inventory and contract (#353)

Status: draft for owner approval, dated 2026-10-22

Related issues: [#353](https://github.com/TailTag-Game/tailtag/issues/353) (this contract), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352)

Decision record: [ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) stays in force. This contract does not approve a hosting move.

This document records what current Railway Staging is and what the hybrid replica must prove. The hybrid replica is an isolated copy of Staging on Cloud Run, Neon, Cloudflare R2 and a separate Clerk application. Children 2 to 9 (#354 to #361) build and test the replica against this contract. No child starts dependent implementation before the owner approves this contract (AC9).

Each requirement result is PASS, FAIL or NOT_EXERCISED. NOT_EXERCISED means that the test did not run, with the reason given. A safe negative result can complete an investigation. It cannot prove a working replica.

## 1. Source and baseline (AC1)

| Item | Value |
| --- | --- |
| Repository SHA for this inventory | `eeaf7edcf44ea1fecec71da1f31cd1f487e1a20a` (`main`, 2026-10-22) |
| Staging generation | Replacement generation, canonical since the 2026-09-24 rebuild ([Staging runbook](../development/staging.md)) |
| Active Staging deployment | Source `e8aedd0d2b4e0e0787edf6bcafc7fbcbb95d4902`, deployment `9359c0a2-4915-42cd-9994-521ce7bc740e` |
| Deployment receipt | [9359c0a2 receipt](../development/staging-deployments/9359c0a2-4915-42cd-9994-521ce7bc740e.json), promoted 2026-10-07 with every gate SUCCEEDED |
| Live observation | 2026-10-23T03:45:28Z. The public, credential-free `/health/identity` returned the same source, deployment and `environment=staging`. `/health/ready` returned 200. |
| Last configuration and ownership readback | [2026-09-28 replacement parity readback](../development/staging.md#2026-09-28-replacement-parity-readback) |
| Performance baselines | `convention-baseline-v2` and `convention-soak-v2` in [`tools/simulator/baselines/`](../../tools/simulator/baselines/) |

The live observation is a shared public origin read, not a fresh image attestation. The checked-out repository SHA is not the deployed SHA.

Unresolved drift:

- D-1: `main` is 34 commits ahead of the Staging source. API changes include `c1c1862` (#330, native Clerk session tokens) and `3c41c14` (#327, OpenAPI contract). Staging has had no promotion since 2026-10-07. The replica will run a newer source than Railway Staging. Child 9 (#361) must state this source difference in every Railway comparison. This workstream does not promote Railway Staging.
- D-2: Railway Staging runs PostgreSQL 18, from an owner readback on 2026-10-22. The restore drill also requires PostgreSQL 18. CI and Compose still use `postgres:17`. This workstream records that gap and does not change CI. The Neon project uses PostgreSQL 18. The #354 capability check makes sure that Neon Launch offers it.
- D-3: The pre-deploy migration command and the health check path live in Railway service settings, not in the repository. The [API README](../../services/api/README.md) documents them. No fresh settings readback exists.

## 2. Current Staging inventory (AC2)

Environment variable names only. This document records no values.

| Area | Current Staging |
| --- | --- |
| Railway plan and region | Hobby plan. US East (Virginia), confirmed by the owner on 2026-10-22. |
| Services | `api` (Django 6.0, Python 3.13, Gunicorn, built from `services/api/Dockerfile`) and `Postgres` in the replacement project, `staging` environment |
| Database | One Railway PostgreSQL service on a Staging-owned volume. No extensions are created by migrations. PostgreSQL 18 (D-2). The API reaches it through the environment-local `Postgres` reference. |
| Backups and restore | No Railway backups on Hobby. Recovery proof is the #207 logical dump through a `railway connect` tunnel into a local PostgreSQL 18 container ([restore contract](2026-09-22-v0-postgresql-backup-restore.md)). No point-in-time restore. |
| Storage | One private Staging R2 bucket with a single-bucket Object Read & Write token. The R2 account endpoint is shared platform infrastructure. |
| Authentication | Dedicated Clerk application `TailTag Staging Replacement`, Production instance. Authorized parties: the Account Portal origin and the simulator origin (#219). |
| Ingress | Public origin `https://staging.tailtag.app`, a Railway custom domain. DNS is managed at Porkbun. Railway probes readiness with host `healthcheck.railway.app`. |
| Egress | Clerk (JWT key is local), R2 S3 API, Sentry ingest |
| Deployment | Exact-SHA controlled promotion (#202) through `scripts/api_staging_promote.py` and the Railway GraphQL API. GitHub autodeploy is off for Staging. |
| Migration hook | Railway pre-deploy command runs `migrate` before Gunicorn starts. The first replacement migration used `config.replacement_migrate`. |
| Build identity | Docker build argument `RAILWAY_GIT_COMMIT_SHA` writes `/opt/tailtag/build-identity.json` (#201) |
| Runtime variables, app-defined | `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_SETTINGS_MODULE`, `DATABASE_URL`, `CLERK_AUTHENTICATION_ENABLED`, `CLERK_JWT_KEY`, `CLERK_AUTHORIZED_PARTIES`, `MEDIA_STORAGE_ENDPOINT_URL`, `MEDIA_STORAGE_BUCKET_NAME`, `MEDIA_STORAGE_REGION`, `MEDIA_STORAGE_ACCESS_KEY_ID`, `MEDIA_STORAGE_SECRET_ACCESS_KEY`, `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `TAILTAG_STAGING_TARGET_PHASE`, `TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID`, `TAILTAG_STAGING_RESET_*`, `TAILTAG_STAGING_DATABASE_SYSTEM_ID`, `TAILTAG_STAGING_DATABASE_HOST`, `TAILTAG_STAGING_DATABASE_PORT`, `TAILTAG_STAGING_DATABASE_NAME` |
| Runtime variables, Railway-provided | `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_SERVICE_NAME`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_SERVICE_ID`, header `X-Railway-Request-Id` |
| Secrets ownership | Railway service variables in the Staging environment. The owner holds the provider accounts. |
| Sentry | One project shared by Development and Staging, split by `environment`. Field-beta dashboard and monitors (#216, #217). One uptime monitor on Staging `/health/ready`. |
| Logs and metrics | Railway service logs, HTTP logs and resource metrics (ADR 0007). 7-day log retention on Hobby. |
| Operator integrations | `railway ssh` relays for reset, fixtures, pool, inspection and operator commands. Operator authorization and audit (#205). Simulator host operator (#316). |

## 3. Railway dependency map (AC3)

Each row maps a Railway dependency to a replica replacement or an exclusion. The owner column names the child that does the work.

| Dependency | Where | Replica replacement | Owner | Consequence if missing |
| --- | --- | --- | --- | --- |
| Deployed readiness requires `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_SERVICE_NAME` | `health/configuration.py`, `config/build_identity.py` | Neutral runtime identity, for example from Cloud Run `K_SERVICE` and `K_REVISION` plus app-defined environment name. Railway behavior stays unchanged. | #355 | `/health/ready` returns 503. This failed in #340. |
| Target binding to the code-pinned Railway project | `config/replacement_target_binding.py` | A separate replica target binding with its own pinned identity. No Railway value is faked. | #355 | Readiness and operator admission fail closed |
| Probe host `healthcheck.railway.app` in the allowed host set | `health/configuration.py` | Replica host set: the Cloud Run service host and the probe host that Cloud Run sends. #355 records that probe host. | #355 | Readiness rejects the configuration |
| Pinned Staging host and Clerk origins | `health/configuration.py` `_validate_staging_phase` | Replica phase rules with replica origins | #355 | Readiness rejects the configuration |
| Build argument `RAILWAY_GIT_COMMIT_SHA` | `services/api/Dockerfile`, restore drill | Neutral build argument. Railway builds keep working. | #355 | The build writes a null source SHA |
| `X-Railway-Request-Id` log correlation | `observability/middleware.py` | Excluded. The field is fail-soft. Cloud Run trace header correlation is deferred. | none | Logs lack an edge request ID. No functional loss. |
| Remote pool and fixture gates on `RAILWAY_ENVIRONMENT_NAME` and `RAILWAY_SERVICE_NAME` | `simulation_pool/remote.py`, `simulation_fixtures/remote.py` | Replica-only gate on the neutral identity | #355 | Simulator setup cannot run |
| Reset safety on pinned Railway IDs | `rehearsal/safety.py` | Replica reset safety on the replica binding | #355 | Reset refuses to run |
| Operator commands check Railway environment and service | `accounts/management/commands/*staging*` | Replica-only admission for the commands that the parity checklist needs. Other commands are excluded. | #355 | The excluded commands are not available on the replica |
| `railway ssh` privileged relays | `scripts/api_*_ssh.py` | Cloud Run jobs that run the exact image with bounded commands | #355 (jobs), #359 (simulator relay use) | Setup, reconciliation, cleanup and reset cannot run |
| Promotion through the Railway GraphQL API | `scripts/api_staging_promote.py` | GitHub Actions with Workload Identity Federation and exact-revision gates | #356 | No repeatable delivery |
| Railway pre-deploy migration | Railway settings | Dedicated migration Cloud Run job from the same image before activation | #355, #356 | Migrations are not ordered before traffic |
| Railway deployment and status events | `scripts/api_development_delivery_event.py` | Excluded. Development delivery stays on Railway. | none | None for the replica |
| Restore drill through `railway connect` tunnel | `scripts/api_staging_restore_drill.py` | Neon branch or point-in-time restore into a separate target | #358 | No recovery proof |
| Host operator requires the `railway` binary and `RAILWAY_NO_AUTO_UPDATE=1` | `tools/simulator/tailtag_simulator/host_operator.py` | Replica admission with no Railway login | #359 | The simulator cannot start a replica session |
| Railway logs and metrics in runbooks | `docs/operations/*` | Cloud Logging and Cloud Monitoring. Sentry stays. | #358 | Runbooks have no log source |
| Staging and Development runbooks | `docs/development/staging.md`, `docs/development/backend-delivery-operations.md` | A separate replica runbook. The Railway runbooks stay unchanged. Development delivery is excluded. | #358 | No replica operating procedure |
| Media smoke and environment fingerprint checks | `scripts/api_media_storage_smoke.py`, `scripts/api_environment_fingerprint.py` | Replica-only variants or Child 5 checks | #357 | Media smoke cannot run |
| Authenticated Staging smoke gates on `RAILWAY_ENVIRONMENT_NAME` and `RAILWAY_SERVICE_NAME` | `scripts/api_staging_auth_smoke.py` | Replica-only authenticated smoke | #357 | P-3 has no end-to-end smoke |
| Deployment identity join to one Railway deployment | `scripts/api_deployment_identity.py` | Join of source SHA, image digest and exact Cloud Run revision | #356 | P-1 cannot bind the serving revision |
| First replacement migration reads `RAILWAY_PROJECT_ID` and `RAILWAY_ENVIRONMENT_ID` | `config/replacement_migrate.py` | Excluded. It is a one-time Railway bootstrap. The replica uses the guarded migration job. | none | None for the replica |
| Baseline ownership registry reconciliation | `scripts/api_staging_registry_reconcile.py`, `scripts/api_staging_registry_reconcile_remote.py` | Replica-only job that keeps the registry and sentinel semantics | #355 | P-5 cannot prove baseline ownership |
| Staging diagnostic scripts gate on `RAILWAY_ENVIRONMENT_NAME` | `scripts/api_staging_fixture_diagnose.py`, `scripts/api_staging_operator_inspect.py`, `scripts/api_staging_operator_matrix.py` | Operator inspection and the audit matrix get replica variants only if P-6 needs them. Fixture diagnosis is excluded. | #358 | Diagnosis uses Cloud Logging and Sentry only |
| Railway tasks | `Taskfile.yml` tasks `api-staging-reset-ssh`, `api-staging-reset-provision-ssh`, `api-media-storage-smoke` | Replica tasks that call the replacements above. The Railway tasks stay unchanged. | #355, #357 | Operators have no task entry point |
| Railway custom domain | Railway settings | Default Cloud Run `run.app` URL. No API custom domain. Clerk DNS records are decision C-1. | #354 | None |

Repository facts behind this map: no `railway.toml` or `railway.json` exists. No GitHub Actions workflow calls Railway today.

## 4. Service replacement matrix (AC4)

| Concern | Railway Staging | Replica | Identity and access | Denied paths |
| --- | --- | --- | --- | --- |
| Infrastructure | Railway project, managed in the dashboard | One new GCP project, Terraform in the repository, remote state in a GCS bucket in that project | `tf-infra` identity used only by the operator | No Railway token in Terraform |
| Delivery | Promotion script and Railway API | GitHub Actions and Artifact Registry | `deployer` identity through Workload Identity Federation, limited to this repository and branch | Deployer cannot read runtime secrets or change IAM |
| Migration | Railway pre-deploy command | Cloud Run job | `migrator` identity and a Neon migration role | Runtime role cannot run DDL |
| Runtime | Railway `api` service | Cloud Run service, `us-east4` | `runtime` identity. Reads only named secrets. Neon runtime role. | Runtime cannot provision or read other secrets |
| Database | Railway PostgreSQL | Neon Launch project, `aws-us-east-1`, PostgreSQL 18, the same major version as Staging (D-2) | TLS with server identity checks | No connection string from Railway |
| Media | Private Staging R2 bucket | New private R2 bucket with its own single-bucket token | Object Read & Write on the replica bucket only | Replica token cannot reach Railway buckets |
| Authentication | `TailTag Staging Replacement` Production instance | New Clerk application for the replica, Production instance (C-1) | Synthetic users only | No Staging Clerk keys |
| Secrets | Railway variables | Secret Manager in the replica project | Per-identity secret access | No copied Railway secret |
| Observability | Shared Sentry project, Railway logs | Same Sentry project with a new `replica` environment and a new client key (DSN). Cloud Logging and Cloud Monitoring. | Replica-only DSN, revocable without touching Staging | Staging dashboards and monitors stay unchanged. #358 makes sure that every Staging monitor filters on `environment` before replica load starts. |

Region pair: the owner confirmed US East (Virginia) for Railway Staging on 2026-10-22. The confirmed replica pair is Cloud Run `us-east4` and Neon `aws-us-east-1`, both in northern Virginia.

Allowed data: synthetic records, synthetic Clerk users and synthetic media created for the replica. Railway Staging data, player data and copied credentials are not allowed.

Proposed service substitutions that need owner approval: none. Cloud Tasks, Cloud Scheduler, Cloudflare edge features and a custom domain are not proposed.

Service decision:

- C-1: Clerk instance type for the replica. A Clerk Production instance needs DNS records under a domain. A Development instance needs no DNS, but its issuer and token behavior differ from Staging. The #219 simulator token path is proven only on a Production instance. Decision: a Production instance on a replica-only subdomain such as `replica.tailtag.app`. The owner adds the Clerk records at Porkbun. This does not change canonical DNS. Status: APPROVED by the owner on 2026-10-22.

## 5. Parity criteria (AC5)

| ID | Criterion | Railway reference | Child |
| --- | --- | --- | --- |
| P-1 | Immutable identity: one source SHA and image digest bind to the serving revision | #201 build identity, deployment receipts | #355, #356 |
| P-2 | Health: liveness, configuration-aware readiness and external smoke stay separate | #203 health contract | #355, #358 |
| P-3 | Authentication: valid tokens pass and every negative case is denied | #135, #329, Staging auth smoke | #357 |
| P-4 | Media: private bucket, signed reads, anonymous reads denied | [Media contract](2026-08-19-v0-media-storage.md) | #357 |
| P-5 | Reset and reseed: ownership registry, quiescence and sentinel checks fail closed | #204 reset contract | #355 |
| P-6 | Operator authorization and audit | #205 audit contract | #358 |
| P-7 | Synchronous catch correctness: no duplicate or lost catches under retries and concurrency | #222 reconciliation, convention baselines | #355, #359, #360 |
| P-8 | Deployment gates: a failed candidate never takes traffic | #202 promotion contract | #356, #358 |
| P-9 | Backup and restore into a separate target with integrity checks beyond row counts | #207 restore contract | #358 |
| P-10 | Fail-closed recovery: unsafe or ambiguous state stops work | #206 rollback contract | #356, #358 |
| P-11 | Isolation: no replica path reaches Railway databases, buckets or credentials | 2026-09-28 parity readback | #354, #357 |

## 6. Portability ownership (AC6)

| Child | Owns |
| --- | --- |
| #355 (Child 3) | API readiness, runtime identity and build identity. Guarded migration, reset, fixture, reconciliation and cleanup jobs. |
| #356 (Child 4) | Delivery orchestration: build, migration ordering, exact-revision gates and promotion |
| #357 (Child 5) | Trust validation for every connection and identity |
| #359 (Child 7) | Simulator admission and execution against the replica |

No child fakes a Railway identity value.

## 7. Evaluation plan and approval gates (AC7)

Workload assumptions: the existing simulator scenarios in `tools/simulator/tailtag_simulator/scenarios/`, mainly `convention-baseline-v2`, `convention-soak-v2`, `convention-hotspot-v2`, `convention-retry-v2` and `journeys-v1`. Runs use the same external simulation host as the Railway baselines.

Measures: per-operation p50, p95 and p99, throughput, error and timeout rates, cold start, database connections, restore time, data loss on restore, release time, transition time and cost. Sample minimums come from the [performance evidence spec](2026-10-10-simulation-performance-evidence.md): 200 samples for p95 and 1,000 for p99. A result below the minimum is inconclusive.

Evidence format: proof documents in `docs/specs/` and allowlisted receipts in `docs/development/`. Detailed simulator reports go to the owner-private archive with verified hashes. Replica baselines stay separate from Railway baselines.

Comparison method: the same scenario, seed and simulation host on both targets. Every comparison states source, configuration and plan differences, including D-1.

Acceptance owner: the owner (Finn the Panther) approves every gate.

Targets and the decision rule: this section freezes the owner decisions recorded in [#353](https://github.com/TailTag-Game/tailtag/issues/353) on 2026-10-22. The Railway reference is the committed `convention-baseline-v2` and `convention-soak-v2` baselines. They show a total p95 of 276 to 317 ms and a p99 of 385 to 407 ms at about 23 to 24 requests per second. The soak run shows a p95 of 310 ms at about 27 requests per second.

Hard gates. A failure of any hard gate gives a reject result.

- H-1: Reconciliation finds zero duplicate, missing or invalid catches during load, retries, revision replacement and capacity transitions.
- H-2: Every #357 authentication and isolation negative test denies access.
- H-3: No committed synthetic write is lost across a revision replacement or a capacity transition.

| ID | Area | Target |
| --- | --- | --- |
| T-1 | Warm latency, total and `confirm` | p95 at most 25% above the Railway baseline (about 400 ms). p99 at most 50% above it (about 600 ms). |
| T-2 | Error and timeout rate | 1% or less |
| T-3 | Throughput | Sustain the baseline (about 24 requests per second) and soak (about 27 requests per second) workloads. Then pass a 2x burst stage (about 50 requests per second) within T-1. |
| T-4 | Cold start | After idle, with Cloud Run and Neon both cold, the first request completes in 5 seconds or less. After a prewarm, p95 meets T-1. |
| T-5 | Idle-month cost | At most the Railway Hobby floor of $5 |
| T-6 | Convention-weekend cost | At most 1.5x the Railway estimate for a matched profile, with the #344 method |
| T-7 | Restore time | Less than 30 minutes from restore start to a verified, usable API on a separate target |
| T-8 | Data loss on restore | 1 minute or less, measured against known committed synthetic writes |
| T-9 | Release effort | 15 minutes or less from merge to promoted revision, with no console steps |
| T-10 | Capacity transition effort | 10 minutes or less for a manual idle to convention transition, with one documented command |

Decision rule for Child 9 (#361):

- Adopt: every hard gate passes and every target is met.
- Revise: every hard gate passes, and at most two targets miss, each with a clear fix.
- Reject: a hard gate fails, or a target misses with no clear fix.

| Gate | Before | Owner approves |
| --- | --- | --- |
| G-1 | #354 first `terraform apply` | Resource, region and plan limits. A billing budget alert. Stop conditions. Cleanup and retention plan. No fixed spending ceiling (#352). |
| G-2 | #359 first load run | Exact target and configuration, the numeric targets T-1 to T-4, load ceilings for requests, concurrency and duration, stop conditions, sample requirements and cleanup plan. Load grows only after a smaller run passes. |
| G-3 | #360 first transition | Idle, pre-convention and active profiles |
| G-4 | Any persistent data deletion | The exact resources |
| G-5 | Any service substitution | A documented decision |

## 8. Prior findings (AC8)

| Prior finding | Class | Note |
| --- | --- | --- |
| Separate project, service accounts, named secret access (#339) | Reusable | Same pattern. Terraform must reproduce it. |
| Budget counts spend after credits, so it cannot alert during a free trial (#339) | Reusable | The G-1 alert must count real spend |
| Image build, port, liveness, logs, startup failure (#340) | Reusable | Same Dockerfile |
| Readiness fails on Cloud Run because of Railway identity (#340, #346) | Changed | #355 owns the fix |
| Cloud SQL, IAM login, proxy, PostgreSQL 17 (#341, #348) | Untested here | Neon replaces Cloud SQL. The proxy and its startup order do not apply. |
| Migration job and repeat run (#341) | Reusable | Pattern only. It must run against Neon. |
| Clerk synthetic users, access rules (#342) | Reusable | A new Clerk application (C-1) |
| Media on Google Cloud Storage with checksum settings (#342) | Untested here | R2 from Cloud Run is a new proof |
| Rollout, traffic rollback in about 4 seconds (#343) | Reusable | Cloud Run behavior. #356 must re-prove it under GitHub Actions. |
| Backup restore and PITR clone (#343) | Untested here | Neon restore is a new proof |
| No-traffic revisions report ready without starting (#348) | Reusable | #356 gates need traffic or another start check |
| Failed revisions keep starting new instances (#343, #348) | Reusable | Cleanup must delete failed revisions |
| Tagged revision URLs unsupported (#349) | Reusable | #356 chooses another exact-revision test |
| Cold start 6 to 15 seconds with Cloud SQL (#343, #348) | Changed | Neon and Cloud Run cold start must be measured together |
| Migration account was able to read the Django secret key and both media keys. Runtime account held an extra Cloud SQL IAM role. (#344 security findings) | Reusable | #354 and #357 must deny both. Per-identity secret access in section 4 depends on it. |
| Database kept a public endpoint with no authorized networks (#341) | Changed | Neon endpoints are public by design. #357 proves TLS, role limits and credential scope instead. |
| Clerk session token lasts about 60 seconds (#342) | Reusable | Test tooling must mint tokens close to use |
| Simulator traffic NOT EXERCISED because the simulator allows only local and Staging targets (#343, #199) | Untested here | #359 adds replica admission without weaker rules |
| Cost method and Railway estimates (#344) | Reusable | T-6 uses the same method with refreshed prices |
| Socket database URL support (#347, closed not planned) | Untested here | Not needed. Neon uses a TCP connection string. |

New proof obligations: Neon behavior, R2 from Cloud Run, Terraform and provider behavior, and simulator portability.

## 9. Approval and resource reuse (AC9)

The #338 GCP project was deleted on 2026-10-22, and its Clerk test application was deleted. No #338 resource is imported. #354 creates fresh resources. The new GCP project ID must differ from the deleted one.

One existing resource is reused: the shared Sentry project. The owner owns it and it exists today. Reuse is safe because the replica gets its own client key and its own `environment` tag, and Staging monitors filter on `environment` (checked in #358). The owner approved this reuse on 2026-10-22.

Owner decisions already made: D-2 resolved, C-1 approved, Sentry project reuse approved, all on 2026-10-22.

Owner approval of this contract: PENDING. Approval covers sections 1 to 8. It happens on review of the pull request that adds this document.
