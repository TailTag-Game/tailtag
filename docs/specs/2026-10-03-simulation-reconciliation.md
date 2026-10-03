# Simulation expected-state and backend reconciliation

Issue: [#222](https://github.com/TailTag-Game/tailtag/issues/222) (SIM-5).
Parent: #199. It builds on:

- the #218 harness ([spec](2026-10-02-headless-simulation-harness.md))
- the #219 identity pool ([spec](2026-10-02-synthetic-identity-pool.md))
- #220 fixture provisioning ([spec](2026-10-02-simulation-fixture-provisioning.md))
- the #221 journeys ([spec](2026-10-03-headless-acceptance-journeys.md))

Later consumers: #223 (cleanup), #224 (run reports), and #229 (performance evidence).

## Status and phase ledger

**APPROVED (2026-10-03).** The maintainer approved this spec and its plan on 2026-10-03. The refinement decisions G1 to G13 were
approved on 2026-10-03 and are posted on
[#222](https://github.com/TailTag-Game/tailtag/issues/222#issuecomment-5973141437).
One later correction lowered the `inspect` record cap from 500 to 200
([comment](https://github.com/TailTag-Game/tailtag/issues/222#issuecomment-5973157533)).
This spec turns those decisions into an acceptance contract (R-1 to R-15) and adds
the design below.

Execution: STANDARD EXPANDED.

Assurance:
- SECURITY: a new privileged read path into Staging, and no secrets or identifiers
  in output.
- DATA INTEGRITY: Catch rows are the authority, so correctness is a hard gate.

Implementation plan:
[simulation reconciliation implementation plan](2026-10-03-simulation-reconciliation-implementation-plan.md).

## Objective

After a `sim-journeys` run, prove that three views of the run agree:

- the simulator's expected state
- the Catch rows persisted on Staging
- each run identity's public catch history

A successful HTTP response is not enough evidence on its own. The run fails unless all
three agree.

## Evidence

Paths are under `services/api/` unless noted.

- **Catch** (`catches/models.py`) has these fields:
  - `catcher_user`
  - `fursuit`
  - `convention`
  - `activation`
  - `catch_session`
  - `caught_at` (`auto_now_add`)

  It is unique on (catcher, fursuit, convention). The database therefore makes a
  same-Convention duplicate impossible. The duplicate check remains as defense in
  depth and because the uniqueness scope could change.
- **Activation and session.**
  - `FursuitActivation` has `fursuit`, `convention`, and `is_active`.
  - `FursuitCatchSession` has `activation`, `started_at`, `expires_at`, and
    `ended_at` (`conventions/models.py:161`, `:224`).
- **Identities start clean.** `provision` rejects an identity with `FAIL_DIRTY` if it
  has any fursuit, enrollment, avatar, or catch (`simulation_fixtures/services.py:236`).
  Every run identity therefore has zero catches anywhere when the run starts.
  The unprovisioned outsider passed the same lease, but `provision` never checks it.
  The pool smoke and readmit flows never create catches, so in practice the outsider
  is clean too. R-3 handles this by treating any outsider catch as a discrepancy.
- **Run attribution.**
  - `FixtureRun(run_id)` records `created_at`.
  - `FixtureObject` records the run's Convention, enrollments, fursuits (with
    `media_key`), and activations.
  - Until RELEASE, `PoolSlot.run_id` and `lease_expires_at` tie every leased index to
    the run, including the outsider. `_leased_to` (`simulation_fixtures/services.py:210`)
    is the existing check.
  - Identity resolution uses the handle `sp_<pool>_<index>` (`services.py:239`).
- **Read-only precedent.** `transaction.atomic()` followed by `SET TRANSACTION READ
  ONLY` already guards Staging diagnostics (`scripts/api_staging_managed_auth_diagnose.py:147`,
  plus three operator commands). PostgreSQL rejects any write in that transaction.
- **Relay pattern.** `scripts/api_sim_fixture_ssh.py` resolves the pinned Staging
  instance and sends a fixed bootstrap through `railway ssh`. The bootstrap reads at
  most 64 KiB of request from stdin, runs `django.setup()`, calls one remote
  `execute`, and prints one validated `{"result", "data"}` JSON. The remote checks the
  target identity before any database access (`simulation_fixtures/remote.py`).
- **Launcher limit.** The simulator rejects launcher output over 65536 bytes
  (`tools/simulator/tailtag_simulator/pool.py:52`).
- **Public reads.**
  - `POST /api/catches/confirm/` returns `catch: {id, caught_at, convention_id,
    fursuit}`.
  - `GET /api/catches/?convention_id=<c>&page_size=100` returns `{catch_count, next,
    previous, results: [{id, fursuit: {id, …}, convention, caught_at}]}`. It shows
    only the caller's own catches as catcher.
  - Both endpoints format `caught_at` as UTC ISO 8601 with a `Z` suffix
    (`catches/serializers.py:374`, `:406`).
  - No public endpoint shows owners the catches made of their fursuits.
- **The journeys** (`tools/simulator/tailtag_simulator/journeys.py`) attempt confirms
  on the pairs below. Here `oXfY` means owner X's fursuit at sorted position Y.

  | Journey | Confirming role | Fursuit | Creates a catch? |
  | --- | --- | --- | --- |
  | `catch` | catcher0 | o0f0 | yes (201) |
  | `retry` | catcher0 | o0f0 | no, it returns the same catch (200) |
  | `stopped_session` | catcher1 | o0f1 | no |
  | `stale_credential` | catcher1 | o1f0 | no |
  | `deactivated` | catcher2 | o1f1 | no |
  | `self_catch` | owner1 | o1f0 | no |
  | `convention_mismatch` | catcher3 | o1f0 | no |
  | `ineligible_catcher` | outsider | o1f0 | no |

  Media writes:
  - `avatar`: catcher2 sets an avatar, replaces it, then clears it.
  - `fursuit_photo`: owner0 creates one fursuit and replaces its photo once.
  - `image_rejections`: three uploads to that fursuit are rejected.
  - No journey writes to a #220 fixture fursuit's photo.

## Design

### Run flow

`sim-journeys` keeps the #221 flow and inserts RECONCILIATION between SIMULATION and
RELEASE:

```text
target → RUN line → SETUP (lease, onboard, provision) → SIMULATION (13 journeys)
       → RECONCILIATION (history reads, inspect, compare) → RELEASE
```

- RECONCILIATION runs once SETUP has passed, whether SIMULATION passed or failed.
  "Failed" here means journey failures. If the SIMULATION stage itself crashes, for
  example because a client cannot be opened, it prints `FAIL simulation` and skips
  reconciliation, and RELEASE still runs. The U2 review accepted this as a limitation
  (L-1).
- If SETUP failed, it does not run.
- RELEASE keeps its existing guarantee and runs after a reconciliation failure, an
  exception, or an interrupt.
- Expected state is held only in memory.

### Roles

The roles are fixed by lease order, exactly as in #221:

- `owner0` and `owner1`
- `catcher0` to `catcher3`
- `outsider`

Each role maps to the pool index it leased. Pool indexes are sent to `inspect`. They
never appear in output, where only role labels are printed.

### Expected state (simulator)

`_Run` gains an `Expectations` record. The journey loop sets the current journey
name. Exactly two journeys are positive, meaning they are meant to produce a catch:
`catch` and `retry`. Each journey records three kinds of fact:

- `attempt(role, fursuit_id)` before every confirm. This records that the journey
  attempted the pair.
- `created(role, fursuit_id, catch_id, caught_at)` from a 201 `created` response.
  Only a positive journey records it. A 201 in any other journey is already a journey
  failure. Reconciliation then reports the resulting row as `unexpected`.
- `confirmed(role, fursuit_id, catch_id, caught_at)` from each 200 `already_caught`
  response in a positive journey. The retry convergence check uses these.

Each attempted pair is classed in one of three ways:

- **Required:** a positive journey recorded `created` for the pair. Exactly one DB
  catch must exist, with that id and `caught_at`.
- **At most one:** a positive journey attempted the pair, but no `created` was
  recorded, because a lost or failed response may still have written a row.
  Uniqueness still applies, and there is no `missing` alarm.
- **Forbidden:** only non-positive journeys attempted the pair. Zero catches must
  exist.

The world is closed. Any catch in the inspected scope that is not required, or
allowed as at-most-one, is a discrepancy. When some journey attempted the pair, the
discrepancy names that journey; otherwise the journey is `-`.

### `inspect` (privileged, read-only)

The new modules live inside the existing `simulation_fixtures` app, so no new app,
model, or migration is needed:

- `services/api/simulation_fixtures/inspection.py`: the query
- `services/api/simulation_fixtures/inspection_remote.py`: the `execute` entry point.
  It accepts only the `inspect` operation and checks the target identity the same
  way `remote.py` does.
- `scripts/api_sim_inspect_ssh.py`: the relay. Its bootstrap imports only
  `inspection_remote`, so this channel has no route to `provision` or `status`.
- `make api-sim-inspect-ssh`: the Make target.

Request arguments are exactly `{pool, run_id, identities: {<role>: <index>}}`, with
all seven roles. Any other shape is `FAIL_REQUEST`.

Every query runs in one `transaction.atomic()` whose first statement is `SET
TRANSACTION READ ONLY`. The steps are:

1. **Lease guard (G13).** Every given index must be leased to `run_id`, using the
   same rule as `_leased_to`. Otherwise return `FAIL_LEASE`. If `FixtureRun(run_id)`
   is unknown, or is not `provisioned`, return `FAIL_RUN_UNKNOWN`.
2. **Resolve.** Map each index to its user through the handle `sp_<pool>_<index>`.
   Read the run Convention and the ledger fursuits from `FixtureObject`.
3. **Catch scope (G5).** The scope is the union of three sets: catches whose catcher
   is a run identity, catches in the run Convention, and catches on a fursuit owned
   by a run identity. If the scope holds more than 200 catches, return `FAIL_LIMIT`.
4. **Fursuit scope.** Collect fursuits owned by run identities that are not in the
   ledger. If there are more than 200, return `FAIL_LIMIT`.

The `PASS` data shape is fixed:

```json
{
  "catches": [{
    "id": 1, "catcher": 12, "fursuit": 34, "fursuit_owner": 10,
    "run_convention": true, "provenance": true, "in_window": true,
    "caught_at": "2026-10-03T19:41:53.769123Z"
  }],
  "fursuits": [{"id": 35, "owner": 10}],
  "fixture_photos_unchanged": true,
  "avatars": []
}
```

The fields are:

- `catcher` and `fursuit_owner`: the pool index, or `null` when the person is not a
  run identity.
- `provenance`: true when all of these hold:
  - the catch's session belongs to the catch's activation
  - that activation's fursuit and Convention equal the catch's
- `in_window`: true when `FixtureRun.created_at ≤ caught_at ≤` the transaction's
  `now()`.
- `caught_at`: formatted exactly as the history serializer formats it.
- `fixture_photos_unchanged`: every ledger fursuit's `photo_key` equals its
  `media_key`.
- `avatars`: the sorted pool indexes of run identities whose `avatar_key` is not null.

Records are sorted by id. With 200 catches the payload is about 34 KB, which fits
the 64 KiB launcher cap. The relay rejects any output that does not match this
schema exactly, and reports it as `FAIL_LAUNCHER`.

### Comparison (simulator)

`tailtag_simulator/reconciliation.py` makes the comparison:

1. **History reads.** For each of the seven roles, call `GET
   /api/catches/?convention_id=<run>&page_size=100` through that role's public
   client, then call `inspect` once through the inspection channel.
2. **Checks.** Each check produces zero or more discrepancies. The `Check` enum
   below is in output order:

| Check | Fails when |
| --- | --- |
| `inspect` | `inspect` returned a non-`PASS` result, or the launcher failed. No further checks run. |
| `contamination` | A catch in scope has a `null` catcher or `fursuit_owner`, or `run_convention` is false. |
| `duplicate` | More than one catch shares (catcher, fursuit) in the run Convention. |
| `missing` | A required pair has no catch. |
| `unexpected` | A catch exists for a forbidden pair, or for a pair no journey attempted. |
| `catch_id` | The DB id differs from the id the confirm response returned for a required pair. |
| `caught_at` | The DB, `created`, `confirmed`, and history `caught_at` values disagree. |
| `provenance` | `provenance` is false. |
| `window` | `in_window` is false. |
| `history` | A role's history results are not exactly its DB catches in the run Convention, matched by (id, fursuit id). |
| `count` | A role's `catch_count` does not equal its DB catch count in the run Convention. |
| `fixture_photo` | `fixture_photos_unchanged` is false. |
| `created_fursuit` | The non-ledger fursuits are not exactly {the `fursuit_photo` fursuit, owned by `owner0`}. If that journey failed before its 201, the expected set is empty. |
| `avatar` | `avatars` is not empty. |

3. **Result.** The run gets a typed `ReconciliationResult`:
   - `passed: bool`
   - `discrepancies: tuple[Discrepancy, ...]`, where each `Discrepancy` is
     `(check: Check, journey: str | None, role: Role | None, expected: int,
     observed: int)`

   Discrepancies are sorted by check order, then by journey order (`JOURNEY_NAMES`),
   then by role order. #223 and #229 consume this value. #224 owns how it is written
   to a durable report.

### Comparison conventions

The U2 tests fixed these details, and the parent approved them on 2026-10-03.

- **Contamination comes first.** A catch is `contamination` when its catcher or
  fursuit owner is not a run identity, or its Convention is not the run's. A
  contaminating catch is reported only as `contamination`, with journey `-` and
  role `-`. Every other catch goes through the pair checks.
- **Journey label.** When two journeys attempted a pair, the line names the first
  of them in journey order. For example, catcher0 × o0f0 is labelled `catch`.
- **Counts.** The `expected` and `observed` fields are:

  | Check | `expected` | `observed` |
  | --- | --- | --- |
  | `duplicate` | 1 | rows found |
  | `unexpected` | 0 | rows found |
  | `contamination` | 0 | rows found |
  | `history` | DB rows | history results |
  | `count` | DB rows | `catch_count` |
  | `created_fursuit` | expected fursuits | found fursuits |
  | `avatar` | 0 | 1 |

  `avatar` uses the role of the avatar's owner.
- **Duplicates.** A duplicate on a required pair reports only `duplicate`. More
  than one row on a forbidden or unattempted pair reports both `unexpected` and
  `duplicate`.
- **Unreadable history.** A history read that fails, or returns a malformed
  response, gives that role `history` and `count` discrepancies, with observed 0.
- **Unknown result codes.** An unknown `inspect` result code becomes
  `FAIL_LAUNCHER`, in both the channel and the printer.
- **History reads** use `page_size=100`.
- **Unknown Convention.** If SIMULATION never learned the run Convention,
  reconciliation reads it through catcher0's `GET /api/conventions/active/`. If
  that read fails, reconciliation fails closed: exit 1, fixed lines only.

### Output

The new lines follow the journey lines and come before the release line:

```text
PASS reconciliation checks=14
FAIL reconciliation result=<FAIL_*>
FAIL reconciliation check=<check> journey=<name|-> role=<role|-> expected=<n> observed=<n>
FAIL reconciliation discrepancies=<n>
FAIL reconciliation
```

The bare `FAIL reconciliation` line is the existing stage-failure line. It appears
when reconciliation fails for a reason other than `inspect`, for example when the
unknown-Convention read fails.

- `checks=14` counts the `Check` members.
- The `result=` line appears only when `inspect` failed. The `result` value comes
  from the relay's fixed set of result codes, and any other value is printed as
  `FAIL_LAUNCHER`.
- When at least one discrepancy is found, one `check=` line prints per discrepancy,
  followed by a `discrepancies=` summary line.
- The `expected` and `observed` values are counts. For value checks such as
  `catch_id`, `caught_at`, `provenance`, `window` and `fixture_photo`, they are 1
  for "agrees" and 0 for "disagrees".
- Nothing else is printed. That excludes tokens, payloads, bodies, URLs, DB ids, pool
  indexes, handles, Clerk ids, media keys, and timestamps.
- The existing `PASS target staging source_sha=…` and `RUN run_id=…` lines provide
  run identity.
- Exit is 0 only when every stage, every journey, and reconciliation all pass.

### Boundary

- **SIMULATION** still receives only `JourneyContext`, which holds public clients.
  It gains no channel, prompt, or index.
- **RECONCILIATION** receives three things: the `Expectations`, the role→client and
  role→index maps, and the inspection channel. Its only public calls are the history
  `GET`s.
- **Channels.** The fixture channel is not passed to RECONCILIATION, and the
  inspection channel is not passed to SETUP or SIMULATION.
- **Imports.** The simulator still imports no Django, ORM, or Clerk SDK code.

## Acceptance contract

- **R-1 Placement** (AC1, G1).
  - RECONCILIATION runs after SIMULATION and before RELEASE, only once SETUP has
    passed, and whether SIMULATION passed or failed.
  - RELEASE still runs after a reconciliation failure, an exception, or an interrupt.
  - No expected state is written to disk.
- **R-2 Closed-world expectations** (AC2, G4). The journeys record attempted,
  created, and confirmed facts as described under Expected state. With the current
  13 journeys there is exactly one required pair (catcher0 × o0f0) and six forbidden
  pairs:
  - catcher1 × o0f1
  - catcher1 × o1f0
  - catcher2 × o1f1
  - owner1 × o1f0
  - catcher3 × o1f0
  - outsider × o1f0 Any other catch in scope is a
  discrepancy.
- **R-3 Scope** (AC3, G5). `inspect` returns the union described in step 3. A catch by
  any run identity, the outsider included, in the run Convention or anywhere else, is
  visible to the comparison.
- **R-4 Inspect contract** (AC4, G3, G13). These behave exactly as described:
  - the request shape
  - the lease guard: `FAIL_LEASE`, and `FAIL_RUN_UNKNOWN` for an unknown or
    unprovisioned run
  - the cap of 200 catches and 200 fursuits: `FAIL_LIMIT`
  - the fixed `PASS` data shape
  - the relay's exact-schema validation

  At the cap the response stays under 65536 bytes.
- **R-5 Discrepancy detection** (AC5). Each `Check` in the table fails on its
  condition, and nothing else causes it to fail.
- **R-6 Timestamps** (AC6, G7). The `caught_at` and `window` checks behave as
  described.
- **R-7 Read-side privacy and counts** (AC7, G8). For all seven roles, the `history`
  and `count` checks behave as described. With the current journeys, every role
  other than catcher0 has an empty history and `catch_count` 0.
- **R-8 Media ownership** (AC8, G10). The `fixture_photo`, `created_fursuit`, and
  `avatar` checks use database fields only. Storage is never contacted.
- **R-9 Read-only privileged path** (AC9, G2).
  - **Transaction:** the first statement in `inspect` is `SET TRANSACTION READ ONLY`,
    and a write attempted inside that transaction raises.
  - **Separate path:** `inspection_remote` accepts only `inspect`, and the relay's
    bootstrap imports only `inspection_remote`.
  - **Target check:** the request identity is verified before any database access.
  - **Contexts:** the simulator's inspection channel is never reachable from SETUP
    or SIMULATION, and `JourneyContext` is unchanged.
  - **Semgrep:** the simulator Semgrep rules pass.
- **R-10 Partial failure** (AC10, G9). When `catch` fails after its `attempt` and no
  `created` was recorded, its pair is at-most-one, and every forbidden pair still
  applies. Exit is 0 only when
  every stage, every journey, and reconciliation all pass.
- **R-11 Output** (AC11, G6). Output consists only of the lines above, in
  deterministic order. A sentinel scan over every failure path finds no token,
  payload, body, URL, DB id, pool index, handle, Clerk id, media key, or timestamp.
- **R-12 Typed result** (AC12, G6). `ReconciliationResult` and `Discrepancy` are
  immutable and built from enums and integers. `run_journeys` derives its exit code
  from the result. No report file is written.
- **R-13 Offline proof** (AC13, G12).
  - `make sim-check` covers R-1, R-2, R-5 to R-8, R-10, R-11, and R-12 against
    in-memory fakes.
  - `make api-check` covers R-3, R-4, and R-9 on PostgreSQL.
  - Neither needs secrets or a network.
- **R-14 Staging proof** (AC14, G12). One maintainer-run `make sim-journeys` passes on
  Staging, on a pool with at least 7 clean identities. Its sanitized output is
  recorded at the end of this spec.
- **R-15 No product change** (AC15). There is no public API, gameplay, schema, or
  migration change. The additions are the read-only inspection modules, the relay
  script, and the Make target.

## Reversibility

TWO-WAY DOOR overall:

- There is no schema, migration, or public API change.
- The `inspect` wire shape is internal to this repository's simulator and relay.
- Rolling back means reverting the commit.

The privileged path is a new trust boundary. It is bounded in four ways:

- it is read-only at the PostgreSQL level
- it is Staging-only, through the target-identity check
- it is lease-gated
- its output is a fixed schema

The `inspect` shape becomes a contract for #223 and #224. Changing it later means
updating the simulator and the relay together.

## Non-goals

- Cleanup, readmit, or any repair of the data a run leaves behind (#223).
- A durable report file or report schema (#224).
- A standalone `sim-reconcile RUN=<id>` command, or reconciling after RELEASE.
- A read-only PostgreSQL role.
- Contacting object storage.
- Reconciliation for `sim-fixture-smoke`.
- Owner-side catch views, because the API has none.
- Scale beyond 200 catches. That belongs to #226.
- Changes to journey behavior, the #219 lease contract, or the #220 `provision`
  contract.

## Staging proof record (R-14)

Pending.
