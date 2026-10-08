# Simulation target safety and runtime guardrails

Issue #227, parent #199. Acceptance Contract: `.refinement/227.md`, approved
G1–G8/AC1–AC25 and published at
https://github.com/TailTag-Game/tailtag/issues/227#issuecomment-6064479095.
The later instruction “implement via ADW” authorizes local implementation.
Live traffic, deployment, commits, pushing, and merging remain separate gates.

## Routing and scope guard

DEVELOPMENT, STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY, RELIABILITY.
Independent Explorer → Test Author → Implementer → Reviewer contexts. Parent
approves the design, test set, and deterministic evidence; whole-change review
is fresh. No initial Astra escalation; escalate if a named architecture or
security ambiguity survives independent review.

Outcome: every supported execution command uses the approved target, budget,
abort, finalization, and report policy. Non-goals: new backend health/gameplay/API,
data/schema changes, inspection expansion, automated resource ingestion,
unattended convention execution, host provisioning, and performance/SLO policy.
Change surface: simulator package/tests/README/Makefile, three existing host
relays and their tests. No remote change is necessary when optional run identity
is checked and stripped before the existing remote request is formed.
Proof: `make sim-check`, relay/backend gates applicable to changed scripts,
offline real-orchestration transcripts/reports, fresh unit/whole-change reviews,
doctor and diff checks, then separately authorized AC25 live proof.
Reversibility: local code/docs are TWO-WAY DOOR. No external action or persistent
data mutation is authorized by this implementation phase.

## Design

Use one run-owned safety runtime, rather than duplicating policy in every command
or adding controls only to convention v2. It reaches all TailTag HTTP through the
existing `ApiClient`; it never reaches Django or privileged collaborators from
SIMULATION. Context-local request metadata binds descendant client calls to the
current runtime/phase, while orchestration alone controls phase/probe/finalization
state. Standalone management retains existing behavior outside a run scope.

### U1: closed policy, shared runtime, target and HTTP boundary

Create `safety.py` for policy/accounting/state and `safety_targets.py` only if
needed to keep network verification separate from the pure runtime. Preserve
existing target resolution; Staging verification gains the #203
identity/readiness/identical-identity sequence; local smoke retains local identity
semantics. The runtime must not import `client`/`targets` at module load if that
creates a dependency cycle. Probe callback injection is a real network boundary.

Frozen policy field names (one resolved closed JSON mapping):
`requests=10000`, `seconds=900`, `in_flight=10`, `population=250`,
`final_requests=1000`, `final_seconds=600`, `poll_seconds=10`,
`error_window_seconds=10`, `error_min_samples=20`, `error_percent=50`,
`error_windows=2`. The request/time/concurrency/population/finalization maxima are
exactly AC13; polling is 5–30 seconds; probe deadline is fixed at 15 seconds.
Other error controls require finite positive values, integral counts/windows,
and percentage in (0,100]. Reject unknown keys, bool-as-number, nonfinite values,
duplicate JSON keys, and oversized policy input before external work.

Public handoff surface:

```python
resolve_safety_policy(value: Mapping[str, object]) -> dict[str, object]
class SafetyAborted(Exception): ...  # fixed reason; no external details
class SafetyRuntime:
    def __init__(self, policy: Mapping[str, object], *,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 observe: Callable[[Mapping[str, object]], None] | None = None): ...
    def scope(self): ...  # synchronous context manager, context-local binding
    def phase(self, name: str): ...  # context-local HTTP classification
    def control(self): ...  # reserved probe slot, genuine request counting
    def bind_probe(self, probe: Callable[[], Awaitable[dict[str, object]]], *,
                   local: bool = False): ...
    async def check_target(self) -> dict[str, object]: ...
    async def start_monitor(self) -> None: ...
    async def stop_monitor(self) -> None: ...
    async def run_phase(self, work: Awaitable[T]) -> T: ...
    async def request(self): ...  # async CM yielding one-shot synchronous start_send
    def observed_reply(self, status: int) -> None: ...
    def observed_transport_failure(self) -> None: ...
    def abort(self, reason: str) -> None: ...
    async def privileged_identity(self) -> dict[str, object]: ...
    async def begin_finalization(self) -> bool: ...
    async def run_closure(self, work: Awaitable[T]) -> T: ...
    def can_reconcile(self) -> bool: ...
    def snapshot(self) -> dict[str, object]: ...
    def validate_population(self, count: int) -> None: ...
    def record_finalization(self, operation: str, outcome: str) -> None: ...
    abort_reason: str | None
def active_runtime() -> SafetyRuntime | None: ...
```

