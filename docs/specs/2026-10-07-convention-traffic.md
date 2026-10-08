# Convention traffic, client failures, and concurrency — implementation contract

Approved outcome: issue #226, AC1–AC23, and
https://github.com/TailTag-Game/tailtag/issues/226#issuecomment-6052703150.
The maintainer approved G1–G10 and requested implementation through ADW.

## Phase ledger and scope guard

DEVELOPMENT / STANDARD EXPANDED. SECURITY, DATA INTEGRITY, RELIABILITY, TEST
ADEQUACY. Parent uses Sol-family engineering judgment; fresh explorer, independent
test authors, implementers, unit reviewers, and whole-change reviewer.
No Astra trigger: no new service, persistence, authorization architecture, or
distributed consistency design. Existing architecture and all product behavior
choices were approved during refinement. No additional clarification is required.

Outcome: bounded stateful concurrent traffic and real-client effects, strict
expectations, historical compatibility, sanitized reproducible evidence.
Non-goals: backend changes/migrations, capacity increases, infrastructure chaos,
new dependencies, generic frameworks, #227 catastrophic policy, #228 host,
#229 percentile/baseline work. Files: simulator code/tests/docs/Makefile and specs.
Proof: unit behavioral red/green evidence, `make sim-check`, doctor, diff checks,
unit/whole review, offline real-orchestration family reports. Authorized small
Staging proof is a later completion gate; no promotion/live traffic authorized.
Reversibility TWO-WAY DOOR: additive versioned simulator behavior and reports;
existing scenario versions retain execution and validation. No external writes
except those explicitly authorized later.

Completed: approved refinement, independent reconnaissance, clean focused branch
`feat/convention-traffic-226`, baseline 789 simulator tests PASS.
Independent authors completed approved minimal sets and value maps. U1 module
absence produced collection red; U2 comparator produced four real behavioral
failures (forbidden/unresolved false passes), engine absence produced collection
red; U3 produced 44 failures/5 passes for missing version/schema/interfaces.
Authored tests' scoped formatting/lint and diff checks PASS.
All three units have final focused green evidence (U1 104, U2 181, U3 233).
The repository-wide gate identified stricter project-context import/type checks;
mechanical corrections preserve assertions and behavior. Initial unit reviews
identified late generation admission, active actor completion-order dependence,
numeric overflow rejection, and impossible per-bucket completion evidence.
All unit reviews now PASS after independent red/green regressions and minimum
fixes; multi-target expiration establishes every planned catch before waiting.
Fixed-default legacy metadata rejects unsupported v2 control overrides. Five
families passed standalone offline orchestration, strict schema3 readback,
authoritative/public comparison, cleanup, release and joined-worker checks.
Whole-change review identified and resolved overdue-work replay within budget
and seedless preparation-failure digests through independent regressions/minimum
fixes. All final unit and whole-change verdicts PASS. Parent `make sim-check`
PASS: 970 tests, formatting/lint, strict types, catalog, Semgrep zero findings;
doctor required checks and diff checks PASS. Final standalone five-family proof
PASS with actual skips distinguished from intended offers. Local AC1–22 and
local AC23 proof complete; live Staging proof remains separately authorized.
Publication authorized on 2026-10-07: commit, push and open a normal PR.
Current: implementation ready for PR review. Pending: controlled promotion
and separately authorized Staging gate; actual 12-hour proof remains #230.
Environment: host uv/Python checks usable; initially stopped OrbStack engine was
started by task, Docker29.4.0 reachable, no containers running, doctor required
checks PASS. Resource audit found no containers; engine restored to its prior
Stopped state. No task-created worker, service or disposable infrastructure remains.

## Architecture and alternatives

Retain the accepted asyncio/httpx architecture. Add a small bounded scheduler and
runtime accounting module; reuse ApiClient for every real request and existing
fixture orchestration for renew/reconcile/retain/cleanup/release. Version 2 adds
concurrent execution, while version 1 continues its sequential workload. Share
public gameplay parsing/discovery where useful; do not maintain duplicate live
implementations of the same validation/business flow. Engine-specific scheduling
is intentionally versioned compatibility, not duplicate gameplay authority.

