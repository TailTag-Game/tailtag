# V0 convention virtual-user behavior models — implementation design

Approved outcome and AC1–AC17: `.refinement/225.md`, published issue comment
https://github.com/TailTag-Game/tailtag/issues/225#issuecomment-6031713570.

## Phase ledger
DEVELOPMENT / STANDARD EXPANDED; SECURITY, DATA INTEGRITY, RELIABILITY,
TEST ADEQUACY. Parent: GPT-6 Sol family/high engineering judgment. Independent
explorer and design/test contracts complete. U1, U2 and U3 implementation,
deterministic gates and all independent review verdicts PASS. All four MEDIUM
review findings are resolved through independent behavioral tests and bounded
production corrections where needed. Final `make sim-check`: 788 tests PASS;
`make api-check`: 3,936 tests PASS; doctor and diff checks PASS.
The whole-change HIGH ownership finding has passed affected U1/U2 independent
review followups; the integrated simulator and five-family offline proofs pass.
Final whole-change verdicts all PASS, with no unresolved local findings.
Scope and resource audits are complete. Current: authorized PR publication.
The maintainer authorized commit, push and PR creation after local review.
Pending: separately approved Staging promotion and live proof.
No Astra trigger.
Two-way door: additive simulator/internal read-only tooling; no migration/gameplay
change. Revert code; preserve old report interpretation. Publication is authorized;
Staging promotion and live execution remain separate gates.

## Design choices
Use the approved A choices; no additional product decision is introduced. Reuse
existing API operation checks, fixture lifecycle, atomic recorder and inspection
query. Alternative rewriting the legacy journey/report pipeline increases
regression exposure. Alternative generic scheduler/load framework is #226 scope.

Three coherent units, implemented and reviewed in dependency order:
U1 operation/inspection/reconciliation boundaries; U2 behavior model/catalog;
U3 reporting/CLI/lease orchestration and integration. Normal role independence:
Test Author != Implementer != Reviewer. Test-author owns tests only; workers own
production files only. Each reviewer gets a frozen unit diff plus fresh evidence.

## Frozen Test Surface Contract
External substitutes permitted: httpx.MockTransport for real API/Clerk network,
lease/fixture/read-only inspection launcher protocols, clocks, subprocess/target
identity/provenance at real host boundaries. Exercise real simulator config,
operations, engine, comparison, report validator/filesystem, lifecycle and CLI.
No mocking internal collaborators for convenience, no test-only production APIs.
API inspection tests use real PostgreSQL transactions/domain setup. Existing
legacy journey/report/inspection tests prove compatibility without duplication.

### U1 interfaces and ownership
Create `tools/simulator/tailtag_simulator/gameplay.py`:
- `StepFailed` retains `.step`, `.expected`, `.observed` sanitized fields.
- `step(name, sending: Awaitable[Reply], status: int, code: str = '-', *,
  shape: Callable[[object], bool] = ...) -> object` preserves current `_step` behavior.
- `arm_session(owner: ApiClient, activation: str) -> str`,
  `stop_session(owner: ApiClient, activation: str) -> None` preserve existing flows.
- `HistoryEntry` frozen `(catch_id: int, fursuit: int, caught_at: str)`;
  `read_history(client: ApiClient, convention: int) -> tuple[HistoryEntry, ...]`.
  Use page_size=20, require stable nonnegative catch_count <=200, unique positive
  IDs/fursuits, bounded <=10 pages and exact final count; malformed/duplicate/loop/
  cross-origin or wrong-path/query next links fail. Build validated canonical paths
  rather than forwarding untrusted `next`. Do not fetch media URLs. No raw body in
  diagnostics. Preserve all legacy `_step` aliases/output expectations.

Add internal operation `inspect-population-v1` to existing inspection remote;
arguments stay `{pool, run_id, identities}`. Labels exactly `owner0`..`owner49` or
`attendee0`..`attendee199`, with 1..50 owners and 1..200 attendees, contiguous each
starting at 0; unique indexes; require every slot leased to run. Reuse `_read` in
one read-only transaction; existing `inspect` exact seven roles remains unchanged.
Returned data shape and 200 catch/extra-fursuit cap unchanged. Relay stays bounded
and Staging identity guards precede DB work. Public API untouched.

