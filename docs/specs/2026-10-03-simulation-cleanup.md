# Simulation cleanup and failed-run retention

Issue: #223 (parent #199). Refinement: approved 2026-10-03 (decisions G1 to G13, all
recommendations). Builds on #219 (identity pool), #220 (fixture ledger), #221 (journeys)
and #222 (reconciliation). Related: #204 (global Staging reset), #224 (run reports).

## Summary

A Staging simulation run leaves state behind:

- its ledger objects: the Convention, enrollments, fursuits and activations
- what the journeys add: catches, catch sessions, rotated credentials, the
  journey-created fursuit, and stored images

Today every identity a run used stays dirty. The next `provision` then quarantines it
(`FAIL_DIRTY`).

This change adds a per-run lifecycle:

- **A passing run cleans itself.** CLEANUP runs after RECONCILIATION and before
  RELEASE. It deletes exactly the run's state under a closed-world attribution rule,
  deletes the run's images, verifies the identities are clean, and readmits them.
- **A failing run is retained.** Its slots are quarantined instead of released, and the
  ledger row becomes `retained` with a fixed reason. Its state stays for investigation.
- **A maintainer cleans retained and older runs later** with `sim-cleanup`, and lists
  them with `sim-retained`. A global cap of 5 retained runs bounds the clutter.

## Design

### Ledger (G13, G5, G6)

One migration on the Staging-only `simulation_fixtures` tables:

- `FixtureRun.status` gains `retained` and `cleaned`. `provisioned` and `failed` are
  unchanged.
- `FixtureRun.reason` is nullable. It is one of `journeys`, `reconciliation`, `cleanup`
  or `interrupted`, and is required when the status is `retained`. It is kept after
  cleaning as history.
- `FixtureRun.cleaned_at` is nullable. It is set exactly when the status is `cleaned`.
- `FixtureRun.cleanup_counts` is nullable JSON. It holds deleted-object counts per kind,
  and setting it marks the database phase complete.
- The new `FixtureIdentity(run, index)` has a unique `(run, index)`. It holds every
  index leased to the run: owners, catchers and extras.
- The new `FixturePendingImage(run, key)` has a unique `key`. It lists image keys whose
  rows are deleted but whose storage objects are not yet confirmed gone.

`FixtureObject` is unchanged. Cleanup deletes a run's `FixtureObject` rows and keeps the
`FixtureRun` row as durable evidence.

### Operations

The existing fixture remote (`simulation_fixtures/remote.py`) and relay
(`scripts/api_sim_fixture_ssh.py`) gain three operations. The target check runs first,
exactly as it does today. The read-only inspection relay is unchanged.

| Operation | Arguments | PASS data |
| --- | --- | --- |
| `provision` (changed) | adds `extras: list[int]` (0 to 10 indexes) | unchanged |
| `cleanup` | `pool`, `run_id` | `convention`, `enrollment`, `fursuit`, `activation`, `catch`, `session`, `credential`, `image`, `readmitted` (ints) |
| `retain` | `pool`, `run_id`, `reason` | `quarantined` (int) |
| `retained` | none | `runs`: at most 100 objects `{run_id, pool, reason, age_days}`; `retained` (int); `unfinished` (int) |
| `retained_counts` | none | `retained` (int); `unfinished` (int), with no listing and no limit |

### Attribution rule (G4)

A run's **identities** come from its `FixtureIdentity` rows. A run from before #223
has none, so its identities are the users of its ENROLLMENT ledger objects, mapped
through the `sp_<pool>_<index>` handle.

The **provisioned identities** are the owners and catchers. For older runs, all of the
derived identities count as provisioned.

`provision` already proves that every provisioned identity owned nothing before the run,
and each slot is exclusively leased or quarantined from then on. So everything a
provisioned identity owns afterwards belongs to this run. The **deletion set** is:

- every fursuit a provisioned identity owns, with its activations, catch sessions,
  credentials and catches
- every enrollment a provisioned identity holds
- every catch a provisioned identity made
- every catch, session, credential, activation and enrollment in the run Convention
- the run Convention itself
- each provisioned identity's `avatar_key`, which is cleared rather than deleted

Cleanup returns `FAIL_ATTRIBUTION` and changes nothing when any of these holds:

- the run's status is `cleaned` or `failed`, or the run belongs to a different pool
- a recorded slot holds a live lease for a different run
- a run identity has any enrollment, activation, catch made, or catch on its fursuits in
  a Convention other than the run Convention
- an extra identity owns a fursuit or enrollment, has made a catch, or has an avatar
- an image key in the set is also referenced outside the deletion set (by
  `Fursuit.photo_key` or `PlayerProfile.avatar_key`), or equals any
  `StagingResetIdentity.media_key`
- an object in the set is referenced by a row outside the set, because a PROTECT
  foreign key would block the delete
- an identity cannot be resolved (missing slot or handle)

An unknown run_id returns `FAIL_RUN_UNKNOWN`.

`provision` also dirty-checks the extras, which closes a gap #220 left open. A dirty
extra is quarantined with `FAIL_DIRTY`, as owners and catchers already are.