Precise internal spelling may change only through a recorded parent amendment
communicated to dependent units. New test-only APIs are prohibited.

Count an actual send at the protected HTTP boundary; acquiring a permit/waiting
for pause does not consume a sent attempt. Guard the complete operation with the
remaining overall deadline, not just HTTPX per-chunk timeouts. Keep one reserved
control request slot outside the ordinary shared semaphore, but count and report
both. Observe genuine outcomes below injection/concealment. Only SIMULATION
workload outcomes enter catastrophic windows. Anchor non-overlapping windows to
the first SIMULATION phase entry; evaluate closed windows, including empty ones
that break a qualifying sequence. A final partial window alone never trips a
two-window default; elapsed polling/deadline checks still run with sparse traffic.
Parent amendment from independent review: admission observes permit evidence
before sending; the request context yields a one-shot synchronous `start_send`
called inside the guarded client send immediately before the HTTP operation.
Only that transition consumes a request. An abort between permit admission and
send therefore consumes no attempt.

`check_target` is a strict phase gate and pins the first approved tuple. Polls
pause new workload on a single availability failure and abort on a second;
malformed identity/redirect/mismatch abort immediately. Paused sends race abort
and deadline; control checks remain runnable. `run_phase` races phase work with
abort/deadline, cancels and awaits owned children, then raises `SafetyAborted`.
An ordinary external cancellation retains Ctrl-C/interruption semantics.
Monitor ownership is explicit and monitor exceptions cannot be lost.
Parent amendment during U4 integration: `run_closure` permits independently
verified non-TailTag Clerk closure after finalization starts, within the same
reserve and injected deadline. It does not relax any HTTP or privileged identity
guard. A later identity mismatch denies TailTag operations independently of the
first recorded abort reason.

Frozen phases use lowercase existing report vocabulary. Abort reasons are exactly
identity_mismatch, readiness, catastrophic_errors, request_ceiling,
duration_ceiling, population_ceiling, correctness, resource_saturation,
report_failure. Pure `ProbeUnavailable`/`ProbeInvalid` classify external probe
results; `TargetRejected` remains compatible with invalid probe rejection and
`TargetUnavailable` with both the historical target failure and availability.
Deadline races use injected monotonic/sleep, cancel and join operation/timer/abort
waiters. Local probe mode is explicit; callbacks are validated defensively.

The approved runtime snapshot has these closed sections (integer counters are
bounded/nonnegative, all times finite/nonnegative):
- policy: exact resolved mapping above.
- target: identity (null or exact tuple), evidence unverified/staging/local.
- preflight: checks, passed, failed, last (unverified/passed/unavailable/invalid/mismatch).
- probes: checks, passed, failed, consecutive_failures, paused, last (same enum).
- execution: requests, ordinary_active/peak, control_active/peak, elapsed_seconds,
  exhausted (null/requests/seconds/population).
- finalization: started, allowed, requests, ordinary_active/peak,
  control_active/peak, elapsed_seconds, exhausted (null/requests/seconds),
  reconciliation, retention, release, clerk_closure. Operation outcomes are
  not_attempted/passed/failed/skipped/uncertain; record_finalization sets them.
- errors: closed_windows, qualifying_windows, consecutive_windows,
  current_completed/catastrophic, last_completed/catastrophic.
- abort: null or exact reason/elapsed_seconds mapping.
- resources: monitoring=unavailable.
- concurrency: ordinary_limit, control_limit=1, combined_limit=ordinary_limit+1.

Active counts cannot exceed peaks or resolved limits. Evidence counters saturate
at `2**63-1`; request counters remain bounded by policy. Evidence counters and
current-window memory remain bounded; no unbounded event arrays. U3 consumes
this same shape; tests exercise it through real runtime and recorder boundaries.

### U2: privileged pinning

The three launcher channels consult `active_runtime()` before a privileged run
call. If present, await `privileged_identity()` and include optional
`expected_identity` at the caller-to-host envelope level. Without a runtime,
preserve the existing caller shape for standalone management.