Create `population_reconciliation.py`:
- `PopulationExpectations` in-memory `.attempts: set[tuple[str,int]]`,
  `.made: dict[tuple[str,int], Made]`, `.seen: dict[tuple[str,int],list[Made]]`.
  Existing `reconciliation.Made(catch_id,caught_at)` may be reused.
  `.target_owners: dict[int,str]` maps actual in-memory target IDs to logical owner
  labels observed through authenticated public owned-fixture reads. The engine
  records every validated target and rejects conflicting ownership. This fact is
  never derived from privileged inspection or persisted in reports.
- `PopulationInspectionChannel` protocol `.inspect(pool, run_id,
  identities: Mapping[str,int]) -> Mapping[str,object]` (async).
- `PopulationInspectionLauncherChannel` sends inspect-population-v1; retain
  sanitized InspectionFailed boundary and bounded launcher protections.
- `PopulationDiscrepancy(check: str, actor: str|None, expected:int, observed:int)`;
  `PopulationReconciliationResult(discrepancies: tuple[...], count:int)` with
  `.passed` property. Fixed check labels: inspect, contamination, duplicate,
  missing, unexpected, catch_id, caught_at, provenance, window, history, count,
  fixture_photo, created_fursuit, avatar. No population media mutations: extra
  fursuits and avatars must be empty, fixture photos unchanged.
- `reconcile_population(expectations, clients: Mapping[str,ApiClient],
  indexes: Mapping[str,int], channel, *, pool, run_id, convention)
  -> PopulationReconciliationResult` (async). Same closed-world run scope;
  .made pairs required, attempted unobserved positives at-most-one; all others
  forbidden. Compare IDs/timestamps/retries/counts/privacy and every actor history. Require each
  persisted catch's owner to equal its target's expected logical owner, including
  ambiguous positives; unknown/conflicting/missing owner facts fail closed under
  the existing contamination check.
- `population_reconciliation_lines(result) -> list[str]` emits fixed codes/labels/
  counts only. Discrepancies deterministic by fixed check and actor order.

U1 owns gameplay.py, minimal journeys.py extraction, population_reconciliation.py,
inspection.py/inspection_remote.py and relay changes. Tests own separate files.

### U2 interfaces and ownership
Create `behavior_config.py` with `resolve_behavior_config(config:
Mapping[str,object]) -> dict[str,object]`: normalize defaults and reject unknown
keys, boolean-as-count, invalid types/ranges, unsupported families, unsafe targets,
missing/invalid pool and impossible family population before external work.
Exact keys:
`target` staging, `base_url` null, `pool`, `family` one of baseline/post-event/hotspot/
retry/soak; `casual`=1, `active`=1, `heavy`=1, `retry_prone`=1,
`normal_owners`=1, `popular_owners`=1, `fursuits`=4;
`casual_budget`=1, `active_budget`=3, `heavy_budget`=8, `retry_budget`=3;
`casual_repeats`=0, `active_repeats`=0, `heavy_repeats`=0, `retry_repeats`=2;
`casual_history`=0, `active_history`=3, `heavy_history`=1, `retry_history`=1;
`normal_weight`=1, `popular_weight`=4; `cycles`=1 (soak default3),
`activation_break`=false. Counts >=0; aggregate owners1..50/attendees1..200,
fursuits1..5; budgets1..200, repeats0..10, history0..200, weights1..100,
cycles1..100. Hotspot requires popular_owners>=1; retry requires retry_prone>=1.
Bounds are synthetic tool constraints, not product contracts. Max distinct catches
is sum(count * min(budget, target_count)) <=200; hotspot target_count=1, otherwise
all run fursuits. Cycles reuse same catch pairs; no growth beyond validated bounds.

Create `behavior.py`:
- `PopulationContext(owners: tuple[ApiClient,...], attendees:
  tuple[ApiClient,...])` contains no privileged clients/channels/callbacks.
- `PopulationRun` fields `.expectations: PopulationExpectations`, `.convention:int`,
  `.passed:bool`, `.summaries: dict[str,dict[str,int]]`, `.failure: str|None`,
  `.trace: tuple[tuple[str,str,str],...]` logical actor/action/target labels only.
