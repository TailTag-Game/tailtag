# Convention traffic implementation plan

Goal: deliver approved issue #226 AC1–AC23 locally through ADW, then present a
concrete Staging proof gate. Contract: `2026-10-07-convention-traffic.md`.
Architecture: asyncio scheduling around existing public-client gameplay and
fixture lifecycle; v2 scenarios/schema3 reports preserve v1 interpretation.
Stack: existing locked Python3.13/httpx/uv/Ruff/Pyright/pytest/Semgrep. No new deps.

## Global constraints

Keep SIMULATION public-only and synthetic fixtures isolated. No backend API/time/
schema changes. Retain ≤200 distinct catches, 50 owners/200 attendees/five
fursuits per owner. Explicit version2; do not mutate historical descriptors.
Commit/push/normal PR publication authorized on 2026-10-07. Promotion and live
Staging traffic still require separate authorization.
Fresh Test Author ≠ Implementer ≠ Reviewer. Approved interfaces and test surfaces
are in the adjacent design contract, which is the authoritative worker handoff.

## U1 — Configurable bounded admission and runtime

Files/interfaces: design U1. Consumes unchanged `resolve_behavior_config` and
protected `Reply`; produces `resolve_traffic_config`, Clock, Entry,
TrafficRuntime, TrafficStopped, run_schedule.

- [x] Independent author tests profile bounds, seed equivalence, arrivals/active
  targets, skipped burst work, identity exclusion, request/in-flight limits and
  cancellation/drain. Example observable: block actor0, offer it again, assert
  skipped=1 and maximum concurrent entries of actor0=1.
- [x] Run `uv run --project tools/simulator --locked pytest -q
  tools/simulator/tests/test_traffic_config.py tools/simulator/tests/test_traffic.py`;
  record legitimate red to `.refinement/226-u1-red.log`.
- [x] Independent implementer builds minimum contract; no catalog/engine/report
  edits. Use parent-approved bounded test set.
- [x] Run focused green, format/lint/type/Semgrep; independent diff-first review
  with SPEC/QUALITY/TEST/SCOPE/assurance verdicts. Resolve correctness findings.

## U2 — Real effects, concurrent gameplay, and typed expectations

Files/interfaces: design U2; depends on U1 frozen config/runtime, produces
`simulate_traffic_population`, TrafficPopulationRun and additive pair expectations.

- [x] Independent author extends behavioral/comparator tests with real HTTP
  substitutes and clock boundaries. Example: first confirm commits but reply is
  concealed; second uses same payload, observes already_caught, one canonical row
  matches authoritative/public histories. A forbidden attempted pair with a row
  must fail even though `attempts` contains it.
- [x] Record legitimate red for focused tests to `.refinement/226-u2-red.log`.
- [x] Independent implementer reuses protected client and shared gameplay
  discovery/parsing; implements exact fault/negative/expiration semantics and
  preserves all v1 tests. No lifecycle/catalog/report file ownership.
- [x] Focused green, deterministic gates, plausible forbidden/ambiguity mutants,
  fresh U2 review. Resolve any contract/security/correctness findings.

## U3 — Versioned catalog/reports and lifecycle wiring

Files/interfaces: design U3; consumes U1/U2. Produces explicit scenario2/schema3
CLI path and durable intended/observed evidence in existing run lifecycle.

- [x] Independent author protects five descriptors, old reports, strict schema3
  tampering/privacy/accounting, and real v2 orchestration success/failed retention/
  cancellation. Example: report success with unresolved>0 must be rejected;
  v1 report fixture continues validating without interpretation changes.
- [x] Record legitimate red to `.refinement/226-u3-red.log`.
- [x] Independent implementer adds catalog/schema/CLI/report adapters and
  operator docs, using frozen signatures. Finalization cannot depend on report
  persistence success; no surviving traffic/renewal tasks.
- [x] Focused green and `make sim-check`, independent U3 review.

## Integrated verification and handoff

- [x] Generate one real-orchestration offline report per family plus short fault
  scenarios using only approved external substitutes; validate schema3 and
  authoritative/public comparator results. Store sanitized transcript/report IDs.
- [x] Whole-change diff-first independent review at Sol/xhigh; review named
  integration risks and material code/test sprawl, without redundant check runs.
- [x] Run final required checks when code has changed: `make sim-check`, doctor,
  `git diff --check`. `make api-check` only if backend tooling changes. Diagnose
  Docker availability without touching unrelated services/resources.
- [x] Audit all changes against AC1–AC23, update phase ledger, preserve explicit
  unverified live gate; clean task-owned resources and produce concrete proof
  instructions for user authorization. Natural 12-hour proof remains #230.

Validation and review outcomes will be recorded in `.refinement/226-*` and the
design ledger. This plan does not authorize an external action.

Local gates completed: 970 tests/static/Semgrep PASS; doctor required checks PASS;
all unit and whole-change verdicts PASS; five-family offline proof PASS. Live
Staging authorization/execution remains AC23's separate gate. No external action
was performed during the local implementation phase. OrbStack engine restored
to prior Stopped state.
