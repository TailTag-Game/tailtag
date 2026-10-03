# Simulation reconciliation implementation plan

Spec: [simulation reconciliation](2026-10-03-simulation-reconciliation.md) (#222,
acceptance contract R-1 to R-15). This plan sequences the work and fixes the
interfaces. The spec stays authoritative for behavior.

## Phase ledger

- **Scope:** STANDARD EXPANDED, in two review units that are built in order:
  - U1 is the API-side read-only inspection: the remote module, the relay, and Make.
  - U2 is the simulator side: expectations, comparison, output, and wiring.

  U2 depends on U1's wire shape, which this plan freezes.
- **Assurance:** SECURITY and DATA INTEGRITY.
- **Reversibility:** TWO-WAY DOOR (see the spec).
- **Completed (2026-10-03):**
  - refinement (G1 to G13, with the cap corrected to 200), reconnaissance, and spec
    and plan approval
  - independent tests and implementation for U1 and U2
  - one review per unit, with no BLOCKER or HIGH findings:
    - U1 fixed L1 (duplicate indexes return `FAIL_REQUEST`), L3 (the run lookup
      matches the pool) and N3 (ASCII-only `caught_at`).
    - U2 fixed M-1 (`FAIL_BOOTSTRAP` is passed through) and N-1 (README).
      L-1 was accepted and recorded in the spec.
  - the whole-change review, with no BLOCKER, HIGH or MEDIUM findings
- **Pending:** the PR (once the maintainer asks) and the maintainer Staging proof
  (R-14).
- **Deferred:**
  - Promote the four private `simulation_fixtures.services` names that
    `inspection.py` imports (U1 L2).
  - Extract a shared core for the three near-copy SSH relays.

## Change surface

| File | Unit | Change |
| --- | --- | --- |
| `services/api/simulation_fixtures/inspection.py` (new) | U1 | `inspect(pool, run_id, identities) -> InspectionOutcome`, run in a read-only transaction |
| `services/api/simulation_fixtures/inspection_remote.py` (new) | U1 | `execute(request, *, runtime_identity, environ)`. It accepts only `inspect`. The target check is shared with `remote.py`, and the shape follows `remote.py`. |
| `services/api/simulation_fixtures/remote.py` | U1 | Only if needed: expose `_target_matches` so the new remote reuses it instead of copying it. No behavior change. |
| `scripts/api_sim_inspect_ssh.py` (new) | U1 | The relay. It reuses the `api_staging_reset_ssh` helpers the same way `api_sim_fixture_ssh.py` does. Its bootstrap imports `inspection_remote`, it keeps the default SSH timeout, and it validates output against the exact schema. |
| `Makefile` | U1 | The `api-sim-inspect-ssh` target |
| `services/api/tests/test_simulation_fixtures_inspection.py` (new) | U1 | Service and remote tests on PostgreSQL |
| `services/api/tests/test_api_sim_inspect_ssh.py` (new) | U1 | Relay output and request validation, following `test_api_sim_fixture_ssh.py` |
| `tools/simulator/tailtag_simulator/reconciliation.py` (new) | U2 | `Role`, `Check`, `Expectations`, `InspectionChannel`, `InspectionLauncherChannel`, `Discrepancy`, `ReconciliationResult`, `reconcile_run(...)`, `reconciliation_lines(...)` |
| `tools/simulator/tailtag_simulator/journeys.py` | U2 | `_Run` records `Expectations`, and the positive journeys record `created` and `confirmed`. Every confirm records an `attempt`. `simulate_journeys` returns the expectations alongside the results. `run_journeys` takes an `inspection_channel`, runs RECONCILIATION, and derives the exit code. |
| `tools/simulator/tailtag_simulator/fixtures.py` | U2 | `run_provisioned`'s `simulate_and_reconcile` callback also receives the leased `indexes`. `fixture-smoke` ignores them, and its output is unchanged. |
| `tools/simulator/tailtag_simulator/__main__.py` | U2 | `INSPECTION_LAUNCHER_COMMAND` and `_inspection_launcher()`, wired into `journeys` |
| `tools/simulator/tests/reconciliation_support.py` (new) | U2 | `FakeInspectionChannel`, built from `journey_support`'s gameplay fake state |
| `tools/simulator/tests/test_reconciliation.py` (new) | U2 | Comparison and output tests |
| `tools/simulator/tests/test_journeys.py` | U2 | The happy run now asserts the reconciliation line, and the exit-code cases are extended |
| `tools/simulator/README.md` | U2 | A "Reconciliation" section: what is checked, the output lines, and the prerequisites |
| `docs/specs/2026-10-03-simulation-reconciliation*.md` | — | Status updates |