- `simulate_population(context, config: Mapping[str,object], seed:int)
  -> PopulationRun` (async). Config resolved before invocation. Owners ordered
  normal then popular; attendees casual/active/heavy/retry; stable ordinals.
  Per-actor SHA256-derived random.Random seed; no run UUID/backend ID/hash() input.
  Validate public me/context/owned fixture state; reuse U1 step/arm/stop/history.
  All fursuits matched by owner logical ordinal and sorted fixture ID ordinal;
  IDs remain memory-only. Resolve target matches convention and target tailtag ID;
  first confirm201/created, revisits200/already_caught same ID/caught_at.
  Every confirm attempt recorded before sending, including transport ambiguity.
  Baseline interleaves actors' logical actions in round-robin; post-event makes
  all context preparation precede a grouped collection phase; hotspot fixed
  popular owner's first fursuit; retry uses configured duplicate confirms;
  soak repeats cycles (first selected target plan reused for later visits).
  History per cadence plus completion; read checks compare complete expected own
  collection, not just HTTP200. Exhausted budgets recorded, no busy loop.
  Stop sessions at cycle end; optional activation break only between cycles;
  exceptions fail closed with fixed failure codes and partial expectations/summary.
  Unexpected failures stop future modeled actions; no internal success fabrication.
  Expected statuses derive logical prior state; any unexpected code fails.
- Summaries exact persona keys casual/active/heavy/retry_prone/normal_owner/
  popular_owner; each exact counters actors, actions, completed, created,
  already_caught, expected_rejections, retries, history_reads, exhausted,
  unused_budget, cycles. Nonnegative bounded ints only.

Extend scenarios.py/catalog add immutable version1 descriptors with IDs
`convention-baseline`, `convention-post-event`, `convention-hotspot`,
`convention-retry`, `convention-soak`, consumes_randomness=true and closed config
from behavior_config. Existing descriptor bytes/meaning unchanged. New descriptor
operations closed logical action names, public-v0 API contract. Catalog/history
validation applies to new descriptors as well. No framework/dependency additions.
U2 owns behavior_config.py, behavior.py, scenarios.py, five JSON descriptors.

### U3 interfaces and ownership
New command `convention --pool NAME --family FAMILY [--config PATH]` plus existing
version/seed/report-dir flags and `make sim-convention POOL=... FAMILY=...
[CONFIG=... VERSION=... SEED=... REPORT_DIR=...]`. Config file strict bounded JSON
object, duplicate/unknown keys rejected; accepts behavioral parameters only,
not pool/target/base_url/family. Explicit CLI values build full closed config.
No arbitrary URL/secret field. Offline invalid config rejects before any network.

Extend RunReport to new scenarios schema2; preserve schema1 existing commands and
fixtures. Reuse atomic/persistence/provenance/attribution state-machine logic,
version-specific result validation separate from lifecycle infrastructure.
Schema2 has same top-level keys as v1; population contains persona counts and
fixture assumptions; profile adds explicit unavailable concurrency/arrival_timing/
network_injection/elapsed_time_soak (not_implemented). results exact keys
`behavior`, `checks`, `cleanup`; behavior `{items: <six summaries>, failure:
<fixed code or null>, reason: not_observed|null}`; checks `{items:[{check,actor,
expected,observed}],count,reason}`. Do not persist trace or raw runtime IDs. All
counts capped1e6, actor labels validated against configured counts; statuses/
cross-field totals consistent. Finished passed requires completed observed behavior,
all reconciliation checks pass, observed cleanup, correct attribution/provenance,
no failed/report phases. Validate both report versions offline; schema1 preserved.
`RunReport.record_behavior(summaries: Mapping[str,object], failure:str|None)` and
`.record_population_checks(result-compatible mapping)` as explicit safe adapters.

Create `convention.py` with `run_convention(pool, *, config, seed,
prompt_secret, lease_channel, fixture_channel, inspection_channel, emit,
clerk_transport=None, api_transport=None, clock=time.time, run_id=None,
report=None) -> int` async. Reuse run_provisioned, no duplicate lifecycle.
Orchestration wraps population work/reconciliation in a task and independently
renews leases every60s (30min TTL), including setup after leasing and before fixture
writes/read-only inspection. Heartbeat on orchestration channel only; validate
renewed count equals all allocated identities; failure cancels/awaits worker before
retain/release and produces nonzero. Start/stop renewal safely within run_provisioned
opt-in path, legacy calls unchanged. No detached task survives release. Config/cap
validation before setup; reporting exceptions cannot bypass finalization.

