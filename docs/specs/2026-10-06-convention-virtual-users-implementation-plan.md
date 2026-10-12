# V0 convention virtual-user behavior implementation plan

> For agentic workers: execute with ADW's independent Test Author → Implementer →
> Reviewer contexts. User selected ADW execution; no additional execution-choice
> checkpoint is needed. Approved contracts take precedence over generic workflows.

**Goal:** Execute and reconcile bounded stateful convention populations through
TailTag's public API with deterministic configuration and sanitized schema-v2 reports.

**Architecture:** Extend the existing simulator at three cohesive boundaries,
preserving legacy journeys/reports. Public behavior has no privileged inputs;
orchestration owns leases, fixture setup, inspection, and finalization.

**Tech stack:** Python 3.13, asyncio, httpx, uv, pytest, strict Pyright, Ruff,
Semgrep; Django/PostgreSQL only for the existing internal read-only inspection.

## Global constraints

Approved AC1–AC17 and exact module interfaces are in
`2026-10-06-convention-virtual-users.md`; all tasks consume that complete contract.
No public gameplay/schema/migration changes; no new dependencies, real load,
network failure injection, scheduler, Production traffic, Development load tests,
owner collecting, or new immutable product population assumptions. Existing
four execution commands remain schema v1; new convention commands use schema v2.
Preserve 200 authoritative catch cap, fixture limits and public-only SIMULATION.
Do not commit/push/promote until authorized. All workers preserve unrelated edits.
No test-only production APIs or mocks of internal domain behavior.

## Unit 1: Public operations and authoritative population correctness

Files: gameplay.py, minimal journeys.py extraction, population_reconciliation.py;
inspection.py/inspection_remote.py, scripts/api_sim_inspect_ssh.py if necessary;
independently authored gameplay/population reconciliation/inspection tests.
Consumes ApiClient/Reply, existing lease/read-only run query, Made facts.
Produces StepFailed/step/arm_session/stop_session/read_history and population
expectations/channel/comparator interfaces frozen in the design.

- [x] Independent author submits minimum test set/value map; parent approves.
- [x] Author writes behavioral tests and saves red evidence; use real PostgreSQL
  for transaction/lease checks and MockTransport only for the HTTP boundary.
  Representative paging protection:
  ```python
  rows = await read_history(client, convention)
  assert [(row.catch_id, row.fursuit) for row in rows] == expected_pairs
  assert all(request.url.host == validated_host for request in observed_requests)
  ```
  Population inspection proof calls `inspection.inspect_population` with bounded
  actor labels and verifies PASS for its own lease, FAIL_LEASE for another run,
  and unchanged acceptance of the legacy exact seven-role inspection.
- [x] Verify intended red failures using `uv --directory tools/simulator run
  --locked --no-sync pytest -q` on owned files; backend command sources
  `.refinement/225-test-env.sh` and runs targeted inspection tests.
- [x] Fresh implementer implements only this unit's production surface. Move the
  existing canonical operation checks; do not rewrite thirteen journey cases.
  Implement bounded canonical paging, exact data parsing, read-only variable-role
  inspection, expected-state comparison and sanitized deterministic diagnostics.
- [x] Run narrow new and existing journey/reconciliation/inspection tests, Ruff
  and strict Pyright for touched packages. Fix findings, not adjacent cleanup.
- [x] Parent captures unit diff and evidence. Fresh reviewer reports SPEC, QUALITY,
  TEST, SCOPE, SECURITY, DATA INTEGRITY and RELIABILITY verdicts. Resolve required
  findings before dependent production work.

## Unit 2: Behavior configuration, families and execution

Files: behavior_config.py, behavior.py, scenarios.py and five additive descriptors;
independent config/behavior/catalog tests and boundary support.
Consumes Unit 1 operations/expectations; produces normalized config, PopulationContext,
PopulationRun, simulate_population, new convention-* scenario resolution.

