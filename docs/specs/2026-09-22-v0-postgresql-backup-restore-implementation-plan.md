# V0 PostgreSQL Backup Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task by task. Execute against the frozen [#207 specification](2026-09-22-v0-postgresql-backup-restore.md). The live drill is the final acceptance gate.

**Goal:** Prove one real canonical Staging custom-format PostgreSQL dump can be restored into an isolated disposable target, validated against its source snapshot, read by the matching TailTag backend, and cleaned up without changing active Staging.

**Architecture:** A focused local operator command holds a read-only source snapshot through a Railway SSH tunnel, streams `pg_dump` to tmpfs in a Docker PostgreSQL 18 container with no network, validates/restores via `docker exec`, and emits a fixed sanitized evidence record. A disposable command-only backend container shares only that target's loopback for read-only ORM proof. The Staging runbook explains operation and failure handling.

**Tech stack:** Railway CLI 5.57.2, PostgreSQL client 18.6, locally cached `postgres:18`, Docker 29.4/OrbStack, Python/uv/Django, pytest, Ruff, Pyright, Semgrep.

## Global constraints and approved contracts

- The [spec's Acceptance Contract](2026-09-22-v0-postgresql-backup-restore.md#acceptance-contract), Test Surface Contract, and Scope Guard are frozen for this review unit. New public APIs, schema migrations, Clerk/R2 operations, PITR/volume-backup configuration, and Staging mutations are outside scope.
- The source is canonical `TailTag/staging` `Postgres`; inspect exact project/environment/service IDs, approved Railway identity, and active API deployment identity before each authenticated operation. `gh api user --jq .login` must equal `FinnThePanther` before authenticated GitHub operations. Stop the entire task on identity/authentication/authorization failure; never switch credentials or retry through another mechanism.
- The target is local, newly created, `--network none`, without published ports, with PostgreSQL data and dump on tmpfs. No Railway target URL is an accepted restore argument.
- A source-side exported `REPEATABLE READ READ ONLY` snapshot is shared with `pg_dump --snapshot`; the source aggregate facts and artifact must describe the same recovery point.
- Only fixed sanitized fields may be written to repository evidence. Keep full Railway service/volume/deployment IDs transient; retain the public source SHA and one-way resource fingerprints or equality results. No command transcript, raw CLI output, database URL, host, credential, Clerk ID, handle, media key, token, row contents, or row identifiers.
- Track every task-created container ID, stop/remove it after all checks (including failed paths), close the Railway tunnel, verify absence, and leave unrelated Docker resources alone. Retain the existing cached image.

## File map

| File | Responsibility |
| --- | --- |
| `scripts/api_staging_restore_drill.py` | Fixed-target operator entry point: identity/health preflight, Railway tunnel, snapshot/dump, guarded Docker target, restore, comparison, backend check, cleanup, sanitized evidence. |
| `scripts/staging_restore_integrity.py` | Read-only SQL/catalog queries and typed aggregate facts used identically on source snapshot and restored target. No record-value output. |
| `services/api/tests/test_api_staging_restore_drill.py` | Fail-closed unit tests for target guard, source snapshot, command failures, evidence allowlist, and cleanup. |
| `services/api/tests/test_staging_restore_integrity.py` | Focused local PostgreSQL integration cases for constraints, orphan/semantic mismatches, and zero-row classification. |
| `Makefile` | Include both operator modules in formatting/lint/Semgrep checks and expose one explicit opt-in drill target. |
| `docs/development/staging.md` | Operator procedure and failure/cleanup instructions; link the authoritative #207 spec. |
| `docs/specs/README.md` | Link spec and plan. |
| `docs/development/staging-recovery/2026-09-22-issue-207-restore.json` | Final sanitized live outcome, created only when the drill runs. |

## Task 1: Environment-ready baseline and source preflight

**Proof:** Local tooling and target identifiers match the discovery result; no mutation occurs.

- [ ] Verify the focused worktree is clean apart from #207 files; preserve the unrelated #206 checkout. Run `./scripts/doctor.sh`, `git diff --check`, and the repository's available backend baseline. Record failures before editing runtime code.
- [ ] Verify `docker context inspect` resolves to a local Unix socket; `docker image inspect postgres:18` succeeds; `docker version`, `pg_dump --version`, `pg_restore --version`, and `psql --version` report compatible tools. Use `--pull=never` for the target image.
- [ ] Reconfirm the Staging IDs through read-only Railway status after `railway whoami` shows `Finn the Panther <finn@finnthepanther.com>`. Resolve the active API revision with the existing fixed-origin `scripts/api_staging_preflight.py` health/identity mechanism and verify Railway deployment metadata agrees. Keep full IDs transient; durable evidence records source SHA, opaque one-way resource fingerprints, and equality/health outcomes.
- [ ] Query `pg_database_size(current_database())` from the read-only source and available Docker daemon memory. Set PostgreSQL-data tmpfs to at least four times source database size and dump tmpfs to at least twice that size, with respective 2 GiB and 1 GiB floors. Refuse to start if the combined reservation exceeds half the daemon memory; record only bounded size class and the pass/fail decision.
- [ ] Keep the prior read-only PITR and volume-backup discovery as selection evidence: PITR `enabled=false`, `bucketWired=false`, no backup schedules or backup records. Do not run any enable/create/restore Railway command.

## Task 2: Guarded operator entry point and source snapshot

**Files:** `scripts/api_staging_restore_drill.py`; `services/api/tests/test_api_staging_restore_drill.py`.

**Interfaces:** `collect_integrity(query_executor, migration_leaves) -> IntegrityFacts` and `compare_integrity(source, restored) -> CheckResults` in Task 3. The source query executor uses the exported-snapshot connection; the recovery query executor sends the same read-only SQL through `docker exec ... psql`. The entry point accepts only `--confirm restore-tailtag-staging-backup`; it accepts no database URL, target service ID, hostname, or alternate environment argument.

The entry point's package-internal boundaries are `parse_tunnel_details(output: str)`, `validate_recovery_target(inspect, expected_id, image_id)`, and `cleanup_task_resources(processes, container_ids, command_runner)`. They carry actual parser, positive-target-guard and failure-cleanup responsibilities; tests may call them with controlled inputs. No new public API is created.

- [ ] Author tests first: refuse wrong Railway project/environment/Postgres ID, a missing or changed active API identity, an already existing target name, wrong Docker context/image/network/ports/tmpfs, nonempty target database, and any attempt to pass a restore URL. Confirm no `pg_dump` or `pg_restore` starts after a refused guard.
- [ ] Add tests proving the source transaction executes `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`, exports one snapshot, passes that snapshot to `pg_dump --format=custom --no-owner --no-acl --snapshot`, and keeps the exporting transaction alive until the dump process completes. A source-read or dump error must prevent restore.
- [ ] Implement a fixed-project Railway `connect Postgres --tunnel-only` subprocess. Parse the CLI's observed `Host`, `Port`, `User`, `Password`, `Database`, and `URL` labels in memory; require loopback host and a live tunnel. Pass credentials through subprocess environment variables, never command arguments or logged output. Suppress raw CLI output and bound timeouts. Reverify Railway identity before opening it.
- [ ] Stream `pg_dump` stdout directly into `docker exec -i "$RECOVERY_CONTAINER_ID" sh -c 'cat > /backup/recovery.dump'`; check both process exit codes and byte count. Keep the dump on tmpfs. Record UTC start/end and client/server versions. Validate with `docker exec "$RECOVERY_CONTAINER_ID" pg_restore --list /backup/recovery.dump` before restore.
- [ ] Implement a strict typed evidence allowlist: public source SHA, UTC timestamps/durations, version numbers, bounded counts, one-way resource fingerprints, enumerated check names/statuses, fixed limitation codes, and cleanup booleans. Never copy untrusted subprocess output or exception text into evidence. Tests reject extra keys and unsafe free-form strings. Atomic evidence writing occurs only after cleanup status is known.
- [ ] Run only `services/api/tests/test_api_staging_restore_drill.py` and Ruff on the two touched Python files; resolve failures before broader work.

## Task 3: Concrete source and restored integrity facts

**Files:** `scripts/staging_restore_integrity.py`; `services/api/tests/test_staging_restore_integrity.py`.

**Interfaces:** `collect_integrity(query_executor, migration_leaves) -> IntegrityFacts` returns applied migrations, graph leaves, named-table counts, constraint fingerprint, and named zero-violation checks. `query_executor` runs fixed parameter-free aggregate/catalog SQL and returns structured rows; source execution uses the held read-only psycopg transaction, while target execution uses `docker exec -i "$RECOVERY_CONTAINER_ID" psql --username postgres --dbname tailtag_recovery --no-psqlrc` with SQL on stdin and parses only structured aggregate output. `compare_integrity(source, restored) -> CheckResults` requires equal semantic facts and records `NOT_EXERCISED` for an empty relationship table.

- [ ] Write integration tests on a disposable local PostgreSQL 18 database for the source/restored fact schema. A changed migration set, missing expected FK/unique/check constraint, orphaned FK, duplicate `tailtag_id`, duplicate enrollment/activation/Catch key, invalid activation/session/credential state, or mismatched Catch provenance must fail. Empty optional Catch/session/credential tables must report `NOT_EXERCISED` for populated-record checks while still requiring schema/constraints.
- [ ] Implement read-only aggregate SQL from current `accounts`, `profiles`, `fursuits`, `conventions`, and `catches` models. Check `PlayerProfile.user_id` FK/one-to-one; Fursuit owner and `tailtag_id`; enrollment user/convention and active uniqueness; activation Fursuit/convention and active/deactivation pairing; session activation and time/end invariants; credential activation, token/current uniqueness and revocation pairing; Catch's five FKs, activation/Fursuit/Convention match, session/activation match and unique catch key. Count violations only; never select protected values.
- [ ] Build an independent expected table/constraint manifest from the matching revision's installed Django models and migration graph, covering built-in Django tables and `accounts`, `profiles`, `fursuits`, `conventions`, `catches`, `operator_audit`, and `rehearsal`. Query `pg_catalog.pg_constraint`, `pg_class`, `pg_attribute`, and `pg_index` for those tables, FK relationships, explicit named check/unique constraints, partial unique indexes, and automatically named key constraints. Require source and restored catalogs to satisfy the manifest, then compare canonicalized definitions and exact applied migration sets/graph leaves. Source/target agreement alone is insufficient.
- [ ] Run the focused integration test and `pg_restore --list` on a synthetic custom-format local fixture. Review plausible mutants: a dropped FK, a missing partial unique index, swapped Catch provenance, a zero-row false pass, and source counts sampled outside the exported snapshot.

## Task 4: Isolated target, real restore, and backend proof

**Files:** `scripts/api_staging_restore_drill.py`; `services/api/tests/test_api_staging_restore_drill.py`.

- [ ] Add failing tests for the full Docker guard and cleanup paths, including a failed `docker run`, failed dump transfer, invalid archive, failed `pg_restore`, failed integrity comparison, failed backend check, and interruption during the stream. Terminate and await the snapshot query, `pg_dump`, stream receiver, and Railway tunnel process groups before removing only captured task-owned container IDs; verify absence. A cleanup failure leaves `overall_outcome=FAIL` with a sanitized opaque local recovery handle.
- [ ] Create the target only after preflight using the exact pattern below. Capture Docker's returned full ID. Reject any preexisting name, any context other than the verified local Unix-socket context, or any unexpected inspect value before writing data.

```bash
RUN_NONCE="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
docker run --pull=never --detach --name "tailtag-207-recovery-${RUN_NONCE}" \
  --label tailtag.issue=207 --network none \
  --mount "type=tmpfs,destination=/var/lib/postgresql,tmpfs-size=${DATA_TMPFS_BYTES}" \
  --mount "type=tmpfs,destination=/backup,tmpfs-size=${BACKUP_TMPFS_BYTES}" \
  --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=tailtag_recovery \
  postgres:18
```

- [ ] Wait for local `pg_isready` through `docker exec`; require `SHOW server_version_num` to be PostgreSQL 18 and an empty newly created `tailtag_recovery` database. Inspect Docker `NetworkMode=none`, empty `PortBindings`, both tmpfs mounts, label, image ID, and full task container ID. The command never accepts a remote restore destination.
- [ ] Run `docker exec "$RECOVERY_CONTAINER_ID" pg_restore --exit-on-error --single-transaction --no-owner --no-acl --username postgres --dbname tailtag_recovery /backup/recovery.dump`. Check exit code and elapsed duration, then collect Task 3 facts from target through `docker exec`/local socket. Compare against source snapshot.
- [ ] Select the exact Git source SHA seen on the active Staging deployment. Resolve it in approved `TailTag-Game/tailtag` history; if absent locally, verify `FinnThePanther` immediately before an authenticated fetch, then fetch that exact revision or stop on failure. Create a disposable detached worktree at that SHA, verify its `HEAD` exactly matches, and build the existing `services/api/Dockerfile` production target from that verified context. Run a disposable command-only backend container with `--network "container:$RECOVERY_CONTAINER_ID"`, no published port, no Clerk/R2 values, and local Django settings. Set `DATABASE_URL` only to `postgresql://postgres@127.0.0.1:5432/tailtag_recovery`; use a synthetic local Django secret. Run `django.setup()` and only ORM counts/`exists()` for the named models. Do not call model saves, migrations, views, Clerk, or storage methods. Record outcomes/limitation only, then remove the backend container and detached source worktree.
- [ ] Repeat fixed-origin readiness/identity and Railway API/DB relationship checks. A changed deployment, Postgres service/volume relationship, or failed readiness makes AC-7 fail even if restore succeeded.

## Task 5: Runbook, deterministic gate, and local rehearsal

**Files:** `docs/development/staging.md`; `docs/specs/README.md`; spec/plan as needed for corrections.

- [ ] Add a #207 runbook section with the exact command, preflight, target guard, expected evidence fields, interruption/failure cleanup, and explicit prohibitions on active Staging mutation. Link the spec and plan from the spec index. Do not add a second general backup system.
- [ ] Run focused unit and PostgreSQL integration tests first, then `make api-check`, `./scripts/doctor.sh`, and `git diff --check`. Review Semgrep output and final diff for credentials, raw data, unrelated files, and dead scaffolding.
- [ ] Rehearse a complete custom-format dump/restore against synthetic local PostgreSQL 18 data using the same script's target guard, validation and cleanup. Verify task containers and dump tmpfs are absent after both success and one injected failure. Do not exercise the canonical Staging source during this rehearsal.
- [ ] Obtain an independent review of Acceptance Contract coverage, target safety, read-only source behavior, SQL correctness, evidence sanitization, and failure cleanup. Resolve BLOCKER/HIGH findings before live operation.

## Task 6: Live #207 drill and durable result

**Files:** create `docs/development/staging-recovery/2026-09-22-issue-207-restore.json` only from fixed sanitized output; update runbook/spec only for verified limitations.

- [ ] Establish an exclusive Staging observation window. Reverify approved identities and the canonical Railway target. Run the operator command once with `--confirm restore-tailtag-staging-backup`; do not use a volume restore or alter PITR, backups, variables, deployments, or Staging data.
- [ ] Require AC-1 through AC-8 results: dump and archive validity, positive target guard, completed restore, matching migrations/constraints/counts/zero-violation checks, backend ORM proof or recorded exact limitation, unchanged active Staging health/relationship, and verified task-container/dump cleanup.
- [ ] Inspect the sanitized JSON before committing it. Record each named check (`PASS`, `FAIL`, or `NOT_EXERCISED`), source snapshot/deployment/time, elapsed durations, target classification, cleanup status, limitations and follow-up. Never commit generated raw logs or the dump.
- [ ] Run `./scripts/doctor.sh`, `git diff --check`, focused tests, and the required repository validation again after the evidence/doc change. Review the complete diff and report any AC limitation plainly.

## Self-review and stop conditions

Every AC maps to Tasks 1–6. Tests map to AC-2/3/4/5/8/9 and the SECURITY, DATA INTEGRITY, and RELIABILITY assurance modifiers. No test creates a public production seam. Stop and replan if the exact source snapshot cannot be tied to the dump, Docker isolation/cleanup is weaker than specified, the observed Staging revision cannot be executed safely, a source write is needed, or a platform/API behavior invalidates the fixed path. A documented procedure or successful dump alone does not complete #207.