U3 owns reports.py, focused reports_v2.py if needed, convention.py, fixtures.py,
__main__.py, Makefile, README and CI only if changed-surface coverage requires it.
Provenance existing module glob covers new inputs; verify catalog/config data
included. No push, commit, promotion, Staging secrets or live traffic without
separately authorized final gate.

## Failure Mode Inventory / Test Value Map
1 variable-role inspection accepts foreign slot/writes: PostgreSQL inspect tests
   extend real fixtures, assert live lease/read-only transaction/200 cap/legacy.
2 untrusted paging leaks token/incomplete history: MockTransport real client tests
   validate bounded canonical next, duplicates/count mismatch/loop/outside origin.
3 retry/nonconvergent/unexpected catch silently succeeds: engine+real comparator
   through gameplay HTTP boundary and inspect fake; compare ID/time/state.
4 population overcap/bool/unknown config: table-driven resolver + CLI no network.
5 seed tied UUID/IO/global RNG: compare logical trace across IDs and repeated seed.
6 personas/families equivalent or infinite exhausted loop: one parameterized family
   end-to-end behavior test with action trace/counters plus exhaustion case.
7 report accepts sensitive/free-form/inconsistent fields or breaks v1: actual file
   round-trip strict v2 fixture, negative partitions, existing v1 suite unchanged.
8 heartbeat fail/cancellation/report failure bypasses release/cleanup: full local
   orchestration with external boundary fakes and controlled clock/wait only.
9 fixture/public privacy faults: population comparator fault matrix, no duplicate
   proof already covered by legacy test unless dynamic actor change matters.
Cheapest useful layers above; avoid redundant API business-rule re-testing. Parent
approves independent author's shape before tests, tests verified red before worker.

## Verification and resources
Baseline make sim-check and narrow real-PG inspection tests before mutation.
Each unit narrow tests + Ruff/Pyright; full make sim-check/api-check/Semgrep/doctor/
git diff --check after integrated change. Preserve fresh evidence; repeat only on
changed scope/failure. Reviewers diff-first, no redundant deterministic reruns.
API test environment `.refinement/225-test-env.sh` (synthetic local values).
Task-created container tailtag225-db, dynamic localhost port, no persistent data;
OrbStack was initially stopped and started for testing. Remove only task container;
restore OrbStack to stopped only if no unrelated resource was started meanwhile.
No blanket prune. Staging proof AC17 pending approved promotion after reviewable
local implementation. Do not claim issue complete before live proof.

## Finalized v2 and counter semantics (parent clarification before U2/U3 tests)
Schema2 population exact keys roles/identities/fixtures. Roles are the six summary
persona names with configured actor counts; fixtures exact owners/attendees/
fursuits_per_owner/fursuits (no outsiders). Profile exact operations/waits_seconds/
load_ramp/concurrency/arrival_timing/network_injection/elapsed_time_soak; all five
load/timing measurement objects are unavailable(not_implemented).
Behavior failure is null or FAIL_SIMULATION/FAIL_LEASE/FAIL_INTERRUPTED, never
arbitrary step/body/error text. Check result count is14 after complete comparison.
Counter completed is successful logical actor-target visits across cycles; created
counts first catches; already_caught includes revisits and duplicate confirmations;
retries counts explicit extra confirmations. Exhausted counts actors with unmet
original distinct-target budget once per run, unused_budget sums that unmet budget
once. Cycles counts completed actor-cycles per persona. Owner completed counts
successfully armed owned-fursuit session cycles; owner cycles counts owner-cycles;
owner created/already_caught/retries/history_reads are0. Completion history merges
coincident final cadence, avoiding duplicate final reads (defaults casual1/active1/
heavy8/retry3 per collection cycle). For successful default soak3: created15,
already_caught48, retries18, attendee completed3/9/24/9. Passed reports must agree
with configured population/finite cycles, observed successful behavior and checks,
including these relationships, not merely accept arbitrary nonnegative counts.
Heartbeat timer nondeterminism seam is fixtures.asyncio.sleep. Renewal must begin
after allocation while Clerk sessions/onboarding may still be blocked, not only
after open_identities returns. Failure before successful provision follows legacy
setup finalization (RELEASE; no RETAIN); once provision succeeded, retain on failure.
Worker cancellation must be awaited before subsequent finalization.

