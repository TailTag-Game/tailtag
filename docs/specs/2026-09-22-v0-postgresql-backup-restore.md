# V0 PostgreSQL backup restoration and integrity proof

Issue: [#207](https://github.com/TailTag-Game/tailtag/issues/207). Parent: #197. Prerequisite #206 is complete; #241 owns only the deferred live application-rollback rehearsal and does not block this drill.

## Decision and boundary

The authoritative #207 recovery path is a real custom-format `pg_dump` from the canonical `TailTag/staging` PostgreSQL database, followed by `pg_restore` into a newly created, disposable PostgreSQL 18 recovery target. The target is local to the operator's Docker daemon, explicitly non-production, and has no Railway service identity or attachment to the active Staging API. This is a restore drill, not a replacement backup strategy or a production recovery design.

Read-only discovery on 2026-09-22 found PITR disabled (`enabled=false`, `bucketWired=false`) and no volume-backup schedule or backup on the Staging Postgres volume. Railway's normal volume restore acts on the source service. The logical dump path is therefore fixed for this issue. Do not enable PITR or volume backups as part of #207.

A local-only probe confirmed the cached PostgreSQL 18 image starts with `--network none`, has no published ports, accepts a query from a second container sharing only its loopback, and is removable with its temporary data. This verifies the proposed target connectivity without touching Staging.

The canonical Staging API and database remain online and unchanged. No step changes the Staging API `DATABASE_URL`, repoints `staging.tailtag.app`, runs #204 reset/reseed, deploys or stops a Staging service, or mutates Clerk/R2. The #206 migration/application recovery contract remains authoritative; this drill neither reverses migrations nor rehearses application rollback.

## Exact recovery target and connectivity

Use the verified local Docker daemon and its already available `postgres:18` image. Start one uniquely named, task-owned container with `--network none`, no published ports, a task label, `POSTGRES_DB=tailtag_recovery`, and tmpfs mounts for both PostgreSQL data and `/backup`. Docker's `none` network has loopback only. No host path, Railway volume, or persistent Docker volume is mounted. Before any restore, inspect the container by its full returned ID and require the expected image, task label, `NetworkMode=none`, empty port bindings, and tmpfs mounts. Require PostgreSQL major version 18, an empty newly created `tailtag_recovery` database, and an unchanged canonical Railway Staging Postgres service/volume ID. Check source database size and available local memory before allocating the temporary mounts; refuse the drill if conservative capacity cannot be established. These independent facts are the target guard; a copied database sentinel is not.

Only the operator host can reach the source, through `railway connect Postgres --tunnel-only` with the exact TailTag project and Staging environment. Keep its connection details in process memory, never in a command line, file, shell history, or log. The local PostgreSQL 18.6 client uses those details for read-only source queries and `pg_dump`. The dump streams directly into `/backup/recovery.dump` on the isolated container's tmpfs. `pg_restore --list` reads that artifact inside the container; `pg_restore --exit-on-error --single-transaction` then connects through `docker exec` to the fixed local `tailtag_recovery` database. The restore operation accepts no operator-supplied host or Railway database URL.

For backend proof, build or select the exact application revision observed for the source recovery point. Run a disposable command-only backend container sharing only the recovery container's isolated network namespace, with its database URL fixed to loopback and `tailtag_recovery`. Use local Django settings with Clerk authentication disabled, no Clerk/R2 credentials, no public port, no server startup, and no migrations. Run read-only ORM queries and remove that container. If this cannot be done safely, record the concrete limitation and strongest safe SQL/schema substitute; do not connect the active Staging API to the clone.

## Source recovery point

Verify the approved GitHub and Railway identities before each authenticated operation. Resolve the current Staging API deployment ID, full source SHA, Staging Postgres service/volume IDs, PostgreSQL major version, and tool versions in process memory. Durable evidence may retain the public source SHA and opaque one-way resource fingerprints or equality results, not full Railway resource IDs. Confirm the same API deployment and database relationship again after the drill. An intervening deployment, database-service replacement, or source identity ambiguity makes the proof inconclusive.

Open a source PostgreSQL `REPEATABLE READ, READ ONLY` transaction and export its snapshot. While that exporting transaction remains open, collect the sanitized source facts below and run `pg_dump --format=custom --snapshot=<exported snapshot>` against the same database. This makes the expectations and dump refer to one database snapshot. Record UTC dump start/completion times, elapsed duration, and the snapshot time, but never the snapshot token. Abort if snapshot export, source capture, dump, or artifact transfer fails. Do not persist source connection details, credentials, private hostnames, Clerk identifiers, handles, media keys, tokens, row contents, or raw query results.

Capture only migration application names and leaf state; exact aggregate counts for the named domain tables; zero/nonzero results for every integrity query; expected catalog constraint definitions/fingerprints; and presence booleans for representative records. The backup need not equal #204's canonical seed: source and restored facts must match at this snapshot. A table with zero rows still requires its schema and constraints; record relationship checks over zero rows as `NOT_EXERCISED`, not as evidence of populated-domain recovery.

## Integrity contract

Run each check on the source snapshot and the restored target. A passing target has matching source facts and zero violations. Query only aggregates, existence booleans, migration labels, and catalog metadata; do not print identifiers or data values.

| Check | Required proof |
| --- | --- |
| Migration and schema | `django_migrations` applied set and graph leaves match; expected Django tables exist; restored PostgreSQL major version is compatible. |
| Constraints | `pg_catalog` shows expected FK, unique/partial-unique, and check constraints on the V0 tables, including explicit model constraint names; constraint definitions/fingerprints match the source snapshot. |
| User/Profile | Every `PlayerProfile.user_id` references one `User`, no duplicate profile user exists, and the profile one-to-one key/constraint is present. Staff Users need not have profiles. |
| Fursuit | Every owner references a `User`; `tailtag_id` is unique and its database uniqueness is present. |
| Enrollment | Every enrollment references a `User` and `Convention`; `(user, convention)` is unique; each user has at most one active enrollment; both uniqueness constraints are present. |
| Activation | Every activation references a `Fursuit` and `Convention`; `(fursuit, convention)` is unique; active state and `deactivated_at` obey the database check constraint. |
| Session | Every catch session references an activation; expiry, end-field pairing, end ordering/reason, and one unended session per activation satisfy the declared constraints. |
| Credential | Every catch credential references an activation; token uniqueness, one current credential per activation, and revocation-field/reason checks hold. Never output tokens. |
| Catch | Every Catch references its catcher, Fursuit, Convention, activation, and session; its activation matches its Fursuit/Convention, its session matches its activation, and `(catcher, fursuit, convention)` is unique. |
| Representative reads | Where the source count is positive, Django ORM can count and fetch existence for Users, Profiles, Fursuits, Conventions, enrollments, activations, sessions, credentials, and Catches without external calls or row output. |

The expected schema manifest comes from the matching application revision's installed Django models and migration graph, not from the source database alone. It includes Django-owned tables plus the TailTag `accounts`, `profiles`, `fursuits`, `conventions`, `catches`, `operator_audit`, and `rehearsal` apps. Check structural FK/primary-key/unique constraints for every declared model. At minimum require the explicit named constraints declared by those models, including both enrollment and credential partial uniqueness rules, the session partial uniqueness rule, Catch uniqueness, `operator_audit_actor_outcome_valid`, `rehearsal_reset_identity_singleton`, and `rehearsal_reset_identity_roots_complete`. This independent manifest prevents matching source/target omissions from appearing valid.

Use the deployed V0 model and migration graph, plus #204's domain closure analysis, to maintain the concrete SQL checks. Do not infer that every User has a profile, that historical Catches or sessions must exist, or that the recovered rows exactly match #204's seed.

## Acceptance Contract

| ID | Observable outcome |
| --- | --- |
| AC-1 | The canonical Staging source and approved operator identity are positively verified; PITR-disabled discovery and the logical-dump selection are recorded. |
| AC-2 | Source deployment identity, PostgreSQL compatibility, migrations, aggregates, constraints, and integrity expectations are captured from one read-only database snapshot without sensitive values in evidence. |
| AC-3 | A real custom-format `pg_dump` succeeds; its transient artifact passes `pg_restore --list`. |
| AC-4 | A newly created, local, network-isolated, positively verified target receives a successful `pg_restore`; destination cannot resolve to canonical Staging. |
| AC-5 | Restored migrations, schema, constraints, domain counts, relationship checks, and representative existence match the source recovery point; populated relationships are exercised where present. |
| AC-6 | The matching TailTag revision initializes Django and performs read-only ORM/domain queries against the recovery target, or a concrete safety/platform limitation and strongest safe substitute are recorded. |
| AC-7 | Before/after evidence shows active Staging API deployment and Postgres service/volume relationship unchanged and Staging health remains good. |
| AC-8 | The backend validation container, recovery Postgres container, and in-memory dump are removed after success or failure; absence is verified and only sanitized evidence remains. |
| AC-9 | A durable record contains the mechanism, source time and revision, tool versions, target classification, dump/restore timing and outcomes, every named check, usability, non-impact, cleanup, limitations, and follow-up. The issue closes only after a real restore and verification. |

An AC-6 limitation and safe substitute must be recorded when backend execution
is unsafe, but they do not turn that incomplete proof into a #207 GO. A GO still
requires the matching-revision read-only backend proof stated above.

## Test Surface Contract and Scope Guard

The operational entry point may use local Docker, the Railway CLI's read-only Staging connection, PostgreSQL client tools, and existing Django models. Its package-internal `parse_tunnel_details`, `validate_recovery_target`, and `cleanup_task_resources` functions are intentional seams for parsing, guarding and failure cleanup; `collect_integrity` and `compare_integrity` are the read-only integrity seams. Unit tests may inject a command runner and source/target query executors to reject a wrong service, a non-isolated target, a source/target mix-up, partial dump/restore, sensitive evidence, or failed cleanup. At least one disposable local PostgreSQL integration rehearsal must exercise real custom-format dump/restore and integrity queries before the live drill. No public production API or database schema is added solely for testing. The live drill is the black-box acceptance test.

Outcome: prove one real Staging logical backup can be restored and read as valid V0 data. Non-goals: PITR or backup-platform changes, volume restore, production recovery, Staging reset, migration rollback, #241, Clerk/R2 validation, frontend, and generalized disaster-recovery automation. Expected files are this spec, an adjacent implementation plan, a focused runbook/operation entry point and tests if needed, the spec index, and one sanitized drill evidence record. Proof is focused automated checks, repository validation, and the recorded live dump/restore/cleanup outcomes.

## Failure and cleanup rule

Never retry an ambiguous restore against another destination. On any failure, terminate and await the source snapshot query, `pg_dump`, stream receiver, and Railway tunnel process groups before stopping/removing only task-owned containers by the full captured IDs; verify their absence. The tmpfs dump and database are removed with the container; no dump is copied to the host or repository. If cleanup cannot be verified, mark the drill failed and record only an opaque local recovery handle for manual cleanup, without declaring completion. Preserve existing images and unrelated Docker resources.

## References

- [Railway PostgreSQL backup and restore guide](https://docs.railway.com/guides/postgres-backups-restores)
- [Docker `none` network](https://docs.docker.com/engine/network/drivers/none/)
- [Docker tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/)
- [#204 domain analysis](2026-09-17-staging-synthetic-reset-reseed.md)
- [#206 migration/application recovery contract](https://github.com/TailTag-Game/tailtag/issues/206)
