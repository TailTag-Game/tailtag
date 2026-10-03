# Simulation fixture provisioning

Issue: [#220](https://github.com/TailTag-Game/tailtag/issues/220) (SIM-3).
Parent: #199. Builds on the #218 harness
([spec](2026-10-02-headless-simulation-harness.md)) and the #219 identity pool
([spec](2026-10-02-synthetic-identity-pool.md)). Later consumers: #221
(journeys), #222 (reconciliation), #223 (cleanup).

## Status and phase ledger

**APPROVED and frozen (2026-10-02).** The refinement decisions G1 to G13 were
approved on 2026-10-02. On the same day, AC6 was amended to include catches and
catch sessions. The decisions are recorded in the #220 issue body. This spec
turns them into a frozen acceptance contract (F-1 to F-14) and adds the design
details below.

Execution: STANDARD EXPANDED. Assurance: SECURITY (a new privileged Staging
channel), DATA INTEGRITY (run isolation and all-or-nothing writes), MIGRATION
(a new ledger table).

The maintainer approved this spec and the
[implementation plan](2026-10-02-simulation-fixture-provisioning-implementation-plan.md)
on 2026-10-02, including the design additions above the acceptance contract.

## Objective

Give a simulation run its own synthetic Convention, enrollments,
photo-bearing fursuits, and activations. SETUP creates them through existing
domain services, acting as the pool identities leased to that run, and records
every object in a run ledger that #222 and #223 can query by run ID. SIMULATION
stays public-API only.

## Evidence

- **Convention creation is operator-only.** There is no public create route.
  The admin form rejects creating a Convention as ACTIVE
  (`conventions/admin.py`, `ConventionAdminForm.clean_status`). A Convention
  becomes playable only through `set_convention_admin_state`
  (`conventions/services.py`). Playability is `status == ACTIVE`, and no date
  window applies (`Convention.is_playable`).
- **Player state has supported services:**
  - `enroll_in_convention(user, convention_id=, set_active=)`
  - `create_fursuit(user, name=, photo=)`
  - `set_fursuit_activation_state(user, convention_id=, fursuit_id=, is_active=True)`

  Each opens its own transaction and enforces profile eligibility, so inside an
  outer transaction they run as savepoints.
- **Image storage happens outside the transaction.** `create_fursuit` stores the
  image through `media_service.replace_image` before it commits the reference.
  Compensation only covers a failure of that one commit (`media/service.py`). If
  an outer transaction rolls back later, the image stays stored unless SETUP
  deletes it explicitly.
- **Every stored image gets a fresh key** (`images/<uuid4>.<ext>`,
  `media/keys.py`). Normalization re-encodes uploads and clears EXIF and other
  metadata (`media/images.py`).
- **Pool identities can be resolved on the server.** Pool slots hold indexes
  only, and Clerk user IDs never reach the database. An onboarded pool identity
  has the profile handle `sp_<pool>_<index>` (#219 D8), which identifies its
  `PlayerProfile` and `User`.
- **Pool identities never touch the #204 baseline** (#219 D11). The baseline
  closure check only rejects state that touches the baseline users, Convention,
  or fursuits (`rehearsal/reset.py`). Run fixtures touch none of them.
- **The privileged channel pattern already exists.** `simulation_pool/remote.py`
  checks the runtime identity before any validation or database access.
  `scripts/api_sim_pool_ssh.py` relays one JSON request over `railway ssh` to
  the pinned Staging instance and prints one fixed JSON response.

## Design

### Run ledger

A new `simulation_fixtures` Django app owns two tables. No domain table changes.

- `FixtureRun`:
  - `run_id`: 36 characters, unique.
  - `pool`
  - `status`: `provisioned` or `failed`.
  - `created_at`, `updated_at`.
- `FixtureObject`:
  - `run` (FK).
  - `kind`: `convention`, `enrollment`, `fursuit`, or `activation`.
  - `object_id`.
  - `media_key`: set only for fursuits.
  - Unique on `(kind, object_id)`.

A run ID can be provisioned at most once. A request that reuses any existing
run ID, including a failed one, is rejected.

### Provisioning

`provision(pool, run_id, owners, catchers, fursuits_per_owner)` takes explicit
lists of pool indexes for owners and catchers.

1. **Validate the request.**
   - Run ID: canonical UUID.
   - Pool name: `[a-z0-9]{1,12}`.
   - `owners`: 1 to 50 indexes.
   - `catchers`: 1 to 200 indexes.
   - `fursuits_per_owner`: 1 to 5.
   - The owner and catcher lists are disjoint and contain no duplicates.
   - The run ID has no ledger row.

   Any failure returns `FAIL_REQUEST` or `FAIL_RUN_EXISTS`, with no writes.
2. **Bind the identities**, inside one transaction. Lock the listed
   `PoolSlot` rows with `select_for_update`. Each slot must be AVAILABLE and
   leased to `run_id`, with `lease_expires_at` in the future. Each index must
   resolve to exactly one profile with handle `sp_<pool>_<index>` and completed
   onboarding. Any failure returns `FAIL_LEASE` with no writes.
3. **Check for leftover state.** An identity is dirty if it:
   - owns any fursuit,
   - has any enrollment or active convention,
   - has an avatar,
   - has any Catch row as catcher, or
   - has any catch session on its fursuits.

   Every dirty identity is quarantined through `simulation_pool.services.quarantine`
   in its own committed transaction, and the result is `FAIL_DIRTY` with the
   quarantined count. Nothing else is written.
4. **Create the Convention.** Create it as DRAFT with `full_clean()`, named
   `Sim <first 8 hex of run_id>`. Its start date is today (UTC) and its end date
   is today plus one day. Then move it to ACTIVE through
   `set_convention_admin_state`.
5. **Enroll everyone.** Call `enroll_in_convention(..., set_active=True)` for
   every owner and catcher.
6. **Create the fursuits.** For each owner, call `create_fursuit` with names
   `Sim Fursuit <owner position>-<n>` and a fixture image (below). Each call
   stores its own image object. Every stored key is recorded as soon as the call
   returns.
7. **Activate the fursuits.** Call
   `set_fursuit_activation_state(..., is_active=True)` for each fursuit in the
   run Convention.
8. **Write the ledger.** Write the `FixtureRun` (`provisioned`) and one
   `FixtureObject` per created object, then commit. Result `PASS`, with counts
   per kind.

If anything in steps 4 to 8 raises, the transaction rolls back. Every image key
recorded in step 6 is then deleted (best effort, using the same storage
backend). A separate transaction writes a `FixtureRun` row with status `failed`
and no objects. A domain rejection (an eligibility or invariant error from a
service) returns `FAIL_INVARIANT`. Anything else returns `FAIL_ERROR`. If an
image deletion fails, a fixed warning is logged with no key in it.

SETUP creates no catch session and no catch credential. Those are fursuiter
behavior, and SIMULATION or #221 creates them through the public API (G1).
Avatars are not set (G12).

### Fixture images

Images live in `services/api/simulation_fixtures/images/`, which the maintainer
fills with JPEG, PNG, or WebP files. Each file:

- is at most 512 KB and 2048 px on its longest side,
- shows no people and nothing that identifies anyone,
- carries no EXIF, XMP, GPS, or camera metadata.

A test enforces the size, format, and metadata limits. A human reviews content
in the PR. Files are used in sorted filename order, cycling. If the folder holds
no images, SETUP generates a deterministic 512×512 PNG per fursuit with Pillow,
which is already a dependency. Either way each fursuit goes through
`create_fursuit`, so it gets its own normalized stored object. No run fursuit
ever uses the #204 baseline media key.

### Privileged channel

- **`simulation_fixtures/remote.py` `execute(request, runtime_identity, environ)`**
  checks `RAILWAY_ENVIRONMENT_NAME=staging`, `RAILWAY_SERVICE_NAME=api`, and an
  exact identity match before validating or touching anything else. This is the
  same check as `simulation_pool/remote.py`. The operations form a closed set:
  - `provision`
  - `status(run_id)`, which returns the run status and counts per kind.
- **`scripts/api_sim_fixture_ssh.py`** reuses the pinned helpers from the #219
  launcher: Railway identity, preflight, target IDs, and active instance. It
  sends the request on stdin, enforces the 64 KB request limit, and prints one
  validated response. Make target: `api-sim-fixture-ssh`.
- **Output** is a fixed result code plus counts. Responses never carry database
  IDs, Clerk IDs, handles, media keys, or tokens.

There is no local or Development relay (G9). Unit and Django tests cover the
domain function and the entry point.

### Simulator: `fixture-smoke`

This is the host-only Staging proof for F-14 and the template #221 will extend.

- **Target:** verify Staging, as in the existing smoke runs.
- **SETUP:**
  - Allocate `owners + catchers` pool identities and open them. This reuses the
    #219 setup: instance pin, marker checks, session redemption, and profile
    onboarding.
  - Call the fixture channel's `provision`, with the first `owners` indexes as
    owners and the rest as catchers.
  - The fixture channel is a protocol on the setup inputs, alongside the lease
    channel. Tests use an in-memory fake.
- **SIMULATION** (public reads only):
  - Each identity reads `GET /api/conventions/active/`.
  - Each owner reads `GET /api/fursuits/` and that Convention's activation list.
- **RECONCILIATION:**
  - Every identity sees the same active Convention.
  - Each owner sees `fursuits_per_owner` enabled fursuits with photo URLs, all
    activated in that Convention.
- **Release:** leases are released even after a failure. Fixtures stay in
  place. Each identity used is now dirty and is quarantined the next time it is
  provisioned, until #223 cleanup or a maintainer readmit.

Make target: `sim-fixture-smoke POOL=<p> OWNERS=<n> FURSUITS=<k> CATCHERS=<m>`.
The defaults are 2, 1, and 2.

### Relationship to #204, #222, and #223

- #204 owns the global baseline. #220 never reads or changes the baseline or its
  media key, and pool identities stay disjoint from it.
- #222 and #223 find a run's objects through the ledger (`status` now, a fuller
  read later) by run ID.
- #223 owns deleting run objects and their images, closing run Conventions, and
  readmitting identities.

## Acceptance contract (frozen)

- **F-1 Run state** (AC1, G1, G6). A valid `provision` creates:
  - one ACTIVE Convention named `Sim <8 hex>`,
  - an active enrollment with the active convention set for every owner and
    catcher,
  - `fursuits_per_owner` enabled fursuits per owner, each with a photo,
  - an active activation for each fursuit in that Convention.

  All of it is created through the services named above. The only direct model
  write is the DRAFT Convention, validated with `full_clean()`.
- **F-2 Configuration** (AC2). These are rejected with `FAIL_REQUEST` before any
  write:
  - `owners` outside 1–50, `catchers` outside 1–200, or `fursuits_per_owner`
    outside 1–5,
  - duplicate or overlapping indexes,
  - a malformed run ID or pool name.
- **F-3 Boundary** (AC3). SETUP creates no catch session and no catch credential.
  `SimulationContext` and the SIMULATION boundary Semgrep rules are unchanged and
  pass.
- **F-4 Ledger** (AC4). Every object created by a successful `provision` has
  exactly one `FixtureObject` row under its `FixtureRun`. No domain table gains a
  column.
- **F-5 Binding** (AC5, G13). If any listed slot is not AVAILABLE, not leased to
  this run, or has an expired lease, or if any handle does not resolve to an
  onboarded profile, the result is `FAIL_LEASE` with no writes.
- **F-6 Isolation** (AC6, amended). A dirty identity is quarantined and the
  result is `FAIL_DIRTY` with no domain or ledger writes. Dirty means it owns
  any fursuit, has any enrollment or active convention, has an avatar, has any
  Catch as catcher, or has any catch session on its fursuits. Any reuse of a run
  ID returns `FAIL_RUN_EXISTS`. Two successful runs share no Convention,
  enrollment, fursuit, activation, or media key.
- **F-7 Target** (AC7). The entry point refuses (`FAIL_TARGET`) unless the
  runtime is the Staging `api` service and the identity matches exactly. This is
  checked before request validation and before any database access. No
  simulator target, Make target, or relay can reach `provision` on local,
  Development, or Production.
- **F-8 Output** (AC8). Remote, relay, and simulator output contain only result
  codes, run IDs (simulator only), counts, and the source SHA. They
  never contain database IDs, Clerk IDs, handles, media keys, tokens,
  credentials, or secrets.
- **F-9 Atomicity** (AC9). After a failure in steps 4 to 8, no domain rows from
  the attempt remain, the images it stored are deleted, and the ledger holds one
  `failed` run with zero objects.
- **F-10 Images** (AC10). Every run fursuit has a distinct media key, not equal
  to the #204 baseline key. Committed fixture images meet the format, size, and
  metadata limits (test-enforced). With an empty folder, generated images are
  used.
- **F-11 No avatars** (AC11). SETUP sets no profile avatar.
- **F-12 Tests** (AC12). Django tests cover F-1, F-2, F-4 to F-7, F-9, F-10, and
  F-11. Relay and simulator tests cover F-7 and F-8 at the subprocess and
  in-memory channel seams.
- **F-13 Docs** (AC13). The simulator README and this spec document:
  - invocation, configuration, and defaults,
  - result codes and failure behavior,
  - the ledger and the hand-off to #222 and #223,
  - the relationship to #204,
  - the quarantine consequence until #223.
- **F-14 Staging proof** (AC14). The migration reaches Staging through controlled
  promotion. One maintainer-run `sim-fixture-smoke` with the defaults passes,
  and its sanitized output (result codes and counts) is recorded below.

## Reversibility

TWO-WAY DOOR. The ledger tables are additive and only the simulator reads them.
The migration also applies on Production because the codebase is shared. The
tables stay empty there, since the entry point refuses any runtime that isn't
Staging. Rolling back means removing the app and its migration. Fixture images
ship in every API image, Production included, and the maintainer accepted that
(G5).

## Non-goals

- Catch sessions, catch credentials, and avatars.
- Player journeys (#221), reconciliation (#222), cleanup, run Convention
  closing, or readmits (#223).
- Changes to the #204 baseline or to #219 lease semantics.
- New public API or product behavior, `run_id` columns on domain tables, a
  local or Development relay, and Production.
