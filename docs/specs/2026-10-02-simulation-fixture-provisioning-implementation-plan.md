# Simulation fixture provisioning implementation plan

Spec: [simulation fixture provisioning](2026-10-02-simulation-fixture-provisioning.md)
(#220, acceptance contract F-1 to F-14). This plan sequences the work and
fixes interfaces. The spec stays authoritative for behavior.

## Phase ledger

Scope: STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY, MIGRATION.
Completed: refinement (G1 to G13, AC6 amended), reconnaissance, spec and plan
(approved 2026-10-02), unit A (tests, implementation, review). Current: unit B.
Pending:
- unit B with independent tests, implementation, and review
- whole-change review
- maintainer adds fixture images
- maintainer Staging rollout: controlled promotion with the migration, then
  `sim-fixture-smoke` (F-14)

Unit A review dispositions (no BLOCKER, HIGH, or MEDIUM):

- LOW-1, documented in unit B: a failure at transaction commit (for example a
  lost connection) surfaces as `FAIL_BOOTSTRAP`. It writes no failed run and
  leaves any stored images for #223, because the commit outcome is unknown.
- LOW-2, fixed: `provision` dropped its `storage` keyword. Fursuit images
  always use the default media storage, so compensation must too.
- LOW-3, fixed: four remote test cases that repeated service-level
  configuration checks were removed.
- LOW-4, declined: the dirty-identity quarantine loop stops at the first slot
  whose lease has lapsed. The rest stay dirty and are quarantined by the next
  provision, so it heals itself.
- The remote target check and launcher bootstrap are verbatim copies of the
  pool versions. A future fix to either must be applied to both.
- Unit B must provision before any heartbeat runs concurrently on the same
  slots, so that provisioning locks and lease updates never interleave.

## Review units

### Unit A — API: ledger, provisioning, remote entry, relay

Files:
- `services/api/simulation_fixtures/`: app, models, migration, `services.py`,
  `images.py`, `remote.py`, `images/.gitkeep`
- settings `INSTALLED_APPS`, and the tooling registration that mirrors
  `simulation_pool` (Pyright include, lint lists, `_PACKAGES` if the reset bundle
  requires it)
- `scripts/api_sim_fixture_ssh.py`
- Make target `api-sim-fixture-ssh`
- tests

Interfaces:
- `services.provision(pool, run_id, owners, catchers, fursuits_per_owner) -> ProvisionResult`.
  It returns the result code plus counts per kind, and raises nothing for the
  documented failures. The quarantine call for dirty identities commits
  independently of the rolled-back provisioning transaction.
- `services.status(run_id) -> RunStatus | None`, with status and counts only.
- `images.fixture_image(position: int) -> File[bytes]`. It cycles through the
  committed folder in sorted order, or generates a deterministic PNG when the
  folder is empty.
- `remote.execute` mirrors `simulation_pool/remote.py`: the same identity check
  first, a closed operation table, and exact argument key sets. Results:
  - `PASS`
  - `FAIL_REQUEST`, `FAIL_TARGET`, `FAIL_RUN_EXISTS`, `FAIL_LEASE`
  - `FAIL_DIRTY` (with `quarantined`)
  - `FAIL_INVARIANT`, `FAIL_ERROR`
- The launcher mirrors `scripts/api_sim_pool_ssh.py`, including its bootstrap
  program and the `FAIL_BOOTSTRAP` and `FAIL_LAUNCHER` codes. Shared helpers come
  from the same `_reset_ssh` imports. Copy the bootstrap rather than introducing
  a shared abstraction. Two launchers do not justify one yet.

Failure modes to protect (test value map):

| Failure | Contract | Cheapest level |
| --- | --- | --- |
| Valid request produces wrong shape, a missing ledger row, or a shared or baseline media key | F-1, F-4, F-10 | One Django service test asserting the full state |
| Out-of-range or overlapping configuration writes anything | F-2 | Parameterized service test |
| Slot not leased to this run, expired, quarantined, or handle not onboarded still provisions | F-5 | Parameterized service test |
| Dirty identity (each of the six kinds) not quarantined, or partial writes made | F-6 | Parameterized service test |
| Run ID reuse (provisioned or failed) accepted | F-6 | Service test |
| Failure after at least one stored image leaves rows or images | F-9 | Service test with in-memory storage and a fault injected into the last fursuit's activation |
| Entry point runs outside Staging or touches the DB before the identity check | F-7 | Entry-point test, mirroring the pool tests |
| Response or launcher output carries IDs, handles, or keys | F-8 | Entry-point and launcher tests |
| Committed fixture image too large, wrong format, or carrying metadata | F-10 | Test over the images folder (passes vacuously while empty) |
| Generated fallback is not deterministic or fails normalization | F-10 | Folded into the full-state test via an empty-folder configuration |
| SETUP sets avatars or sessions, or creates credentials | F-3, F-11 | Assertions inside the full-state test |

Not planned: a separate concurrency test. Step 2 locks the leased slots for the
whole transaction, and #219 already protects allocation races with real
PostgreSQL.

### Unit B — simulator: fixture channel and `fixture-smoke`

Files:
- `tools/simulator/tailtag_simulator/fixtures.py`
- `__main__.py` subcommand
- Make target `sim-fixture-smoke`
- `tools/simulator/README.md`
- tests

Interfaces:
- A `FixtureChannel` protocol with a launcher-backed implementation that runs
  `make -s api-sim-fixture-ssh` as a subprocess, mirroring `LauncherChannel`.
  Tests use an in-memory fake.
- `run_fixture_smoke(pool, owners, fursuits_per_owner, catchers, *, prompt_secret, lease_channel, fixture_channel, emit, ...)`.
  It reuses the #219 setup to allocate and open identities, then calls
  `provision`. SIMULATION receives only per-identity public clients and runs the
  reads in the spec. RECONCILIATION checks those reads. Release always runs.
- Simulator output: fixed stage lines, the run ID, and counts (F-8).

Failure modes: SIMULATION reaching the fixture or lease channel (F-3, covered
structurally by the existing Semgrep boundary rules); leases not released after
a provisioning failure; a `FAIL_DIRTY` result not surfaced as a fixed stage
line; IDs or handles in output (F-8).

Refactor allowance: extract the #219 pool smoke's allocate-and-open step so
both runs share it, keeping `run_pool_smoke` behavior unchanged. This is
allowed only as far as needed to avoid duplicating `_setup`.

## Sequencing

A, then B. Each unit gets an independent test author, an implementer, and a
reviewer (Opus). A final whole-change review covers both. Docs and the README
land with B.

Required validation before PR:
- `make api-check` and `make sim-check`
- `make api-semgrep-check` (stage new files first: Semgrep skips untracked files)
- `ruff` with `--no-cache` for the new modules
- `./scripts/doctor.sh` and `git diff --check`

The Staging rollout (F-14) is a maintainer step after merge readiness. It is not
automated here.