A global transport injector would affect target/auth/setup/inspection traffic and
is rejected. Operation-level effects wrap already protected ApiClient calls.
A load framework replacement is outside the accepted ADR and introduces needless
dependency/report duplication. Internal backend calls remain forbidden.

## U1: closed configuration, schedule, and runtime limits

Own `traffic_config.py`, `traffic.py`, and their focused tests. Do not modify
scenarios/reports/CLI or gameplay. Export:

```python
resolve_traffic_config(config: Mapping[str, object]) -> dict[str, object]
@dataclass(frozen=True)
class Clock:
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    wall_time: Callable[[], float] = time.time
@dataclass(frozen=True)
class Entry:
    actor: int
    ordinal: int
    at_seconds: float
class TrafficStopped(Exception): ...
class TrafficRuntime:
    def __init__(self, config: Mapping[str, object], *, clock: Clock = Clock()): ...
    async def request(self, send: Callable[[], Awaitable[Reply]]) -> Reply: ...
    def bind_seed(self, seed: int) -> None: ...
    def record(self, counter: str, amount: int = 1) -> None: ...
    def stop(self, reason: str) -> None: ...
    def snapshot(self) -> dict[str, object]: ...
async def run_schedule(
    config: Mapping[str, object], seed: int,
    run_entry: Callable[[Entry], Awaitable[bool]], *,
    runtime: TrafficRuntime, clock: Clock = Clock(),
) -> dict[str, object]: ...
```

Configuration reuses the existing flat behavior shape plus exactly four
nested objects: `traffic`, `failure`, `retry`, `limits`. Persona counts, target
budgets, repeats and target weights remain controls. Version 2 uses elapsed
traffic for re-entry and a completion history check per entry; fixed `cycles`,
`activation_break`, and `*_history` fields remain compatibility metadata only.
Reject nondefault supplied values for those fields before external work: cycles
1 (soak 3), activation_break false, and casual/active/heavy/retry history 0/3/1/1.
This closes a reviewed attribution gap without inventing concurrent owner-break
or cadence behavior; version 1 retains its executable controls unchanged.
Strip the nested objects before calling
the unchanged v1 behavior resolver; retain fixture/distinct-catch bounds. Strict
unknown/duplicate-key/type/nonfinite/range rejection precedes external work.
Closed config keys/defaults are below; supplied nested values merge defaults.

`traffic`: `mode` (`arrivals` or `active`), `segments` (1–100 objects each exactly
`duration_seconds`, `start`, `end`), `bursts` (0–100 objects each exactly
`at_seconds`, `count`), `think_seconds`, `jitter_seconds`, `max_entries`,
`bucket_seconds`. Durations positive, rates/targets/delays finite nonnegative;
active segment targets integral and no greater than population/active cap. Burst
times inside profile and counts bounded. `max_entries` default 10000, max 10000;
bucket count max 1000 (reject incompatible bucket/duration configuration).
Positive ordinary profiles default to arrivals over 2 seconds at attendees/2;
post-event uses zero-rate segments plus one attendee-sized burst at 0.25s;
hotspot likewise at 0.1s; soak defaults active for 30s at min(attendees,10).
Default think delay 0.05s (soak 1s), jitter 0, bucket width 1s.
All defaults are synthetic assumptions. Supplied segments replace recipe defaults.

`failure`: `operations` (unique subset `read`, `resolve`, `confirm`),
`pre_send_delay_seconds`=0, `pre_send_failure_rate`=0,
`response_delay_seconds`=0, `lost_response_rate`=0, `timeout_rate`=0,
`duplicate_overlap`=(hotspot only), `domain_case`=`none` (or `stale`, `stopped`,
`expired`), `recover_existing`=false, `confirmation_delay_seconds`=0.
Default operations all three; retry recipe defaults pre-send/loss rates 0.1.
Rates each 0–1; mutually exclusive loss/timeout selections sum at most 1.
Delays bounded by configured generation ceiling. Expiration requires explicit
long duration/limits sufficient for the 12-hour wait; never enabled by default.