Each host relay accepts either its exact historical caller shape or that shape
plus a strictly validated Staging expected tuple. It independently performs the
existing preflight/provider checks, compares expected tuple with the fresh tuple
before SSH, strips the expected field from the remote request, and sends the
existing independently verified `identity`. The remote still checks runtime
identity before DB access. Mismatch emits sanitized `FAIL_TARGET`, which the
channel maps to latched `identity_mismatch`; no SSH or later run operation occurs.
Do not normalize caller identity into authority or weaken `_active_instance`.

Files: three host relay scripts and tests; launcher-call portions of `pool.py`,
`fixtures.py`, `reconciliation.py`, and `population_reconciliation.py`.
After U2 completes, U4 may edit lifecycle portions of those same modules.

### U3: schema 4 and runtime evidence

Extend the existing report recorder and add a narrow `reports_v4.py` validator.
Keep historical schemas 1–3 validation intact. New `RunReport` construction emits
schema 4 using the unchanged resolved scenario descriptor/configuration and
appropriate legacy scenario result semantics. Add a closed `safety` envelope;
it owns resolved policy, pinned identity, preflight/probe counters, pause state,
execution/finalization request counts and peaks/durations, error-window counters,
first abort reason/time, finalization results, and resource monitoring marked
unavailable. Use bounded counts/last observations rather than an unbounded log.

The runtime's `snapshot` and the recorder's `record_safety` agree on one shape.
U1 and U3 must coordinate the exact frozen shape before tests assert it. Schema4
validation may project scenario result sections through unchanged legacy helpers;
do not accept arbitrary extras or turn abort into pass in that projection.
Safety policy is outside immutable scenario configuration. Traffic's historical
stop vocabulary stays unchanged; detailed abort cause belongs to safety evidence.

Add `RunReport.record_safety(snapshot: Mapping[str, object]) -> None` and optional
`safety_policy` construction argument. Runtime observation updates durable
snapshots, with persistence failure stopping further workload. Final safety stops
emit `outcome=aborted`/nonzero; Ctrl-C emits interrupted/130; preflight failure or
ordinary actor failure cannot pass. Historical reports keep their old semantics.
No raw exception/response/credential values reach reports or stdout.

### U4: lifecycle, CLI, correctness classification, operator documentation

Every run function owns or receives one runtime, including calls without a report.
Add optional `safety: SafetyRuntime | None = None` to execution entry points.
Convenience defaults still enforce the default policy. CLI passes the resolved
runtime, binds report observation, and installs/restores signal handlers in
`try/finally`. An injected clock/probe/network transport is allowed only at real
boundaries. Orchestration binds a credential-free probe for the resolved target.
Each phase uses strict target checks and `run_phase`; public-only inner behavior
never gains privileged channel handles. Stop monitor before bounded finalization.

CLI: every execution command gets `--safety-config PATH` (closed bounded JSON
policy); convention gets `--unattended` (reject before external work). `SIGUSR1`
on the run process requests fixed `resource_saturation`. Document how an operator
signals that specific process and reads Railway/Sentry evidence. This does not
introduce a control server, host provisioning, metric ingestion, or PID registry.
Forward corresponding `SAFETY_CONFIG`/`UNATTENDED` make arguments safely.

Normal reconciliation consumes execution budget. After an abort,
`begin_finalization` switches to ONE shared end-to-end time/HTTP reserve and
freshly gates recovery; it does not reset the reserve per operation. On identity
mismatch return false and send no further TailTag probe/API/privileged request.
Correctness/ceiling may reconcile partial in-memory expectations; readiness/error/
saturation skips reconciliation. Retention/release only proceed when permitted,
unchanged, and ready. Cleanup never makes an aborted run successful. Preserve
partial expected state on cancellation, mark possible commits uncertain, close
independently verified Clerk sessions within the reserve, and report skipped or
failed lease/retention operations. Renewal stops before or within finalization.
Already-started remote mutation cancellation cannot claim rollback.
Report-failure aborts skip reconciliation and use the same ready/pinned gate for
retention/release. Once aborted and in finalization, observer persistence is best
effort so a broken report sink cannot prevent bounded recovery; it never resumes
execution or permits a passing outcome.