### Cleanup sequence (G5, G6, G7, G10, G11)

1. **Database phase.** This is one transaction, run only when `cleanup_counts` is null.
   - Lock the run row and its slots, then check attribution.
   - Delete in PROTECT order: catches → credentials → sessions → activations →
     enrollments → fursuits → Convention.
   - Clear avatars and delete the `FixtureObject` rows.
   - Insert every image key into `FixturePendingImage`, and set `cleanup_counts`.

   A failure rolls everything back and returns `FAIL_ERROR`.
2. **Image phase.** For each pending key, `default_storage.delete(key)`. A key is
   removed from the pending list only once `default_storage.exists(key)` is false. If
   any key remains, the call returns `FAIL_STORAGE`. Rerunning `cleanup` skips the
   database phase and resumes here.
3. **Verification phase.** Run the same dirty predicate `provision` uses on every run
   identity, and require that no row references the run Convention. A failed check
   returns `FAIL_VERIFY` and leaves the status unchanged.
4. **Completion phase.** This is one transaction.
   - Set the status to `cleaned` and set `cleaned_at`.
   - For each recorded slot, readmit it if it is quarantined, and clear any expired
     lease.

   A slot that holds a live lease for this run keeps it, because the in-run RELEASE stage
   clears it.

### Run lifecycle (G1, G2, G3, G8, G12)

`run_provisioned` (shared by `sim-journeys` and `sim-fixture-smoke`) changes as follows:

- **Before leasing.** Call `retained_counts`, which has no listing limit, so a
  backlog of unfinished runs cannot block a run:
  - When `retained` is 5 or more, print `FAIL setup result=FAIL_RETAINED_LIMIT` and
    lease nothing.
  - When either count is above zero, print `WARN retained=<n> unfinished=<m>`.
- **Provision.** `provision` passes `extras`, which are the leased indexes beyond owners
  and catchers.
- **Outcome.** Once provision has passed, the run's outcome is one of `pass`, `journeys`,
  `reconciliation` or `interrupted`:
  - The simulate-and-reconcile callback reports which part failed.
  - Any exception or interrupt counts as `interrupted`.
- **CLEANUP.** Runs only on `pass`. It prints `PASS cleanup <counts>` or
  `FAIL cleanup result=<code>`. A failure sets the outcome to `cleanup`.
- **RETAIN.** Runs for any outcome other than `pass`. It calls `retain` with that
  reason and prints `RETAIN reason=<r> quarantined=<n>`, or `FAIL retain` if the call
  fails. Retained state stays in place.
- **RELEASE.** Runs as today and ends the Clerk sessions. The pool release clears only
  leases the run still holds.

`retained` lists two kinds of run:

- runs whose status is `retained`
- `unfinished` runs: status `provisioned`, with no recorded slot holding a live lease
  for the run. These are crashed runs and runs from before #223.

The cap counts only `retained` runs.

**The report (G3).** The run's fixed stdout lines are its report, starting with
`RUN run_id=`, so maintainers capture them. The `FixtureRun` row is the durable database
evidence. #224 will own a report file.

### Maintainer commands

- **`make sim-cleanup POOL=<p> RUN_ID=<id>`** runs `cleanup`. It prints
  `PASS cleanup <counts> readmitted=<n>`, or `FAIL cleanup result=<code>`. It needs no
  Clerk secret and no API target.
- **`make sim-retained`** runs `retained` and prints one line per run,
  `RETAINED run_id=<id> pool=<p> reason=<r> age_days=<d>`, where `reason` for an
  unfinished run is `unfinished`. It then prints `PASS retained retained=<n>
  unfinished=<m>`.

### Limitations

- **Orphan images.** Some image objects cannot be attributed to a run:
  - objects a domain service failed to delete best-effort after replacing or removing
    an image (`media/service.py`)
  - images stored by a `provision` whose commit outcome was unknown (`FAIL_BOOTSTRAP`)

  These are documented and logged, never deleted.
- **Outsider slots from before #223.** Runs from before #223 recorded no outsider. Their
  outsider slots are readmitted manually with `sim-pool-readmit`.
- **A hard crash before RETAIN.** The run's slots keep their leases until the leases
  expire. The run appears as `unfinished`, and the next `provision`'s dirty check still
  quarantines any dirty identity.

### Reversibility

TWO-WAY DOOR. The migration is additive on the Staging-only simulation tables.

The cleanup deletes are irreversible for the rows they remove, but those rows are
synthetic Staging state that this run created, under a rule that refuses rather than
widens. The #204 baseline and its media key are excluded by construction and by an
explicit guard.

## Acceptance contract (frozen)

- **C-1 Ledger identities** (AC1, G13). `provision` takes `extras` (0 to 10 indexes).
  - Extras must be disjoint from owners and catchers, leased to the run, onboarded, and
    clean. A dirty extra fails with `FAIL_DIRTY` and is quarantined.
  - The committed run records every owner, catcher and extra index in `FixtureIdentity`.
  - The simulator passes every leased index it does not provision.