Nothing changes under `services/api/` outside `simulation_fixtures/` and its tests.
There is no migration, and no public view or serializer change.

## Interfaces

```python
# services/api/simulation_fixtures/inspection.py
ROLES: Final = ("owner0", "owner1", "catcher0", "catcher1", "catcher2", "catcher3", "outsider")
MAX_RECORDS: Final = 200

@dataclass(frozen=True)
class InspectionOutcome:
    result: str                      # "PASS" | "FAIL_LEASE" | "FAIL_RUN_UNKNOWN" | "FAIL_LIMIT"
    data: dict[str, object]          # the spec's PASS shape; {} on failure

def inspect(pool: str, run_id: str, identities: Mapping[str, int]) -> InspectionOutcome:
    """Returns FAIL_REQUEST itself for a malformed argument, including duplicate indexes."""
```

```python
# tools/simulator/tailtag_simulator/reconciliation.py
class Role(StrEnum): OWNER0 = "owner0"; ...; OUTSIDER = "outsider"   # lease order
class Check(StrEnum): INSPECT = "inspect"; CONTAMINATION = "contamination"; ...  # spec order, 14 members

@dataclass
class Expectations:
    def begin(self, journey: str) -> None: ...
    def attempt(self, role: Role, fursuit: int) -> None: ...
    def created(self, role: Role, fursuit: int, catch_id: int, caught_at: str) -> None: ...
    def confirmed(self, role: Role, fursuit: int, catch_id: int, caught_at: str) -> None: ...

class InspectionChannel(Protocol):
    async def inspect(self, pool: str, run_id: str,
                      identities: Mapping[Role, int]) -> Mapping[str, object]: ...
        # raises InspectionFailed(result) on a non-PASS result or a launcher fault

@dataclass(frozen=True)
class Discrepancy:
    check: Check
    journey: str | None
    role: Role | None
    expected: int
    observed: int

@dataclass(frozen=True)
class ReconciliationResult:
    discrepancies: tuple[Discrepancy, ...]
    @property
    def passed(self) -> bool: ...

async def reconcile_run(expectations: Expectations, clients: Mapping[Role, ApiClient],
                        indexes: Mapping[Role, int], channel: InspectionChannel,
                        *, pool: str, run_id: str, convention: int,
                        created_fursuit: int | None) -> ReconciliationResult: ...
def reconciliation_lines(result: ReconciliationResult) -> list[str]: ...
```

How a failure of `inspect` itself is represented is still open. One option is a
`ReconciliationResult` with a single `Check.INSPECT` discrepancy plus the result
code, carried as `inspect_result: str | None`. The implementer chooses the smallest
representation that produces the spec's `result=` line.