`retry`: `attempts`=3 (1–10), `base_seconds`=0.25, `cap_seconds`=2,
`jitter_seconds`=0 (all finite nonnegative; base≤cap).
`limits`: `attempts`=5000 (1–1000000), `active`=10 (1–250),
`in_flight`=10 (1–250), `generation_seconds`=300 (positive ≤86400),
`drain_seconds`=15 (positive ≤300). Profile duration must fit generation bound;
natural expiration needs an explicitly long profile. Count modeled attempts,
including never-sent effect attempts, without double-counting real sends.

Arrivals integrate piecewise linear journey-start rates and include bounded
seeded jitter/bursts. Intended actor assignment and offered offsets derive from
seed/stable logical ordinals, never global randomness or HTTP completion order.
No backlog: unavailable/busy actors or full active cap skip/count offered work.
Active mode uses bounded periodic admission opportunities (100ms) to maintain
configured targets with actual shortfalls recorded. It does not queue work or
overlap ordinary entries of an identity. Duration/finite-entry bounds prevent
busy/infinite loops. Completion/cap accounting is separate from correctness.
Delayed scheduling coalesces overdue logical groups: count/skip older missed
arrival groups or active ticks rather than replay them as a catch-up burst. The
most recent due group may be admitted while the profile is live; all overdue
work is skipped once the profile has ended. Intentional simultaneous burst
entries remain one group. Normal timer wake jitter must not discard every offer.

Runtime request admission enforces request/in-flight caps and finite request
termination; HTTPX's per-I/O inactivity timeout alone is not a total request
deadline. Use the existing 10-second timeout also as a total real-call deadline,
bounded by the overall generation plus drain remaining. Preserve existing
protected client behavior. The absolute simulation budget starts with counted
public preparation; profile offsets and recorded generation elapsed time start
when scheduling begins. Preparation consumes budget rather than resetting it.
Operators should leave room for preparation when configuring a profile near its
generation ceiling. A late wake checks the absolute generation deadline before
admission; a normal terminal boundary is allowed to drain. All tasks are tracked,
cancelled/joined on stop or drain expiry. Clock injection is a real nondeterminism
boundary, not a production mock transport. Stop reasons are a fixed allowlist.
An isolated total-call timeout raises detail-free `httpx.TimeoutException` after
awaited cancellation, so U2 can retry it. Exhausted whole-run budget raises
TrafficStopped. U2 owns a narrow `client.TransportFailed(RequestFailed)` subclass
for genuine HTTPX transport failures; base RequestFailed still means fatal
origin/redirect/size protection. Existing v1 handlers continue catching the base.

`snapshot()` returns exactly: `plan_digest` (64 hex), `offered`, `admitted`,
`skipped`, `completed`, `active_peak`, `in_flight_peak`, `attempts`, `sent`,
`injected`, `transient`, `retries`, `expected_rejections`, `exhausted`,
`unresolved`, `generation_seconds`, `drain_seconds`, `lag_seconds`, `stop_reason`,
`buckets`. Counts nonnegative ≤1e6. Times finite nonnegative. `buckets` ≤1000
objects exactly `at_seconds`, `offered`, `admitted`, `skipped`, `completed`.
Counters `record()` admits only injected/transient/retries/expected_rejections/
exhausted/unresolved/sent. An unresolved decrement is allowed on observable
recovery, provided the final count stays nonnegative. U2 records sent immediately
before actual ApiClient call. Stop reasons are exactly null/attempts/generation/
drain/external/correctness/entries.
`plan_digest` describes intended plan/configuration/seed and never fixture IDs.
`bind_seed` computes that canonical config/seed digest before the first counted
public preparation request; both the gameplay adapter and scheduler bind the
provided seed. Initialization uses seed0 until a runner binds its actual seed.
Partial preparation-failure/cancellation reports must retain the actual seed's
digest, with identical digest for identical inputs and different distinct seeds.

## U2: public-client gameplay, effects, and exact expectations

