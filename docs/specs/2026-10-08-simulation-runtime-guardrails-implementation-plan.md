# Simulation runtime guardrails implementation plan

Goal: implement approved #227 AC1–AC24 locally, then present AC25 live proof.
Architecture: one shared protected-client safety runtime; orchestration controls
phases/cancellation; privileged relays compare pinned identity; schema4 evidence
preserves historical reports/scenarios. Stack: existing Python3.13/httpx0.28.1,
uv, Ruff, Pyright, pytest and Semgrep; no new runtime dependencies.
Worker handoff: adjacent design contract, `.refinement/227.md`, this plan.
ADW independent Test Author ≠ Implementer ≠ Reviewer replaces redundant skill
execution-choice prompts; local implementation is already authorized.

## Global constraints

AC13 ceilings, AC12 polling/deadline, AC16 error windows are frozen in the design.
Preserve public-only SIMULATION, exact Staging/local policy, bounded inspection,
existing retries/workload budgets, closed sanitized report validation. External
actions require separate authorization; no automated metric ingestion.
Subsequent user authorization covered the source commit, bounded Staging proof,
two-identity provisioning, one normal retry, and PR publication. Deployment and
merge remain unauthorized.

## U1 — Safety core and protected HTTP/target boundary

- [x] Independent Test Author proposes minimal cases for policy, actual sends,
  concurrency/probe reserve, pause/abort/deadline/window boundaries; parent approves.
- [x] Write tests at real transport/clock seams; record legitimate red.
- [x] Implement frozen `SafetyRuntime`/policy/client/target contract. Observe real
  responses below injected effects; no privileged handles enter public behavior.
- [x] Focused tests and format/lint/type/Semgrep pass; fresh diff-first reviewer
  returns SPEC/QUALITY/TEST/SCOPE and assurance verdicts; resolve material findings.

## U2 — Pinned privileged calls

- [x] Author/parent approve three-relay parity and matching/malformed/mismatch
  tests plus channel wire-shape tests; record legitimate red.
- [x] Implement optional expected tuple in caller/host envelope, verify before
  SSH, strip from unchanged remote wire; map mismatch to latched safety abort.
- [x] Focused relay tests and relevant backend gates; independent unit review.
  Do not alter remote gameplay/model/DB schema or existing standalone management.

## U3 — Schema4 safety evidence

- [x] Coordinate exact U1 snapshot shape; independent schema/privacy/compatibility/
  persistence tests, parent minimization, legitimate red.
- [x] Implement recorder/closed validator; new reports schema4; historical fixture
  validators unchanged; aborted never passes; preserve immutable descriptors.
- [x] Focused report/static gates and fresh unit review.

## U4 — Lifecycle/operator integration

- [x] Independent behavioral tests for command/version parity, abort-class
  finalization matrix, partial state/cancellation, global reserve, CLI/signal and
  unattended refusal. Parent approves and author records legitimate red.
- [x] Wire every execution entry point to default or supplied safety runtime;
  strict phase gates, monitor/owned phase termination, correct finalization, fixed
  operator stop, separate JSON config, safe Makefile forwarding, documentation.
- [x] Classify actual correctness and transient/ordinary rejection failure seams;
  preserve failed-run evidence and actual uncertain commits.
- [x] Focused tests and canonical simulator checks; independent unit review.

## Integrated evidence and closeout

- [x] Real-orchestration offline reports/transcripts for normal and operator-stop
  paths, plus behavioral tests for readiness, identity, ceiling, correctness and
  finalization paths using only approved external fakes.
- [x] Plausible-mutant analysis for target equality, budgets/reserves, injected
  failure exclusion, abort outcome, and post-mismatch traffic prohibition.
- [x] Fresh whole-change reviewer at Sol/xhigh, diff-first; no duplicate fresh
  deterministic checks unless finding/code change requires them.
- [x] Final `make sim-check`, applicable backend checks, doctor, diff/scope audit;
  stop/remove task-owned disposable resources, restore engine state if started.
- [x] AC coverage/review/evidence ledger updated. Prepare concrete small Staging
  normal/operator-stop proof with bounded configuration and recovery steps;
  the separately explicit AC25 live gate passed; see the
  [Staging proof](2026-10-08-simulation-runtime-guardrails-staging-proof.md).

No implementation or external success claim is permitted without fresh evidence.
