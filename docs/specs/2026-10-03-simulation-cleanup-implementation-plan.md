# Simulation cleanup implementation plan

Spec: [simulation cleanup](2026-10-03-simulation-cleanup.md) (#223, acceptance contract
C-1 to C-16). This plan sequences the work and fixes the interfaces. The spec stays
authoritative for behavior.

## Phase ledger

- **Scope:** STANDARD EXPANDED, in two review units built in order:
  - **U1, the API side:** migration, ledger identities, the cleanup, retain and retained
    services, the remote operations, and relay output validation.
  - **U2, the simulator side:** the retained-cap check, extras, the CLEANUP and RETAIN
    stages, `sim-cleanup` and `sim-retained`, the Make targets, and docs.

  U2 depends on U1's wire shape, which this plan freezes.
- **Assurance:** DATA INTEGRITY, SECURITY and MIGRATION.
- **Reversibility:** TWO-WAY DOOR (see the spec).
- **Completed (2026-10-03):**
  - refinement, spec and plan
  - independent tests and implementation for U1 and U2
  - one review per unit, with no BLOCKER or HIGH findings:
    - U1 fixed M1 (a test for the refusal that rolls back started deletes), L1
      (`FAIL_ERROR` outside the database phase), and a docstring NIT.
    - U2 fixed MEDIUM-1 (RELEASE now runs even if RETAIN is interrupted; the new test
      was mutant-checked), LOW-2 (a test for an interrupt during CLEANUP), and LOW-1
      (README retain-reason wording).
  - the whole-change review, with no BLOCKER, HIGH or MEDIUM findings. Its three LOW
    and NIT documentation corrections were applied.