- [x] Independent author proposes minimum set against frozen interfaces; parent
  approves, author records red before implementation.
  Example observable config contract:
  ```python
  config = resolve_behavior_config({"pool": "p1", "family": "baseline"})
  assert config["heavy_budget"] == 8
  assert config["retry_repeats"] == 2
  ```
  Engine tests use public HTTP requests and assert logical trace/persona counts,
  same-seed equivalence across backend ID changes, exact retry ID/time convergence,
  finite exhaustion and each family's distinct workload.
- [x] Fresh implementer builds finite logical behavior against real shared operations;
  keep per-actor RNG and stable actor/target ordinals independent of run/backend ID.
  Strictly reject unsupported config and capacity before any external operation.
- [x] Add immutable scenario descriptors; preserve old descriptor bytes/digests and
  historical interpretation. Defaults and unavailable load features are explicit.
- [x] Run narrow tests plus legacy catalog/report tests for integration impact,
  package Ruff/Pyright/catalog checks and Semgrep for new modules.
- [x] Capture diff/evidence; fresh unit reviewer returns separate applicable verdicts.
  Resolve contract violations and high/blocker findings before Unit 3.


## Unit 3: Schema v2, CLI and reliable lifecycle

Files: reports.py and focused v2 validation module as needed, convention.py,
fixtures.py opt-in renewal, __main__.py, Makefile, README, narrowly required CI;
independent v2 fixture/validation, convention CLI/lifecycle tests.
Consumes Unit 1 correctness result and Unit 2 config/engine/catalog; produces
run_convention and convention CLI/Make invocation, strict v2 durable evidence.

- [x] Author freezes literal v2 report fixture/field semantics, red round-trip,
  unknown/sensitive/inconsistent negative partitions and complete lifecycle proof.
  Existing v1 literal fixtures/tests remain unchanged.
  Example external result protection:
  ```python
  report = load_report(path)
  assert report["schema_version"] == 2
  assert report["outcome"] == "passed"
  assert report["correctness"] == "passed"
  ```
- [x] Implementer extends version-specific schema validation around the existing
  durable atomic recorder. Keep provenance/attribution/finalization semantics and
  existing schema1 branch. Bound all labels/counts/config; forbid raw identifiers.
- [x] Implement convention orchestration reusing run_provisioned; opt-in lease
  renewal during setup/work/reconciliation cancels and awaits worker on loss,
  preserves failed state and release, and leaves no detached task after return.
- [x] Wire strict JSON config CLI and Make target; invalid config makes no network
  call and emits fixed diagnostics. Document executable foundation versus future
  load evidence, compatibility, capacity, commands, retention and live-proof gate.
- [x] Run complete `make sim-check`, PostgreSQL `make api-check`, doctor and
  `git diff --check`; use fresh evidence without duplicate reruns when unchanged.
- [x] Fresh unit reviewer then fresh whole-change reviewer inspect frozen diffs,
  approved contracts and evidence, returning all distinct applicable verdicts.
- [x] Parent runs bounded offline CLI/report artifact proof and verifies no debug,
  scratch, dead, duplicate or unrelated scope remains. Clean task infrastructure.

## Final external-action gate

Only after local implementation, deterministic checks and reviews are concrete:
request necessary authorization for publication/promotion/Staging execution.
AC17 requires five small live family proofs after inspection tooling reaches
Staging. No claim of full issue completion until those proofs pass. Record all
limitations and exact evidence; do not relax the approved live-proof criterion.

Publication authorization received after local implementation and reviews:
commit, push and open a normal PR. Staging promotion and live proofs remain a
separate gate; retain issue #225 until that acceptance evidence exists.

## Resources and baseline

Task PostgreSQL: tailtag225-db, no persistent volume; only it may be removed.
OrbStack initially stopped; restore stopped state if unrelated resources remain
in their original stopped state. Baseline simulator validation passed with zero
Semgrep findings. Baseline legacy inspection tests recorded independently.