Descriptor freeze before U2/U3 tests: new descriptor roles are the six persona
summary keys in declared order. Macro operations: identity_preflight,
retention_preflight, lease, token_setup, provision, context, owner_cycle, family
macro, owner_stop, reconciliation, identity_final, cleanup, retain_on_failure,
release. Family macros: baseline=round_robin_collect, post-event=grouped_collect,
hotspot=hotspot_collect, retry=retry_collect, soak=repeated_collect_cycles.
Assumptions: synthetic_population, isolated_convention, run_owned_fursuits,
public_api_only, separate_owner_attendee, finite_cycles, family_<family with
hyphens replaced by underscores>. waits_seconds empty. Defaults are normalized
full configuration with pool null, family from ID, cycles3 only for soak.
Parameters map every config key to itself. Digest is SHA256 of canonical descriptor
without the digest field. Existing descriptor bytes remain unchanged.

Post-event collection is grouped by actor in stable actor order after every context
is prepared. Baseline target visits are round-robin, with duplicate confirmations
inside each visit. This logical distinction does not imply real arrival timing.

Retry-family macro uses a first-confirm phase followed by configured duplicate
confirmations; no configured repeats are overridden. Logical visit completion and
history cadence occur after its required confirmations. Other families keep extra
confirmations inside each visit. This distinguishes retry from baseline, which
already includes retry-prone attendees, without introducing delay or injection.

## Technical contract corrections during integration

The authentication `clock` defaults to `time.time`, as in existing fixture and
journey orchestration. It is forwarded into Clerk token-cache expiry checks,
which compare JWT Unix-epoch timestamps. Report durations continue using their
separate monotonic clock. This corrects the design's initial default and preserves
existing authentication behavior; it adds no product or workload scope.

The independent test author corrected an impossible fake ownership state during
population rebinding: old owners shared the same fursuit IDs with new owners.
Clearing fixture maps in place preserves shared state while representing the
API's unique fursuit ownership. Runtime acceptance assertions are unchanged.

Absent-persona invariant: when a configured persona has zero actors, every
counter in its summary must be zero for both complete and partial evidence.
This makes the existing population/counter consistency requirement explicit.

## Local validation evidence

Validated locally on `feat/convention-behavior-225`, based on `b64cca9`.
Local validation used no deployment, secret access or live Staging traffic.
Commit, push and PR creation were authorized after that validation.

| Contract coverage | Evidence | Status |
| --- | --- | --- |
| AC1–AC3, AC5–AC11: stateful personas, configurable families, canonical API operations, deterministic actor streams, finite exhaustion | Independent behavior/config/history tests; five-family offline orchestration | PASS locally |
| AC4, AC7, AC14: population assumptions and strict v2 evidence, explicit unavailable traffic profiles, legacy v1 interpretation | Literal v1/v2 fixtures, real recorder/filesystem/CLI, negative cross-field/privacy cases | PASS locally |
| AC12–AC13: expected/authoritative/public-history agreement, ambiguity handling, attribution, cleanup/retention/release | Real comparator and orchestration across external HTTP/launcher substitutes; real PostgreSQL inspection tests | PASS locally |
| AC15: bounded variable-role inspection, run lease isolation, read-only query and capacity | PostgreSQL inspection/relay tests, strict configuration and canonical paging | PASS locally |
| AC16: independent renewal during setup/work, count loss, interruption and repeated success | Controlled timers with blocked external HTTP; two positive renewals; no surviving tasks | PASS locally |
| AC17: offline behavioral and required repository checks | Complete simulator/backend validation and parent offline proof | PASS locally; live component pending |

`make sim-check`: **788 passed**, formatting/lint/strict typing/catalog history PASS,
Semgrep **0 findings across 23 modules**. `make api-check`: **3,936 passed**,
654 existing warnings, formatting/lint/typing/Semgrep/Django/schema/migration drift/
Gunicorn checks PASS. `./scripts/doctor.sh`: required checks PASS; warnings were the
uncommitted working tree and absent optional Dev Container CLI. `git diff --check`
PASS. No new dependencies or migrations.

Independent test additions protect new history paging and population comparison,
variable-role PostgreSQL inspection, configuration/persona/family behavior, schema-v2
validation, CLI/Make forwarding and reliable orchestration. Existing legacy tests
remain compatibility protection. Named review gaps led to focused tests for
same-count history disagreement, configured weights/repeats/cadence, token-cache
wall-clock behavior, two successful renewals and absent-persona evidence. Actual
bounded mutants were killed for count-only history, ignored configuration, the old
clock default, and once-only/always-failing renewal. Temporary copies were removed.

