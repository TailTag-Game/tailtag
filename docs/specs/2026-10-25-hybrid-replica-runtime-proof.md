# Hybrid replica runtime proof (#355)

Status: live phase complete on 2026-10-25

Related issues: [#355](https://github.com/TailTag-Game/tailtag/issues/355) (this proof), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352), foundation proof [#354](2026-10-22-hybrid-replica-provisioning-proof.md), contract [#353](2026-10-22-hybrid-replica-contract.md)

Runbook: [Hybrid replica provisioning](../development/hybrid-replica-provisioning.md), section 11

This document records the evidence for each #355 acceptance criterion. AC1 to AC9 come from the issue. AC10 to AC21 come from the refinement comment on #355. Each result is PASS, PARTIAL or NOT_EXERCISED. PARTIAL means that part of the criterion passed and the rest is named as a follow-up. The AC16 override limit was measured after the first version of this proof.

## Identities

| Item | Value |
| --- | --- |
| Final source SHA | `84b99d570fc94db5f6b5f5b6bdad350949d0d641` (`84b99d5`, PR #376) |
| Final image digest | `sha256:b125badfe89b5033dc63bc4ccea7d1cbe87cce483b8fea70473647a11d5cc730` |
| First image | `9c7eb57` (PR #372) as `sha256:d7d1853b06fa346960558cf705d9b22834b05b54fe760f3ce50700a270bdae2e`, replaced by the final image |
| Service revisions | `tailtag-api-replica-00006-gxg` on `9c7eb57`, `tailtag-api-replica-00007-sd9` on `84b99d5`, then `tailtag-api-replica-ac7-2f951c` on the same image (AC7) |
| Image runtime | Python 3.13, psycopg 3.3.4 binary wheel, libpq 18.0, Django 6.0, gunicorn 26.0 with one sync worker |
| Database | Neon PostgreSQL 18.6, direct endpoint, `max_connections` 901 with 4 reserved |
| Terraform | 1.17.0 with `hashicorp/google` 8.8.0, `cloudflare/cloudflare` 5.28.1 and `kislerdm/neon` 0.18.0. Lock file hashes are unchanged from #354. |
| Build host | Docker 29.8.2, buildx 0.37.2, `linux/amd64` |
| UTC window | 2026-10-23 to 2026-10-25 |

This document never records project IDs, project numbers, hosts, account IDs, Clerk user IDs, connection strings or tokens.

## Results

| AC | Result | Evidence or reason |
| --- | --- | --- |
| AC1 | PASS | Both images were built from a clean checkout of a merged `main` SHA and deployed by digest. For `84b99d5`, a second uncached build produced the same image ID as the pushed image. Every revision and job execution reported the matching source SHA in `/health/identity` or its result line. |
| AC2 | PASS | The service and jobs identify themselves from Cloud Run values and the hashed pins, with no Railway variable. The legacy `*.a.run.app` URL returned HTTP 400. Unit tests cover wrong or missing replica identity, and the Railway tests pass unchanged. |
| AC3 | PASS | Every replica connection uses `sslmode=verify-full` with the Debian CA bundle (AC13). The direct endpoint, the connection budget and connect timing are in AC14. |
| AC4 | PASS | The migrate job ran as `tt-migrator` and passed twice on `9c7eb57` and once on `84b99d5`. A failed first run did not move traffic. Details are in AC12. |
| AC5 | PASS | Reset `provision` (`tailtag-replica-reset-dh57z`) recorded the reset identity. Reset (`zp2hd`) restored the baseline, and registry reconciliation (`5kgng`) matched all 15 checks. A failed reset stopped before any write (live finding 9). |
| AC6 | PARTIAL | Every pool, fixture and inspection operation passed admission in its own job and reached the domain code. A full fixture provision and inspection needs onboarded pool players, which needs simulator access to the replica (#359). |
| AC7 | PASS | A temporary reviewed probe proved catch writes, retries, a concurrent first create and state across a revision replacement. See the AC7 section. |
| AC8 | PASS | Readiness and job admission require the hashed database and media pins (AC20). No check read or wrote a Railway resource. |
| AC9 | PASS | This document, runbook section 11 and PRs #369 to #376 record the changes, limits and receipts. |
| AC10 | PASS | Revision and execution names appear as `deployment_id`, with environment `replica`, in every identity and job result. Target pins for the service and six jobs matched at runtime. |
| AC11 | PASS | `TAILTAG_SOURCE_SHA` and the OCI revision label were set on both builds. Source SHA, digest, `/opt/tailtag/build-identity.json`, label and this receipt agree. The second build recorded the same identity. |
| AC12 | PASS | `config.settings.migrate` reads only `DATABASE_URL`. Runs `tq9k4`, `rrnqt` and `qk6kg` passed with no unapplied migration. Run `x2pr8` failed with a TLS error and exited non-zero, and no traffic moved. The Terraform tests prove that `tt-migrator` reads only `migrator-database-url`. |
| AC13 | PASS | The image uses libpq 18.0. Its bundled OpenSSL cannot find the system CA store, so `SSL_CERT_FILE` names `/etc/ssl/certs/ca-certificates.crt` (PR #374). Every job and the service then connected with verify-full. #357 keeps the controlled-failure proof. |
| AC14 | PASS | All three role URLs use the direct endpoint with port 5432. The pooled endpoint is unsupported, because the app takes session advisory locks. The budget is in the AC14 section. |
| AC15 | PASS | The role script created `maintainer` and wrote its secret. A second run wrote nothing. The capability probe reported `pg_control_system`, `database_owner` and `pg_signal_backend` as ok. Ownership survived Neon suspends, because reset passed days later. |
| AC16 | PASS | Six job shells exist with parallelism 1, no retries, timeouts and named secrets. Their image is ignored by Terraform. One execution took 35 to 52 seconds. Cloud Run accepts an override value of 32,768 bytes and refuses 32,769 bytes (live finding 12). |
| AC17 | PASS | Migrate, reset, provision, every pool operation, every fixture operation and inspection passed replica admission. Registry reconciliation passed. Operator account commands stay Railway-only. |
| AC18 | PASS | The owner made the replica Clerk Production application on `replica.tailtag.app`, the DNS records, the JWT key, two synthetic users and one designated media object. The pool used size 3. |
| AC19 | PASS | Terraform sets port 8000, an HTTP startup probe on `/health/live` and the non-secret map. The probe sends the deterministic `run.app` host as its `Host` header (PR #374), and every revision passed it. |
| AC20 | PASS | The database host and name and the media endpoint and bucket are pinned by hash. Readiness passed with the real values. Unit tests refuse Railway-shaped values with no network call. The #354 AC13 credential scope still applies. |
| AC21 | PASS | Readiness returned 200 on every revision while `sentry-dsn` had no version. `SENTRY_DSN` is wired only when `wire_sentry_dsn` is on, which #358 owns. |

## AC7: catch behavior

The probe followed the [field-beta probe contract](2026-10-01-field-beta-observability-validation.md#probe-contract), adapted to the replica. The owner reviewed it in full before the run. It ran outside the repository, and it was deleted after the run. The owner pasted short-lived session tokens for the two synthetic users at hidden prompts. The probe printed only stage names, status codes, outcomes and counts.

| Step | Request | Result |
| --- | --- | --- |
| C-1 | Both users read `/api/me/`, the active convention, the fursuits and the activations | PASS, baseline found |
| C-2, C-3 | Owner starts two catch sessions and fetches both credentials | PASS |
| C-4 | Catcher resolves credential A | PASS, 200 |
| C-5 | Catcher confirms A | PASS, 201 `created` |
| C-6 | Catcher sends the same confirmation again | PASS, 200 `already_caught`, same catch ID |
| C-7 | Catcher sends two simultaneous first confirmations for fursuit B | PASS, codes 200 and 201, one catch |
| C-8 | Catcher reads the catch history | PASS, 2 catches, 1 per fursuit |
| C-9 | Operator makes a new revision on the same image | PASS, new `deployment_id`, same source SHA |
| C-10 | Catcher reads the history again | PASS, the same two catch IDs |
| C-11 | Owner stops both catch sessions | PASS, end reason `owner` |

The service runs one gunicorn sync worker, so the two C-7 requests can arrive one after the other. C-7 proves the result a client sees. The catch service tests cover the database race and its unique constraint. A reset (`6vmjf`) restored the baseline afterwards.

## AC14: connection budget

| Part | Connections |
| --- | --- |
| Service: up to 2 instances with one gunicorn worker each, `CONN_MAX_AGE` 0 | 2 |
| Jobs: six jobs with parallelism 1 | 6 |
| Reset: control connection and denial probe | 2 |
| Total | 10 |

The total stays far below 901. A warm connection took 0.54 seconds. After scale to zero, the first service request took 10.6 seconds, which includes the instance start and the Neon wake. Jobs started after long idle periods connected within the 5-second `connect_timeout`. The Neon wake alone was not measured.

## Live findings

1. Neon's connection URI has no port, so the stored role URLs had none. Reset compares a numeric port. PR #372 writes port 5432.
2. Making `maintainer` the database owner changed the Neon provider's branch `role_name`, which forces replacement. `prevent_destroy` blocked the plan. PR #373 ignores that field and reads the admin URL from the environment.
3. Clerk set the first production domain on the apex. The owner changed the application to a Secondary application on `replica.tailtag.app`.
4. `sslrootcert=system` failed inside the image, so the first migrate run failed. PR #374 sets `SSL_CERT_FILE`.
5. A pre-flight audit added the startup probe `Host` header and `GUNICORN_CMD_ARGS="--timeout 0"` in PR #374.
6. Reset `provision` needs both synthetic users as API rows. Each user made one authenticated call first, through the replica auth smoke (PR #375).
7. The smoke needed Django settings to build a request. PR #376 defaults them.
8. The first request after scale to zero took 10.6 seconds, longer than the 5-second smoke and reset preflight limits. PR #376 warms the service in the smoke, and runbook section 11 adds a warm-up before reset jobs.
9. Neon's proxy gives the client a different backend pid from the server. Reset excluded its executor by the client pid, so it ended its own session and left the database closed. No data changed. The owner reopened the database as `maintainer`. PR #376 asks the server for the pid.
10. Idle `maintainer` sessions stayed open after their clients closed. Reset ends them like other client sessions.
11. One image push stalled on upload timeouts. The push succeeded later from another network.
12. Cloud Run refuses a job env override value over 32,768 bytes, with `length cannot exceed 32768`. The local runner allowed 65,536 bytes, so a larger request failed as `FAIL_LAUNCHER` and started nothing. The runner now caps the request at 32,768 bytes. Requests of 4 KB, 16 KB and 32 KB reached the job intact.

## Approved deviations

- AC15 quiescence counts every client session except Neon's `cloud_admin`, as the owner decided on 2026-10-23.
- AC13 uses `SSL_CERT_FILE` in Terraform instead of a CA path in each stored URL, so no secret rotation was needed.
- AC6 and AC17 use an admission matrix, because a full fixture provision needs #359. AC6 stays open until that run.
- AC7 uses a temporary probe instead of a committed harness, as on Staging.
- PR #376 had a parent self-check instead of an independent review, under the Lean ADW policy.

## Residual risks and follow-ups

- As database owner, `maintainer` owns schema `public` and has the right to drop it. The reset job accepts no SQL, and only `tt-maintainer` and project owners read its URL.
- The nine private reset values travel as a job environment override. They stay in the execution record, which only project owners can read.
- The service scales to zero, so the first request can take over 10 seconds. A minimum instance count costs money while the service is idle.
- The service runs one sync worker, so it serves one request at a time per instance.
- #359: simulator access to the replica, a full fixture provision and the inspection flow.
- #357: Clerk negative tests and the controlled TLS failure proof. #358: Sentry on the replica.