Distinguish observable integrity/success-contract violations from transient
requests and unexpected ordinary rejection. Extend existing typed failure seams
as needed so generic catches do not label every 5xx as correctness. Keep existing
retry/ambiguity and expected-state invariants, v1/v2 semantics, and inspection cap.

Files: run/lifecycle portions of `smoke.py`, `pool.py`, `fixtures.py`, `journeys.py`,
`convention.py`, behavior/traffic/gameplay/reconciliation seams as needed,
`__main__.py`, Makefile, README. No speculative alternate live execution path.

## Test Surface Contract and failure/value map

Allowed substitutes: external HTTP transports, Clerk/provider/SSH launcher
boundaries, injected monotonic time/sleep, and existing fixture/inspection channels.
Exercise real policy/runtime, client, orchestration, report recorder/validator,
and internal gameplay/cancellation. Do not mock internal domain collaborators.

| Unit / realistic failure | Existing protection | Minimum distinct new proof |
| --- | --- | --- |
| U1: unsafe identity/readiness; request budget escape; saturated monitor; lost abort task; false error-window trigger | origin/redirect, v2 workload caps | Parameterized phase/poll and actual HTTP budget/window/cancel behavioral tests. |
| U2: relay silently follows a new deployment; optional identity permits malformed bypass | per-call relay/runtime checks | Parameterized three-relay matching/mismatch/malformed caller tests; real channel envelope preservation. |
| U3: abort report passes; unknown/sensitive safety fields admitted; old reports reinterpret | historical schemas/privacy/store failure | Real schema4 round trip plus bounded tampering partitions and historical fixtures; persistence-failure abort. |
| U4: legacy command bypass; identity-abort release writes; finalization resets budget; isolated transient aborts; operator signal lost | lifecycle/fault/traffic suites | Command/version parity, abort-class finalization matrix, controlled cancellation/partial-state, CLI operator/unattended proof. |

Parent approves this shape, then the independent Test Author proposes exact cases
and minimization before writing them. Every test must protect a distinct failure;
extend shared fake external fixtures to serve readiness where required rather
than duplicating internal stubs. Post-implementation tests require a newly found
failure mode/review finding. No product/backend time change or live chaos.

## Phase ledger

- Scope: U1–U4 above, AC1–AC24 local work; AC25 separately authorized live gate.
- Assurance: SECURITY, DATA INTEGRITY, RELIABILITY; local changes reversible.
- Completed: approved refinement, independent reconnaissance, focused branch,
  frozen design/test contracts, independent test authorship and implementation.
  All four units passed SPEC, QUALITY, TEST, SCOPE and applicable assurance review.
  Finding-specific fixes cover send admission/cancellation, terminal identity
  denial, strict report truth, immediate correctness classification and uncertain
  provisioning retention. No backend application or persistence schema changed.
- Evidence: backend canonical checks passed (3,948 tests); final simulator canonical
  checks passed (1,100 tests in 48.94 seconds) after all code/test edits.
  Three isolated assurance mutants were detected without mutating production.
  Real-orchestration offline normal/operator-stop reports are valid schema 4;
  tasks joined, Clerk sessions closed, leases released. These are controlled
  external-boundary evidence, not observed live Staging results.
- Reviewed: fresh whole-change Sol/xhigh review passed SPEC, QUALITY, TEST, SCOPE,
  SECURITY, DATA INTEGRITY and RELIABILITY. Three HIGH findings and one MEDIUM
  were resolved with independent before/after proof: deadline transfer, successful
  response classification, guarded quarantine-before-release and truthful pending
  diagnostics. Original smoke privacy/timeout protection was restored.
- Completed final gate: canonical simulator/backend checks, doctor, diff/scope
  audit, fresh whole-change review, AC1–24 evidence accounting and cleanup.
  No implementation edits or local validation remain.
- Current: local implementation ready on the focused branch, uncommitted.
  AC25 is the separately authorized live integration gate; issue closeout remains open.
- Resources: disposable task database removed, originally stopped OrbStack engine
  restored to stopped. No task-owned server/container/watch process remains.
- Pending: AC25 small Staging normal/operator-stop proof package is ready, but live
  execution requires its separately explicit authorization and approved clean
  source provenance. No commit, push, deployment, merge or live traffic performed.