`run_journeys` gains a keyword-only `inspection_channel: InspectionChannel`. It calls
`reconcile_run` inside its existing `simulate_and_reconcile` callback, after the
journey lines and before `run_provisioned` releases. When SIMULATION never reached
the convention read, it has no convention or fursuit IDs. In that case
reconciliation reads the Convention through catcher0's `GET
/api/conventions/active/`, and fails closed if that read fails. See the spec's
Comparison conventions.

## Test Surface Contract

- **Seams.** All are existing seams except the inspection channel fake:
  - the httpx transports
  - the lease and fixture channel fakes
  - `emit`, `prompt_secret`, and `clock`
  - the new `FakeInspectionChannel`, which builds its `PASS` data from the
    `journey_support` gameplay fake's catch, fursuit, and avatar state, so that the
    simulator fake and the API fake cannot drift apart
- **Fault injection.** `FakeInspectionChannel` takes an optional `corrupt` callable.
  It edits the data before returning, for example adding a foreign catch, flipping
  `provenance`, or shifting `caught_at`. A test can also raise `InspectionFailed`.
- **API side.** Real PostgreSQL through the existing pytest setup. Data is built with
  `simulation_fixtures_test_support` plus the real domain services. The relay tests
  replace only `railway` subprocess execution, as `test_api_sim_fixture_ssh.py`
  already does.
- **No mocks of simulator or service internals.**

## Failure mode inventory → tests

| # | Failure mode | Test (minimum) | Unit |
| --- | --- | --- | --- |
| FM1 | `inspect` can write, or a later edit adds a write | One test: within `inspect`, the captured queries start with `SET TRANSACTION READ ONLY`. One test: an ORM write inside the same read-only helper raises `InternalError`. | U1 |
| FM2 | The scope misses a leak direction | One parametrized test that seeds one foreign catch per scope arm: a run catcher in another Convention, a non-run catcher in the run Convention, and a non-run catcher of a run fursuit elsewhere. Each appears with the right `null` or `false` flag. | U1 |
| FM3 | The lease guard is wrong | Parametrized: an index leased to another run, an expired lease, an unknown run, and a failed run. Each returns its code with empty data. | U1 |
| FM4 | The size cap is wrong | 201 catches → `FAIL_LIMIT`. At 200 records, the serialized relay output is ≤ 65536 bytes. | U1 |
| FM5 | The flags are computed wrongly | One happy test covers `provenance`, `in_window`, `caught_at` format equal to the history serializer, `fixture_photos_unchanged`, `fursuits`, and `avatars`. Then one parametrized break per flag: a session from another activation, `caught_at` before the run, a changed photo key, a set avatar. | U1 |
| FM6 | The wrong channel or target is reached | Remote: an identity mismatch → `FAIL_TARGET` with no queries run. `operation="provision"` → `FAIL_REQUEST`. The bootstrap source names `inspection_remote` and does not name `simulation_fixtures.remote`. | U1 |
| FM7 | The relay passes extra or unsafe output | Parametrized relay validation: extra keys, a wrong type, a non-ISO `caught_at`, a `null` where an int is required, an unknown result. Each → `FAIL_LAUNCHER`. | U1 |
| FM8 | A comparison check misses its condition | One parametrized test, one case per `Check`, through `corrupt` or a broken journey fake rule. Each produces exactly its expected `check=… journey=… role=…` line and exit 1. The other checks stay silent. | U2 |
| FM9 | A false alarm on a correct run | The happy run gives 13 journey `PASS` lines, `PASS reconciliation checks=14`, `PASS release`, and exit 0, in this exact line sequence. | U2 |
| FM10 | A partial failure gives a wrong verdict | Three cases: `catch` breaks after the confirm reached the fake (the row exists, so the pair is at-most-one and there is no `missing`, but journey `FAIL` gives exit 1); `stale_credential` creates a catch (`unexpected journey=stale_credential role=catcher1`); and SETUP fails, so there is no reconciliation line and release still runs. | U2 |
| FM11 | Output leaks | A sentinel scan over the output of FM8, FM9, and FM10. The sentinels are the fake's ids, indexes, handles, `caught_at` values, media keys, and URLs. | U2 |
| FM12 | `inspect` failure handling | `InspectionFailed("FAIL_LEASE")` → `FAIL reconciliation result=FAIL_LEASE`, then release, then exit 1. An unknown result code → `result=FAIL_LAUNCHER`. | U2 |
| FM13 | The boundary regresses | Extend the existing FM4 test from #221: there are no inspection channel calls during SIMULATION, and exactly one `inspect` call happens after the journeys and before release, with the seven role→index pairs. | U2 |
| FM14 | The callback widening breaks `fixture-smoke` | The existing `test_fixture_smoke.py` stays unchanged and passing. | U2 |

Deliberately no extra tests for:

- each field's JSON type on the simulator side, beyond FM7's relay validation
- discrepancy sorting, beyond FM8's single-line cases plus one multi-discrepancy
  ordering assertion inside FM10
- Semgrep rules, which are unchanged

## Sequence

1. **Maintainer approval** of the spec and this plan.
2. **U1 tests.** `test-author` (Sonnet, high) writes the U1 API tests against the
   interfaces above. They fail because the code is missing. The parent then approves
   the test set.
3. **U1 implementation.** `implementer` (Sonnet, high) writes the U1 code until the
   new tests and `make api-check` pass. It must not edit tests without parent
   approval.
4. **U1 review.** `reviewer` (Opus, high) reviews U1 and gives SPEC, QUALITY, TEST,
   SCOPE, SECURITY, and DATA INTEGRITY verdicts.
5. **U2 tests.** `test-author` writes `reconciliation_support.py`,
   `test_reconciliation.py`, and the `test_journeys.py` extensions. The parent then
   approves the test set.
6. **U2 implementation.** `implementer` writes the U2 code until `make sim-check`
   passes.
7. **U2 review.** A `reviewer` reviews U2 with the same verdicts.
8. **Deterministic gate** on the final HEAD:
   - `make api-check` and `make sim-check`
   - `./scripts/doctor.sh` and `git diff --check`
   - `ruff --no-cache` on new modules
   - Semgrep with the new files added to git, since untracked files are skipped
9. **Whole-change review.** One fresh `reviewer` (Opus, high) reviews the whole
   change.
10. **PR.** Push as `FinnThePanther`, but only once the maintainer asks.
11. **Maintainer Staging proof.** After merge and promotion, provision a fresh pool
    with at least 7 identities, then run `make sim-journeys POOL=<pool>`. Record the
    sanitized output in the spec (R-14).