- **C-2 Migration** (AC1). One additive migration that adds the fields, tables and check
  constraints described under Ledger. Existing `provisioned` and `failed` rows remain
  valid.
- **C-3 In-run CLEANUP** (AC2, G1, G12). The stage runs in both `sim-journeys` and
  `sim-fixture-smoke`, only when SETUP, every journey and RECONCILIATION passed. It runs
  before RELEASE, while every slot is still leased, and goes through the fixture relay.
- **C-4 Attribution** (AC3, AC4). Cleanup deletes exactly the deletion set. When any
  refusal condition holds it returns `FAIL_ATTRIBUTION` and changes no row and no
  storage object. Tests cover each of these refusals:
  - a cleaned run
  - a slot holding a live lease for another run
  - state in a foreign Convention
  - a dirty extra
  - a shared image key
  - the #204 key
- **C-5 Deletion and evidence** (AC5). The database phase is one transaction in PROTECT
  order. Pool users and profiles survive, with avatars cleared. The `FixtureRun` row
  survives with its status, reason, `cleanup_counts` and `cleaned_at`.
- **C-6 Images** (AC6). The image set is ledger `media_key`s, the current `photo_key` of
  each run fursuit, and each run identity's `avatar_key`.
  - Every key is pending before any storage delete.
  - The status becomes `cleaned` only when the pending list is empty and every key fails
    `exists()`.
  - A storage failure returns `FAIL_STORAGE` with the key still pending.
- **C-7 Verification** (AC7). `cleaned` requires that every run identity passes the
  `provision` dirty predicate and that no row references the run Convention. Otherwise
  the call returns `FAIL_VERIFY`. The simulator prints `PASS cleanup` with counts only.
- **C-8 Retention** (AC8, G2, G3). Once provision has passed, any journey failure,
  reconciliation failure, cleanup failure, exception or interrupt triggers retention:
  - `retain` quarantines every recorded slot that holds a live lease for the run, and
    sets the status to `retained` with the matching reason.
  - RELEASE still ends the Clerk sessions.
  - A SETUP failure before provision behaves as it does today.
- **C-9 Partial failure** (AC9, G11). The database phase is all-or-nothing. The image
  phase can be resumed from `FixturePendingImage`. A rerun of `cleanup` after
  `FAIL_STORAGE` skips the database phase and completes once storage recovers.
- **C-10 Later cleanup and readmit** (AC10, G10). `sim-cleanup` applies C-4 to C-7 to a
  `retained` or `provisioned` run. Only on `cleaned` does it readmit quarantined slots
  and clear expired leases. It never readmits after a failed or unverified
  cleanup.
- **C-11 Clutter bound** (AC11, G8).
  - `retained` lists retained and unfinished runs, up to 100. A larger list returns
    `FAIL_LIMIT`.
  - The pre-run check uses `retained_counts`, which returns both counts with no limit.
  - Each `sim-journeys` and `sim-fixture-smoke` run prints the `WARN` line when either
    count is above zero.
  - The run refuses with `FAIL_RETAINED_LIMIT`, before leasing anything, once 5 or more
    runs are retained.
- **C-12 Older runs** (AC12, G9). A run from before #223 has no `FixtureIdentity` rows.
  Its identities come from its ENROLLMENT ledger objects, and it cleans under C-4 to C-7.
  An identity that cannot be resolved returns `FAIL_ATTRIBUTION`.
- **C-13 No contamination** (AC13). An API-level test runs two successive runs on one
  pool. In it:
  - Run A provisions, creates a catch, session and credential, and is cleaned.
  - Run B then provisions the same indexes without `FAIL_DIRTY`.
  - Run B's identities own nothing from run A.
- **C-14 Safety and output** (AC14).
  - The target check runs before any validation or database access.
  - Outputs carry only fixed codes, counts, and the run ids and pools of listed runs.
    They never carry media keys, object ids, handles or credentials.
  - The relay allows only known data keys, int counts, and exactly shaped `runs`
    entries; the simulator validates each operation's full shape.
  - Semgrep passes, and the simulator boundary rules still hold.
- **C-15 Documentation** (AC15). Updated:
  - the simulator README: commands, codes, reasons, cap, legacy cleanup, limitations
  - this spec and its implementation plan
  - the "until #223" notes in the #220, #221 and #222 specs
- **C-16 Staging proof** (AC16, run by the maintainer). It covers:
  - one passing `sim-journeys` run that ends in `PASS cleanup` and `PASS release`
  - a second run on the same pool that passes SETUP
  - `sim-cleanup` of at least one run from before #223 that readmits its slots
  - `sim-retained` before and after

  The sanitized lines are recorded here.

## Out of scope

- #204 reset and reseed, and the `rehearsal` app.
- The #224 report file.
- Reconciliation rules (#222) and journey behavior (#221).
- Production cleanup.
- Time-based automatic destruction of retained state.
- Recovering unattributable orphan images.
- Deleting pool users, profiles or Clerk identities.
- Changes to `sim-pool-smoke`.
