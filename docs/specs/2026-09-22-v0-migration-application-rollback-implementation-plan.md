# V0 Migration and Application Rollback Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish and deterministically protect TailTag's fail-closed V0 migration/application rollback policy, current Staging NO-GO evidence, and future exact-deployment rehearsal procedure.

**Architecture:** Keep the authoritative behavioral and evidence contract in one #206 specification, the actionable recovery procedure in the Staging runbook, and the general forward-fix boundary in the Development delivery runbook. Preserve live findings in one sanitized JSON record and extend the existing documentation-contract test surface; add no runtime rollback command, migration analyzer, application behavior, or new test infrastructure.

**Tech Stack:** Markdown runbooks/specifications, sanitized JSON evidence, Python 3.13/pytest documentation-contract tests, existing `make api-check`, Django/PostgreSQL migration-drift validation, Ruff, Pyright, and Semgrep.

## Global Constraints

- The frozen specification is `docs/specs/2026-09-22-v0-migration-application-rollback.md`; do not reinterpret or weaken it.
- Execution is STANDARD EXPANDED with MIGRATION, DATA INTEGRITY, RELIABILITY, and TEST ADEQUACY assurance.
- The final current-Staging decision is NO-GO; no live rollback, mechanics-only rehearsal, or artificial migration pair is authorized or required.
- Forward-fix is the safe fallback. Database rollback, reverse migration, and OR-8 restore behavior remain outside #206.
- `PRE_DEPLOY_COMMAND` behavior during rollback is unverified and must remain stated as unverified.
- Do not add a generic compatibility analyzer, rollback command, automatic rollback, dependency, schema/product change, or new test infrastructure.
- Evidence must contain no credentials, variable values, password material, private URLs, private resource identifiers, database contents, or personal identifiers.
- Preserve the user's pre-existing untracked Staging deployment records and all unrelated work.
- Test authors may change the approved documentation-contract test surface but must not invent production seams. Implementers must not weaken approved tests.
- Run focused tests first, then `./scripts/doctor.sh`, `git diff --check`, and `make api-check`. Track and remove only task-created disposable containers and networks.

## File and interface map

- `docs/specs/2026-09-22-v0-migration-application-rollback.md` — authoritative Acceptance Contract, Test Surface Contract, policy, investigation conclusion, and future evidence sequence.
- `docs/specs/2026-09-22-v0-migration-application-rollback-implementation-plan.md` — task handoff and verification sequence.
- `docs/specs/README.md` — discoverability link for #206 and this plan.
- `docs/development/backend-delivery-operations.md` — concise environment-agnostic compatibility/forward-fix decision boundary for Development maintainers, linked to the authoritative spec.
- `docs/development/staging.md` — canonical Staging decision procedure, current NO-GO conclusion, and future exact-D evidence sequence.
- `docs/development/staging-recovery/2026-09-22-issue-206-no-go.json` — sanitized machine-readable investigation evidence only; no mutation record or secret-bearing fields.
- `services/api/tests/test_runtime_commands.py` — focused static contract assertions over the documents and evidence JSON.

---

### Task 1: Confirm environment readiness and preserve existing state

**Files:**
- Read: `AGENTS.md`
- Read: `CONTRIBUTING.md`
- Read: the frozen #206 specification and this plan

**Interfaces:**
- Consumes: the focused branch plus the two pre-existing untracked deployment evidence files.
- Produces: a recorded baseline and ownership boundary for any task-created test resources.

- [x] **Step 1: Inspect the branch, diff, and containers**

Run:

```bash
git status --short --branch
git diff --check
docker ps --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'
```

Expected: the two pre-existing untracked deployment records remain untouched;
record unrelated running containers so cleanup cannot affect them.

- [x] **Step 2: Run the documentation baseline**

Run:

```bash
./scripts/doctor.sh
```

Expected: all applicable local repository checks pass. A dirty-worktree warning
caused only by approved task files or the pre-existing records is informational;
any unrelated failure is investigated before implementation.

### Task 2: Author and approve focused documentation-contract tests

**Role:** Independent `test_author`; the documentation implementer must not
weaken these tests.

**Files:**
- Modify: `services/api/tests/test_runtime_commands.py`
- Read: `docs/specs/2026-09-22-v0-migration-application-rollback.md`

**Interfaces:**
- Consumes: Acceptance Contract items 1-9 and the approved Test Surface Contract.
- Produces: failing objective assertions for the runbooks, spec index, and JSON evidence record.

- [x] **Step 1: Add a single cohesive #206 documentation-contract test unit**

Add focused tests that require:

- the spec index links the #206 spec and implementation plan;
- both runbooks link the authoritative #206 spec;
- expand/compatible/contract, positive old-app/current-state compatibility,
  forward-fix, and no routine reverse migration are explicit;
- the exact preferred/current/non-representative SHAs and relevant deployment
  IDs are retained;
- the #239 usable-password incompatibility and final NO-GO are present;
- exact `canRollback` and `deploymentRollback` signatures and the explicitly
  unverified `PRE_DEPLOY_COMMAND` boundary are present;
- the future procedure binds exact R/A/D identities, rejects ambiguous/lost
  responses without blind retry, uses #201 identity, performs smoke/focused
  read-write proof, and restores through #202 rather than a second rollback;
- the JSON evidence has an allowlisted shape, fixed outcomes, `live_mutation=false`,
  and no keys matching password, credential, token, secret, variable value,
  private URL, database content, or personal-identifier material.

