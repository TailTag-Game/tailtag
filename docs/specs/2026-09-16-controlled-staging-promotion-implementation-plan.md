# Controlled Staging Promotion Implementation Plan

> **For agentic workers:** Use ADW STANDARD COMPACT with independent test author,
> implementer and fresh Compact reviewer. Use subagent-driven-development or
> executing-plans for execution; neither coding nor live deployment is authorized
> by this research/design handoff.

**Goal:** Promote one eligible immutable main ancestor to Staging and retain
sanitized evidence for exact returned deployment D.

**Architecture:** One opt-in local maintainer script orchestrates existing
GitHub/Railway interfaces, #201 identity readback/join and existing HTTP smoke.
Railway's configured migration/readiness gates remain authoritative. A final
active-set comparison controls the current-promotion success claim.

**Tech Stack:** Existing Python/uv, gh and Railway CLIs, Railway GraphQL,
GitHub REST, existing pytest/subprocess test setup and Makefile checks.

## Global constraints

The frozen [#202 specification](2026-09-16-controlled-staging-promotion.md)
owns all acceptance, test-surface and scope decisions. Its AC-1 through AC-12
are the canonical independent-agent handoff. Do not replace their predicates.
Only `serviceInstanceDeployV2(commitSha=S)` may submit; capture returned D.
No retry, alternate path, autodeploy, recovery, Production or dependencies.
No raw metadata, environment values, secrets, private URLs or raw CLI errors.
Verify Finn identity before authenticated operations and stop on failure.

## Review unit: maintainer operator and runbook

**Create:** `scripts/api_staging_promote.py`,
`services/api/tests/test_api_staging_promote.py`.
**Modify:** `docs/development/staging.md`, `Makefile`,
`services/api/pyproject.toml`, `scripts/backend_ci_relevance.py`,
`services/api/tests/test_backend_ci_relevance.py`,
`services/api/tests/semgrep_support.py`; extend existing command-contract tests
only where registries are asserted. Do not broaden test infrastructure.
**Live proof artifact:** `docs/development/staging-deployments/<D>.json`.

**Consumes:** `main()` entry point of existing identity join script; actual
three-field stdout of `python -m config.build_identity` on selected instance;
existing `make api-smoke`; decoded REST/GraphQL shapes frozen in spec.
**Produces:** opt-in `main()` command accepting `--source-sha S --confirm
promote-tailtag-staging`, fixed-target exact-SHA submission, atomic allowlisted
D.json checkpoints and nonzero exit for every non-success overall result.

### 1. Readiness and independent acceptance tests

- [ ] Confirm approved coding authorization, focused branch, clean baseline and
  unchanged #200/#201 interfaces. Use repository toolchain/bootstrap guidance;
  run `make api-check` baseline before meaningful test/implementation work.
  Track and later restore only task-created or temporarily started test resources.
- [ ] Give a fresh test author the frozen spec and repository test patterns.
  Require a test-to-AC mapping and expected preimplementation failures.
  Cover every mutant listed in Test Surface Contract, atomic S/D capture before
  first observation, partial records on interruption, pagination, sanitized
  subprocess errors and stop-without-retry on identity/auth failures.
- [ ] Use deterministic fake interfaces. For older-ancestor acceptance, the fake
  compare returns `status='ahead'`, base and merge-base equal S, behind_by zero
  with M different from S; successful run has exact path/event/head_sha and
  completed/success fields. For supersession, all earlier gates succeed but
  final active list contains another ID: assert overall SUPERSEDED, historical
  gate results preserved and nonzero exit. For leakage, fake CLI error text
  contains a sentinel secret: assert sentinel absent from both output streams
  and every evidence-file byte.
- [ ] Run `uv --directory services/api run --locked --no-sync pytest
  tests/test_api_staging_promote.py -q`. Confirm failures reflect absent
  behavior rather than unavailable tools/network or unrelated setup.
- [ ] Parent approves test adequacy and scope, including each mutant and AC item,
  before handing approved tests/contracts to a separate implementer.

### 2. Implement the single supported operator

- [ ] Implement safe argument validation and fixed target/evidence path.
  Use subprocess argument arrays, `shell=False`, captured output and 30-second
  timeout. Never echo raw response/error streams. Before each gh request run
  exact approved account verification; repeat approved Railway verification
  immediately before submission. Failed operations stop, with no fallback.
- [ ] Implement commit resolution, remote immutable-main capture and comparison,
  workflow-list pagination and exact-run revalidation using the frozen requests.
  Accept older ancestors; do not reuse local branch state or PR validation.
- [ ] Verify evidence writability and canonical Staging source, disabled triggers,
  migration/readiness configuration and operator coordination. A mismatch stops
  without changing platform settings. Implement only the frozen mutation,
  extracting String D and checkpointing S/D before lifecycle calls.
- [ ] Implement exact-D target/status/event observation, cursor pagination,
  five-second progress polling and 20-minute bound. Classify errors/skips/
  incomplete evidence conservatively. Persist fixed outcomes; completion alone
  cannot pass and a failure does not establish database cleanliness.
- [ ] Select actual RUNNING instance belonging to D, explicitly pass instance ID
  to SSH, run unchanged #201 backend command, then feed actual stdout to the
  unchanged join script. Validate S/D/staging and use exact createdAt timestamp.
  Do not expose a new application seam or manufacture join input.
- [ ] Execute existing canonical HTTP smoke with captured output. Record only
  outcome. Query canonical active set immediately before success; evaluate D
  membership/status/running instance without choosing latest/first. Atomically
  finalize the allowlisted D.json and exit zero only for full success.
- [ ] Handle mutation-response loss and record-write failure explicitly, without
  resubmission or latest-ID discovery. Handle interruption as INDETERMINATE.
  Do not implement recovery, deployment cancellation or automatic retry.
- [ ] Register the script in existing formatting/lint/Pyright/Semgrep and backend
  relevance surfaces, following the #201 operator pattern. Extend relevant
  existing path/command matrices only to protect its inclusion.

### 3. Operator documentation and deterministic gate

- [ ] Update the Staging runbook to link the frozen contract and single supported
  opt-in operator. Document coordination, exact S selection, candidate rejection,
  expected states, evidence path, interruption, supersession, safe exact-D first
  diagnostics and OR-7 handoff. Keep bootstrap history distinct from promotion.
- [ ] Run focused operator tests, then affected CI/command-contract/Semgrep tests.
  Run `make api-check` including Semgrep. Do not weaken approved tests to fit
  implementation. Use realistic plausible-mutant analysis without introducing
  a mutation framework.
- [ ] Dispatch a fresh Compact reviewer with spec, tests, final diff and check
  evidence. Review acceptance, security, reliability, data boundary, evidence
  sanitization and scope. Resolve AC violations and BLOCKER/HIGH findings;
  parent judges MEDIUM findings against the frozen scope.

### 4. Separately authorized normal live proof and handoff

- [ ] Obtain publication/merge/live-operation authorization as required; verify
  approved author/committer before commit and Finn account immediately before
  each authenticated remote mutation. No push/deploy is authorized in research.
- [ ] Select a reviewed main ancestor S containing the implemented operator;
  verify exact successful push API run. Run one normal Staging promotion through
  the supported operator, capture returned D and retain its sanitized record.
  Do not substitute historical #201 branch-deployment evidence or run destructive
  failure experiments. Stop and report any live interface contradiction.
- [ ] Parent inspects all evidence fields, exact-SHA identity, required gate
  outcomes and final active state. If superseded/failed/indeterminate, report that
  outcome honestly; do not close acceptance or automatically deploy again.
- [ ] Run final authoritative relevant checks, `./scripts/doctor.sh` and
  `git diff --check`. Clean only task-owned disposable test resources, preserve
  persistent volumes and verify cleanup. Report AC coverage, changed files,
  deterministic/review/live results and shared-URL/point-in-time limitations.

## Plan self-review

AC-1/2/3 map to eligibility tests and operator preflight. AC-4/5/6 map to
submission/checkpoint/lifecycle tests and implementation. AC-7/8/9 map to
identity/smoke/active gates. AC-10/11 map to failure/interruption/sanitization
tests, evidence and runbook. AC-12 maps to separate reviewed live proof.
Every expected file serves the operator, its existing verification registries,
runbook or canonical evidence. No application/infrastructure change is planned.