Own `traffic_behavior.py`, `traffic_effects.py`, the narrow `client.py` error
taxonomy extension, necessary shared preparation
extraction in `behavior.py`/`gameplay.py`, `population_reconciliation.py`, and
focused tests/support. Preserve v1 behavior and public API contract. Export:

```python
async def simulate_traffic_population(
    context: PopulationContext, config: Mapping[str, object], seed: int, *,
    clock: Clock = Clock(), runtime: TrafficRuntime | None = None,
) -> TrafficPopulationRun: ...
@dataclass(frozen=True)
class TrafficPopulationRun:
    population: PopulationRun
    traffic: dict[str, object]
class TrafficCancelled(asyncio.CancelledError):
    population: PopulationRun
```

Use U1 resolved configuration and runtime. Discover fixtures through public reads;
map to stable logical actor/target positions. Reuse existing context/fixture
validation and response parsing. Prepare owner activation/sessions through public
actions, then admit stateful actor journeys. Each actor retains its own seed
stream, target plan, canonical catches, and retries. Normal entries cannot
overlap; explicit same-actor duplicate confirmations are bounded and joined.
Counts retain v1 persona summary names, but v2 has observed totals rather than
v1's fixed formulas. Context/bootstrap/lifecycle requests are protected but
finite/countable; effects only apply to selected ordinary gameplay operations.

Effects happen around real HTTP calls; never create Reply/httpx.Response objects
to simulate success/rejection. Pre-send failure counts an attempt but never sends.
Concealment/delivery delay discards or delays the bounded real reply; no concealed
body informs actor success. Transport-only failures remain distinct from protected
origin/redirect/size violations. Extend detail-free client errors narrowly if
needed without changing v1 public behavior. Retry reads/resolve/confirm only;
real HTTP 502/503/504 and transient transports use the approved bounded policy.
Expected domain rejection is explicit 404/catch_target_unavailable and valid
shape; unexpected/malformed results fail correctness and stop modeled work.

For `domain_case`, execute controlled target-local owner transitions between
resolution and confirmation, preserving opaque payload in memory. Stale uses
public rotate; stopped uses public stop; expired retains public `expires_at` and
waits naturally without session refresh. Serialize domain experiment transitions
per target where necessary rather than letting simulator-owned races fabricate
expected outcomes. `recover_existing=true` first establishes a canonical catch,
then makes target state stale, and confirms unchanged historical recovery;
otherwise reject new creation. Domain cases are composable experiments, not
changes to ordinary API semantics or fixture setup privilege.

Extend `PopulationExpectations` additively with
`pairs: dict[tuple[str, int], Literal["required", "forbidden", "unresolved"]]`
(default empty) as explicit pair expectations;
empty mapping retains legacy v1 interpretation. Use exactly `required`,
`forbidden`, `unresolved`. Required has canonical `made` data; forbidden permits
no new catch; unresolved allows at most one during diagnosis but never passes.
Permit `unresolved` to become required after observable recovery, never using
concealed response facts. Convergent duplicates preserve ID/time. Preserve all
existing authoritative/public history/privacy/provenance checks and fixed
diagnostic allowlist; use existing unexpected/missing/inspect check labels.
Negative attempts never gain write permission through generic attempts set.

All ordinary actors finish before final reconciliation; retries exhausted on one
actor mark run failed but do not automatically cancel other actors. Correctness
errors and limits stop new work. Stop/await all tasks before returning partial
observations on failure. External cancellation propagates as TrafficCancelled
after cleanup; it carries partial PopulationRun for sanitized report adapters only
and no observations in its message/args. U3 records partial summaries/runtime and
re-raises; operator/lease cancellation does not resume reconciliation or turn into
success. No lease/admin channel is passed into simulation. Runtime/effect evidence contains
only closed counters/labels, no raw IDs, bodies, payloads, or tokens.

## U3: immutable catalog, schema 3, CLI and lifecycle integration

Own `scenarios.py`, five new `scenarios/convention-*-v2.json`, `reports_v3.py`,
targeted `reports.py` extensions, `convention.py`, `__main__.py`, README/Makefile,
and integration/report/catalog tests. Consume U1 resolver/U2 runner.