- **Merged** as `b20355c` (#292).
- **Maintainer Staging proof (C-16):** passed 2026-10-04 (deployment `5dd8353e`,
  runs `8ca8c7f5` and `1db7405c`, pool `r1`), and is recorded in the spec. All three
  runs from before #223 are cleaned.
- **Pending:** none for #223.
- **Deferred:**
  - Reuse `simulation_pool.services` quarantine and readmit in `cleanup.py` (U1 L2).
  - Add a test for an unresolvable legacy handle (U1 L3).
  - Add simulator-side malformed-reply leak tests (U2 LOW-3).
  - `sim-retained` still returns `FAIL_LIMIT` above 100 listed runs. Runs are no longer
    blocked, because the pre-run check uses `retained_counts` (CodeRabbit on #292).
  - Extract a shared core for the near-copy SSH relays (carried over from #222).

## Change surface

| File | Unit | Change |
| --- | --- | --- |
| `services/api/simulation_fixtures/models.py` | U1 | `FixtureRun` statuses, `reason`, `cleaned_at` and `cleanup_counts`; `FixtureIdentity`; `FixturePendingImage` |
| `services/api/simulation_fixtures/migrations/0002_*.py` (new) | U1 | Additive migration with check constraints |
| `services/api/simulation_fixtures/services.py` | U1 | `provision(..., extras)`: validate, bind, dirty-check, record identities. Extract the dirty predicate so cleanup can reuse it. |
| `services/api/simulation_fixtures/cleanup.py` (new) | U1 | `cleanup(pool, run_id)`, `retain(pool, run_id, reason)`, `retained(now=None)` |
| `services/api/simulation_fixtures/remote.py` | U1 | Register `cleanup`, `retain` and `retained`; `provision` takes `extras` |
| `scripts/api_sim_fixture_ssh.py` | U1 | Accept the new result codes and validate the exact new data shapes |
| `services/api/tests/…` | U1 | Service, remote and relay tests (see the test surface below) |
| `tools/simulator/tailtag_simulator/fixtures.py` | U2 | Cap check and WARN line, `extras`, outcome tracking, CLEANUP and RETAIN stages |
| `tools/simulator/tailtag_simulator/journeys.py` | U2 | The callback reports `journeys`, `reconciliation` or `pass` |
| `tools/simulator/tailtag_simulator/cleanup.py` (new) or `fixtures.py` | U2 | `run_cleanup` and `run_retained` command bodies |
| `tools/simulator/tailtag_simulator/__main__.py` | U2 | `cleanup --pool --run-id` and `retained` subcommands |
| `Makefile` | U2 | `sim-cleanup` and `sim-retained` targets |
| `tools/simulator/tests/…` | U2 | Run-lifecycle tests against fakes |
| `tools/simulator/README.md`; the #220, #221 and #222 specs | U2 | Documentation (C-15) |

## Frozen wire shapes

All requests are `{"operation", "arguments"}`. All responses are `{"result", "data"}`.

- **`provision` arguments:** `{pool, run_id, owners, catchers, fursuits_per_owner,
  extras}`. `extras` is a list of 0 to 10 ints, disjoint from owners and catchers.
- **`cleanup` arguments:** `{pool, run_id}`.
  - **PASS data:** `{convention, enrollment, fursuit, activation, catch, session,
    credential, image, readmitted}`, all non-negative ints.
  - **Failures:** `FAIL_REQUEST`, `FAIL_RUN_UNKNOWN`, `FAIL_ATTRIBUTION`, `FAIL_STORAGE`,
    `FAIL_VERIFY` and `FAIL_ERROR`, each with empty data.
- **`retain` arguments:** `{pool, run_id, reason}`, where `reason` is one of
  `journeys`, `reconciliation`, `cleanup` or `interrupted`.
  - **PASS data:** `{quarantined}`.
  - **Failures:** `FAIL_REQUEST`, `FAIL_RUN_UNKNOWN`, and `FAIL_ATTRIBUTION` when the
    status is not `provisioned` or `retained`. A retain on a run that is already
    `retained` is PASS and keeps its first reason.
- **`retained` arguments:** `{}`.
  - **PASS data:** `{runs, retained, unfinished}`. `runs` is sorted with retained runs
    first, then oldest first. Each entry is `{run_id, pool, reason, age_days}`, and
    `reason` is a retained reason or `unfinished`.
  - **Failures:** `FAIL_LIMIT` when there are more than 100 runs.

- **`retained_counts` arguments:** `{}`. **PASS data:** `{retained, unfinished}`,
  with no limit. The pre-run cap check uses it instead of `retained`. Added after
  CodeRabbit review on #292.

The relay keeps the existing result set and adds `FAIL_ATTRIBUTION`, `FAIL_STORAGE`,
`FAIL_VERIFY` and `FAIL_LIMIT`. It validates the data shape per key. Each entry in `runs`
must have exactly those four keys: a UUID string, a pool matching `[a-z0-9]{1,12}`, a
reason from the enum, and an int of 0 or more.

## Test surface

Use real PostgreSQL (`make api-test`) and Django's in-memory or file storage for the
API, as the existing fixture tests do. Use the existing fakes for the simulator. Mock
storage only to inject a delete or `exists` failure.

**U1 failure modes to protect against**, in one parameterized refusal table where
practical:

- **Deletion and evidence.** After a provisioned run with a catch, a session, a rotated
  credential and an extra fursuit, cleanup deletes the whole set. Users and profiles
  survive and the ledger row is `cleaned`. This proves C-4, C-5 and C-7.
- **Refusals change nothing.** Each refusal in C-4 leaves the row and storage counts
  unchanged.
- **Storage failure and resume.** An injected storage failure returns `FAIL_STORAGE`
  with keys still pending. A rerun completes (C-6, C-9).
- **Run from before #223.** A run with no `FixtureIdentity` rows cleans through
  enrollment-derived identities (C-12).
- **No contamination.** A second provision on the same indexes passes after cleanup
  (C-13).
- **Retain.** `retain` quarantines the live slots and is idempotent. `retained` lists
  and counts retained and unfinished runs, and returns `FAIL_LIMIT` (C-8, C-11).
- **Extras in provision.** Extras are recorded, and a dirty extra returns `FAIL_DIRTY`
  (C-1).
- **Remote and relay.** The target check runs first, unknown keys and shapes are
  rejected, and new outputs are validated (C-14).

**U2 failure modes to protect against:**

- **Passing run.** It runs CLEANUP before RELEASE, and RETAIN is never called.
- **Failing run.** A journey, reconciliation or cleanup failure, or an interrupt, each
  call `retain` with the matching reason and still release.
- **Cap reached.** The run leases nothing and prints `FAIL_RETAINED_LIMIT`.
- **WARN line.** Printed when either count is above zero.
- **Extras.** Passed to `provision`.
- **`sim-cleanup` and `sim-retained`.** Exact output lines.

## Verification

Run the narrowest tests while working. Before review:

- `make api-check`
- `make sim-check`
- `./scripts/doctor.sh`
- `git diff --check`

Run Semgrep after `git add -N` for new files.