Parent offline orchestration produced valid schema-v2 reports for all five families:

| Family | Identities | Created | Already caught | Explicit retries | Checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 6 | 15 | 6 | 6 | 14 |
| post-event | 6 | 15 | 6 | 6 | 14 |
| hotspot | 6 | 4 | 2 | 2 | 14 |
| retry | 6 | 15 | 6 | 6 | 14 |
| soak (3 cycles) | 6 | 15 | 48 | 18 | 14 |

Each completed cleanup and release, closed sessions and left no asynchronous task.
The canonical Make/CLI validated every stored report after the final validator fix;
it also validated a legacy v1 report. Real CLI subprocesses rejected unknown and
oversized-capacity configuration with fixed diagnostics before report initialization.
These are **offline proofs with synthetic external provider/HTTP/launcher boundaries**;
source/target identity values are test fixtures, not live deployment evidence.
Ignored `.refinement/225-*` files retain detailed local logs and sanitized reports.

AC17 remains incomplete until the changed internal inspection tooling is promoted
through the approved Staging process and one small live run per family passes with
validated reports, authoritative reconciliation, cleanup and release. Those actions
require separate authorization. This implementation adds executable behavior
foundations; timing, concurrency, injection and elapsed-time load remain deferred.

## Whole-change ownership correction

The first whole-change review found that membership in the configured owner set
was insufficient: changing a catch's recorded owner to another participating owner
could pass reconciliation. AC12 requires agreement with expected state. The minimal
cross-unit contract extension is `PopulationExpectations.target_owners`, populated
only from public owner fixture reads and compared against every inspected catch,
including ambiguous confirmations. It adds no privileged behavior input, report
field, gameplay change, public API, migration, dependency or product decision.

Independent tests must show otherwise-valid two-owner evidence fails when only
owner association changes, and prove the engine supplies complete owner facts.
Affected U1/U2 workers and reviewers retain their ownership and independence.
Integrated simulator/whole-change proof repeats because correctness code changes;
backend evidence remains fresh because backend code/tests are unchanged.

Ownership correction followup evidence: four comparator regressions passed for
confirmed/ambiguous wrong-owner evidence and missing/invalid expected facts;
a separate engine case proves all eight fixture owner facts are captured with
one caught target and seven uncaught targets, including shifted backend IDs.
Affected U1/U2 independent review verdicts all PASS. Full `make sim-check` now
passes **788 tests**, with zero Semgrep findings. Parent five-family offline
orchestration and canonical CLI report validation were repeated successfully
against the ownership correction. Backend files stayed unchanged after their
3,936-test gate.

Resource audit complete: the task PostgreSQL container and its exclusive anonymous
test volume were removed. OrbStack is restored to its initial stopped state. No
unrelated container, persistent data, shared network or reusable image was removed;
all task check/mutation/CLI processes finished. Doctor passed before this restoration.

## Final local handoff

Fresh whole-change review passes SPEC, QUALITY, TEST, SCOPE, SECURITY, DATA
INTEGRITY, RELIABILITY and TEST ADEQUACY. The previous HIGH ownership finding is
resolved; no new BLOCKER, HIGH or MEDIUM finding remains. All 34 changed files
trace to the approved implementation, independent tests, catalog or documentation.
The simulator and internal inspection additions remain a TWO-WAY DOOR, with no
migration, new dependency or public gameplay change.

Local implementation is reviewable and validated; it is not full issue completion.
AC17's approved Staging promotion and five live proofs remain unperformed. The
maintainer has authorized publishing the focused change for review. After PR
approval, CI and merge, separately approved promotion must precede live validation.
Preserve this distinction when updating the issue or PR; do not auto-close the issue
before the live acceptance evidence exists.

Process reflection: unit review caught focused test gaps, while whole-change review
caught an expected-state handoff omission between public fixture reads and privileged
comparison. Exact owner association now lives in the domain fact map and behavioral
regressions, rather than another global prose rule. Fake state rebinding now preserves
unique ownership, and the clock boundary regression protects actual token refresh.
A broader shipping retrospective belongs after the remaining live acceptance phase;
no unrelated repository guidance or infrastructure was added for these one-off lessons.