Scenario IDs remain convention-baseline/post-event/hotspot/retry/soak; explicit
version 2 uses U1 closed config, immutable descriptor/digest and public-v0 API
contract. Do not change/remove old descriptor bytes or default v1 CLI meaning.
CLI `--scenario-version 2` selects new resolution/runner/schema; config file
remains bounded duplicate-key-rejecting JSON, never arbitrary target/pool/secret.

Schema 3 reuses existing top-level lifecycle/source/identity/atomic persistence.
`profile` records resolved `traffic`, `failure`, `retry` plus declared operations;
`limits` records enforced configured ceilings alongside existing target/client
limits, using existing `{value,reason,unit,scope}` objects. Replace request_ceiling
(attempts/simulation), duration_ceiling (seconds/generation), concurrency_ceiling
(requests/simulation); add active_ceiling (actors/simulation) and drain_ceiling
(seconds/drain); reason is null with configured value. Historical limits unchanged.
`results` contains existing behavior/checks/cleanup and `traffic`
`{value: snapshot|null, reason: null|not_observed}`. Successful correctness can be
separate from workload completion, but passed run requires both and full
attribution/persistence/cleanup/release. Strict schema-3 validator verifies exact
keys/types/ranges, accounting totals, bucket totals, peaks≤limits, no unresolved
submissions/stop on success, and persona/check labels. Do not reuse v1 fixed
summary equations for new concurrency/effect semantics or weaken old validators.
Percentiles/throughput/SLO gates remain unavailable, owned by #229.

Add `RunReport.record_traffic(snapshot: Mapping[str, object])` and a read-only
`scenario_version` property if necessary; report candidate validation remains
independent of disk and failures cannot skip finalization. Record partial traffic
on failure/interruption where it exists; reuse lease failure classification.
`run_convention` gains `scenario_version:int=1`, `traffic_clock:Clock=Clock()`;
v1 path unchanged, v2 uses resolver/U2 runner and same reconciler/lifecycle.
Use real reports plus external HTTP/launcher/time substitutes for integration.

## Frozen test surface and failure/value map

Allowed substitutes: HTTPX external API/Clerk transports, privileged launcher
channels, monotonic/wall/sleep boundaries, filesystem failures. Prohibited:
mocking internal domain helpers/runner/comparator, fake production responses,
test-only production APIs, backend imports/database bypass. Tests exercise real
config/runtime/client/engine/reconciliation/reporting, at the cheapest useful
level. Preserve existing v1 protection; do not duplicate the 789 baseline cases.

| Unit | Real failure | Existing protection | Minimum new protection |
|---|---|---|---|
| U1 | invalid bounds or seeded plan depends on network order | v1 finite config only | table-driven invalid/valid profiles and seeded plan/admission behavior |
| U1 | queued bursts, overlapping identity work, ceiling leakage | no real scheduler | controlled-clock blocked entries prove skip/caps/drain/no surviving tasks |
| U2 | concealed committed catch counted as success or retry duplicates | v1 ambiguity + convergence | real fake HTTP boundary with lost first reply and canonical recovery |
| U2 | forbidden negative creates a catch yet passes | generic attempts allows rows | comparator required/forbidden/unresolved table extending existing tests |
| U2 | injections affect auth/owner controls or manufacture responses | protected client and Semgrep | request recording + public lifecycle/negative matrix |
| U2 | natural expiry overwritten/stopped instead | existing lifetime contract | fake wall/sleep external boundary, public expires_at and no refresh actions |
| U3 | schema/version reinterprets historical reports | schema1/2/catalog baseline | v2 descriptor immutability + real schema3 recorder/validator tamper table |
| U3 | report/cancel/lease failure skips retention/release | v1 lifecycle tests | real v2 orchestration success/failure/cancellation report proof |

Parent approves this minimum test shape. Independent authors may propose fewer
cases with equal unique protection; additional cases require a named failure
mode. Observe legitimate red before production implementation; focused green,
format/lint/type/Semgrep, then fresh unit review. Assurance adds negative
target/injection/privacy cases and plausible-mutant checks for forbidden writes,
concealed commits, admission backlog, and compatibility routing.