- [x] **Step 2: Run the focused tests and confirm the expected red state**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_runtime_commands.py -k 'migration_rollback or issue_206'
```

Expected: failures identify the missing runbook/index/evidence implementation,
not an unavailable environment or an application seam.

- [x] **Step 3: Perform parent test-adequacy review**

Map each assertion to Acceptance Contract items 1-9. Reject tests that require
a live Railway call, generalize migration syntax into a safety oracle, inspect
secrets, or manufacture application/runtime behavior. Approve the tests before
Task 3.

### Task 3: Implement the maintained policy, runbook, and evidence surfaces

**Role:** Independent `implementer` using the frozen spec and approved Task 2 tests.

**Files:**
- Modify: `docs/specs/README.md`
- Modify: `docs/development/backend-delivery-operations.md`
- Modify: `docs/development/staging.md`
- Create: `docs/development/staging-recovery/2026-09-22-issue-206-no-go.json`
- Test: `services/api/tests/test_runtime_commands.py`

**Interfaces:**
- Consumes: exact policy, identifiers, sanitized findings, API shape, and future procedure from the frozen spec.
- Produces: discoverable maintainer guidance and machine-readable NO-GO evidence; no executable rollback interface.

- [x] **Step 1: Add the spec index entry**

Link the #206 contract and implementation/test handoff in
`docs/specs/README.md` beside the other operational-readiness contracts.

- [x] **Step 2: Replace the Development rollback summary with the frozen decision procedure**

In `docs/development/backend-delivery-operations.md`, retain Development scope
but link #206, state the expand/compatible/contract and forward-fix rules, and
require exact identity, migration/schema/data review, and pair-specific
PostgreSQL proof before application rollback. Remove the stale dashboard-only
claim and document that the verified Public API accepts an exact deployment ID.
Keep `PRE_DEPLOY_COMMAND` rollback behavior unverified.

- [x] **Step 3: Add the Staging #206 recovery section**

In `docs/development/staging.md`, add the fail-closed compatibility checklist,
the three investigated boundaries, the affirmative operator-state
incompatibility, the final NO-GO/no-mutation outcome, and the future R/A/D
evidence and #202 restoration sequence. Link the spec and evidence record rather
than duplicating secret-bearing diagnostics.

- [x] **Step 4: Add the sanitized evidence JSON**

Create `docs/development/staging-recovery/2026-09-22-issue-206-no-go.json` with
only allowlisted public UUIDs/SHAs/image digests, fixed status/outcome strings,
the migration names, Boolean proof results, exact API signatures, the unverified
pre-deploy field, cleanup completion, and `live_mutation=false`. Do not include
raw commands, outputs, variable maps, database rows, accounts, credentials, or
private target details.

- [x] **Step 5: Run the focused test to green**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_runtime_commands.py -k 'migration_rollback or issue_206'
```

Expected: all #206 documentation-contract tests pass.

### Task 4: Deterministic and assurance verification

**Files:**
- Verify: every file in the File and interface map

**Interfaces:**
- Consumes: completed documentation/evidence diff and approved tests.
- Produces: deterministic, scope, security, migration, and cleanup evidence.

- [x] **Step 1: Run documentation and whitespace checks**

```bash
./scripts/doctor.sh
git diff --check
```

Expected: applicable checks pass; no secret or personal data appears in output.

- [x] **Step 2: Run the authoritative repository gate**

```bash
make api-check
```

Expected: Ruff, Pyright, Semgrep, all PostgreSQL-backed tests, Django checks,
migration drift, OpenAPI generation, and Gunicorn verification pass.

- [x] **Step 3: Perform plausible-mutant analysis**

Confirm the approved tests reject at least: rollback authorized despite NO-GO;
forward-fix omitted; reverse migration described as routine; N falsely described
as deployed; the no-migration pair described as representative; password
incompatibility removed; `PRE_DEPLOY_COMMAND` asserted to run or skip; mutation
described as returning D; blind retry permitted; latest used instead of exact D;
and a second rollback used for restoration.

- [x] **Step 4: Inspect scope and cleanup**

```bash
git status --short
git diff --stat
git diff -- docs/specs docs/development services/api/tests/test_runtime_commands.py
docker ps -a --filter 'name=tailtag-issue-206-' --format '{{.ID}} {{.Names}} {{.Status}}'
```

Expected: every touched file is in the approved surface, the user's untracked
deployment records remain untouched, no task container remains, and no debug or
secret-bearing artifact exists.

### Task 5: Independent review and authoritative completion

**Role:** Fresh `spec_reviewer`, then fresh `code_reviewer`, followed by parent verification.

**Files:**
- Review: complete approved diff

**Interfaces:**
- Consumes: frozen spec, deterministic evidence, plausible-mutant analysis, and final diff.
- Produces: resolved specification/code-quality findings and completion evidence.

- [x] **Step 1: Run independent specification review**

Require explicit coverage of all nine Acceptance Contract items, the NO-GO
alternate path, sanitized evidence, and no unapproved live/runtime behavior.

- [x] **Step 2: Run independent code/test-quality review**

Review test scope, JSON safety, maintainability, repository conventions, and
whether assertions reject plausible unsafe documentation while avoiding brittle
prose duplication.

- [x] **Step 3: Resolve all BLOCKER/HIGH findings and selected in-scope MEDIUM findings**

Re-run the focused tests and applicable deterministic gates after any change.

- [x] **Step 4: Parent final verification**

Account for every Acceptance Contract item, inspect every touched file, verify
no live Staging mutation occurred, and report commands/results, review findings,
known limitations, and forward-fix/no-rollback operational impact.
