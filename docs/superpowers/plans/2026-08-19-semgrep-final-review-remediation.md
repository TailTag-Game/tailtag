# Semgrep Final-Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the final-review findings while preserving a deterministic,
local, fail-closed TailTag Semgrep gate that does not alter API production
dependencies.

**Architecture:** Semgrep moves from the API development environment to a
separate locked non-package project under `.semgrep/`; `make api-setup`, CI,
and the devcontainer synchronize both projects before the existing no-sync
`make api-check` contract runs. The canonical target validates fixture
metadata, runs Semgrep's fixtures, then scans the exact repository-owned scope
using local rules and an explicit empty baseline.

**Tech Stack:** Python 3.13, `uv`, Semgrep CE 1.173.0, GNU Make, Django,
pytest, GitHub Actions, JSON/TOML/YAML text validation with the Python standard
library where possible.

## Global Constraints

- The approved amendment at
  `docs/specs/2026-08-19-semgrep-validation-final-review-amendment.md`
  supersedes conflicting implementation details in the original Semgrep spec;
  preserve the original objective and non-goals.
- Semgrep is a separate non-package `.semgrep/pyproject.toml` plus
  `.semgrep/uv.lock` and ignored `.semgrep/.venv`; invoke it with
  `uv --directory .semgrep`.
- `services/api/uv.lock` must be byte-identical to
  `ede15f13bbde767f4816ffdb4f3b966d357ec78d`; parsed API
  `[project].dependencies` and `[dependency-groups]` must also equal that
  commit. The current no-dev tree/export must not contain Semgrep.
- `make api-setup`, CI setup, and devcontainer setup synchronize both locked
  projects. `make api-check` is no-sync, and CI retains exactly one validation
  command: `make api-check`.
- All Semgrep operations use checked-in local rules, disable metrics and
  version checks, pass `--baseline-commit ''`, and use no Registry, remote
  config, account, token, login, upload, or network rule download.
- Root `.semgrepignore` is the complete repository-owned ignore policy and
  does not exclude tests.
- Main-scan scope is every tracked `.py` under `services/api/` plus exactly
  `scripts/api_smoke.py`, `scripts/api_auth_smoke.py`,
  `scripts/clerk_development_session.py`,
  `scripts/backend_ci_relevance.py`, and
  `scripts/validate_semgrep_contract.py`.
- Do not add SCA, dependency vulnerability scanning, secret scanning, SARIF,
  AppSec Platform integration, runtime/API/database/deployment behavior, or a
  mutation-testing framework.
- Stop and return `NEEDS_CONTEXT` if a rule finds genuine repository source,
  the API runtime resolution (including `jsonschema`) cannot be restored, or
  meeting this plan would weaken the approved security scope.
- The implementation agent must not weaken, delete, or rewrite approved
  acceptance tests to make implementation pass.

## File and ownership map

| Area | Owner | Responsibility |
| --- | --- | --- |
| `.semgrep/tests/tailtag-security.py`; `services/api/tests/test_developer_commands.py`; `services/api/tests/test_backend_ci_relevance.py`; `services/api/tests/test_runtime_commands.py`; `services/api/tests/test_semgrep_contract.py`; `services/api/tests/test_semgrep_integration.py` | Independent test author | Freeze observable acceptance/regression coverage and RED evidence. |
| `.semgrep/pyproject.toml`; `.semgrep/uv.lock`; `.semgrep/.gitignore`; root `.semgrepignore`; `.semgrep/rules/tailtag-security.yml`; `Makefile`; `scripts/validate_semgrep_contract.py`; `scripts/backend_ci_relevance.py`; `services/api/pyproject.toml`; `services/api/uv.lock`; `.github/workflows/api.yml`; `.devcontainer/devcontainer.json` | Implementation agent | Implement only the approved contract; do not edit tests or docs. |
| `.semgrep/README.md`; `services/api/README.md`; `docs/architecture.md` | Documentation agent | Describe the implemented command/setup/scope/preflight/baseline and intentional limits; do not edit code or tests. |
| Whole diff and approved amendment | Fresh reviewers | Spec-compliance, code-quality, security, and integration evidence. |

---

### Task 1: Independently author and freeze remediation acceptance tests

**Files:**

- Modify: `.semgrep/tests/tailtag-security.py`
- Modify: `services/api/tests/test_developer_commands.py`
- Modify: `services/api/tests/test_backend_ci_relevance.py`
- Modify: `services/api/tests/test_runtime_commands.py`
- Create: `services/api/tests/test_semgrep_contract.py`
- Create: `services/api/tests/test_semgrep_integration.py`

**Interfaces:**

- Consumes: the approved amendment, current Make command shape, current rules,
  `scripts/backend_ci_relevance.py`, and Git tracked-file state.
- Produces: frozen behavior tests. Later implementation supplies
  `scripts/validate_semgrep_contract.py`, `.semgrep/pyproject.toml`, root
  `.semgrepignore`, canonical Make command construction, and isolated-scan
  behavior; it may not edit these tests.

- [ ] **Step 1: Add rule fixtures that express the approved precision boundary.**

  Add `ruleid` positives for direct interpolated f-string, `%`, and
  `.format(...)` expressions sent to `execute` on `cursor`, an identifier
  ending `_cursor`, `connection`, `conn`, `db`, and `self.cursor`; direct
  f-string calls through `connection.cursor().execute(...)` and
  `self.connection.cursor().execute(...)`; a same-lexical-block
  `query = f"...{user_input}..."` then `cursor.execute(query)`; and Django
  `Model.objects.raw(f"...{value}...")` plus imported and qualified
  `RawSQL(f"...{value}...", ...)`.

  Add `ok` fixtures for `Writer.execute`, `writer.execute`,
  `executor.execute`, a constant f-string/static assigned query, and a
  parameterized cursor query. Add safe YAML `ok` forms for
  `yaml.load(..., Loader=yaml.SafeLoader)`, `yaml.CSafeLoader`, and direct
  imports/aliases of both; retain a vulnerable `yaml.load` without those exact
  loaders as `ruleid`.

  ```python
  # ruleid: tailtag.django.dynamic-raw-sql
  query = f"SELECT * FROM users WHERE name = '{user_input}'"
  cursor.execute(query)

  # ok: tailtag.django.dynamic-raw-sql
  cursor.execute("SELECT * FROM users WHERE name = %s", [user_input])

  # ok: tailtag.python.unsafe-yaml-load
  yaml.load(document, Loader=yaml.SafeLoader)
  ```

- [ ] **Step 2: Add command, setup, dependency, and classifier contract assertions.**

  Update developer/runtime command tests to require both sync commands:

  ```bash
  uv --directory services/api sync --all-groups --locked
  uv --directory .semgrep sync --locked
  ```

  Require the separate executable form
  `uv --directory .semgrep run --locked --no-sync semgrep scan`, the validator
  before `scan --test`, explicit `--baseline-commit ''` on both Semgrep
  commands, local config, metrics/version disabling, and no remote/
  credential/upload tokens. Require no sync below `make api-check`, exactly
  one workflow validation command `make api-check`, and both-project CI and
  devcontainer setup. Require `.semgrep/`, `.semgrepignore`, all five helpers,
  Makefile, and API workflow to classify as relevant while existing unrelated
  paths remain irrelevant.

  Add immutable-baseline assertions that read commit
  `ede15f13bbde767f4816ffdb4f3b966d357ec78d` through Git, compare API lock
  bytes, parse TOML and compare only `[project].dependencies` and
  `[dependency-groups]`, and assert a locked no-dev API tree/export contains
  no Semgrep.

- [ ] **Step 3: Add direct validator invalid-case tests.**

  In `test_semgrep_contract.py`, execute the future script with temporary
  rule/fixture directories and assert nonzero plus a diagnostic for every
  mutation-style invalid case: zero directories/files, filesystem/I/O error,
  unsupported extension or file in either directory, malformed YAML/fixture
  annotation, unknown annotation, duplicate rule IDs, ambiguous/noncanonical
  rule IDs, basename mismatch, and any rule missing `ruleid` or `ok`.

  ```python
  completed = subprocess.run(
      [api_python, "scripts/validate_semgrep_contract.py", "--rules", str(rules), "--fixtures", str(fixtures)],
      cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False,
  )
  assert completed.returncode != 0
  assert "missing ok annotation" in completed.stderr
  ```

  Include a valid minimal matching rule/fixture control case. Do not test full
  Semgrep YAML/pattern semantics here; that remains `semgrep scan --test`.

- [ ] **Step 4: Add black-box canonical scan integration tests.**

  In `test_semgrep_integration.py`, derive the expected set independently from
  Git: `git ls-files -z -- services/api` filtered to `.py`, unioned with a
  literal frozen set of the five approved root helpers. Invoke the canonical
  main-scan configuration/shared command construction and parse Semgrep JSON
  `paths.scanned`; assert exact equality, including API tests. Do not derive
  expectations by parsing Make operands.

  Add the canonical baseline probe: create an isolated local clone/worktree of
  the current branch, symlink its `services/api/.venv` and `.semgrep/.venv` to
  already-synchronized environments, commit an approved-target `.py` file
  containing a known `ruleid` fixture, set `SEMGREP_BASELINE_COMMIT=HEAD`, and
  run `make api-semgrep-check` with no overrides. Assert nonzero and the
  expected `tailtag.*` rule ID. The test must not run a reconstructed Semgrep
  command or invoke network synchronization.

- [ ] **Step 5: Run the focused acceptance suite and record expected RED evidence.**

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_developer_commands.py tests/test_backend_ci_relevance.py \
    tests/test_runtime_commands.py tests/test_semgrep_contract.py \
    tests/test_semgrep_integration.py
  ```

  Expected before Task 2: RED because the separate `.semgrep` project/lock,
  root ignore policy, validator, new helper target, baseline flag, setup
  synchronization, rule precision, and canonical integration behavior do not
  yet exist. Existing unrelated assertions may remain green; do not change a
  test solely to remove RED evidence.

- [ ] **Step 6: Independent test-adequacy gate before implementation.**

  A fresh test reviewer receives the approved amendment and only this test
  diff. Confirm every acceptance clause is observable, plausible incorrect
  implementations are rejected, expected scope is independently derived, and
  the baseline probe invokes `make api-semgrep-check` unchanged. Resolve test
  defects now, rerun the focused suite to preserve expected RED, and obtain
  explicit approval before assigning Task 2.

- [ ] **Step 7: Task-level review and handoff.**

  Run `git diff --check`, then a fresh specification-compliance review and
  code-quality review of the test diff. Commit approved tests separately with
  an implementation-neutral message. Hand the immutable acceptance tests, RED
  output, and test-adequacy verdict to Task 2; the implementer has no
  authority to edit them.

### Task 2: Implement isolated deterministic Semgrep validation

**Files:**

- Create: `.semgrep/pyproject.toml`, `.semgrep/uv.lock`, `.semgrep/.gitignore`,
  `.semgrepignore`, `scripts/validate_semgrep_contract.py`
- Modify: `.semgrep/rules/tailtag-security.yml`, `Makefile`,
  `scripts/backend_ci_relevance.py`, `services/api/pyproject.toml`,
  `services/api/uv.lock`, `.github/workflows/api.yml`,
  `.devcontainer/devcontainer.json`

**Interfaces:**

- Consumes: frozen Task 1 tests, their RED evidence, and the approved
  amendment.
- Produces: separately locked Semgrep executable, validator CLI, canonical
  setup/scan flow, exact scope, relevance classification, and restored API
  dependency resolution for Task 3 documentation and Task 4 verification.

- [ ] **Step 1: Preflight the frozen contract and dependencies.**

  Read the Task 1 review verdict, run its focused tests unchanged, inspect
  current main findings with the intended local rules, and compare the API
  dependency state with the immutable baseline before editing. Use:

  ```bash
  git show ede15f13bbde767f4816ffdb4f3b966d357ec78d:services/api/uv.lock > /tmp/tailtag-api-baseline.lock
  cmp /tmp/tailtag-api-baseline.lock services/api/uv.lock
  ```

  Stop with `NEEDS_CONTEXT` for a genuine source finding, a dependency mismatch
  that prevents restored API resolution (including `jsonschema`), or any need
  to weaken the frozen security scope.

- [ ] **Step 2: Isolate and lock Semgrep without changing API production resolution.**

  Create a non-package `.semgrep/pyproject.toml` with Semgrep CE `1.173.0`,
  generate `.semgrep/uv.lock`, and ignore `.semgrep/.venv`. Remove Semgrep from
  API dependency configuration and restore `services/api/uv.lock` to the exact
  immutable baseline while preserving only allowed unrelated tool
  configuration. Synchronize with:

  ```bash
  uv --directory services/api sync --all-groups --locked
  uv --directory .semgrep sync --locked
  uv --directory .semgrep run --locked --no-sync semgrep --version
  ```

  Verify the API no-dev tree/export contains no Semgrep before continuing.

- [ ] **Step 3: Implement repository-owned scope, validator, and Make pipeline.**

  Add root `.semgrepignore` as the sole complete ignore policy, preserving all
  API tests in scan scope. Implement a stdlib-only
  `scripts/validate_semgrep_contract.py` that accepts rule/fixture directory
  inputs, checks only supported extensions, nonempty directories, canonical
  unique IDs, basename matching, valid/known annotation syntax, and per-rule
  `ruleid` plus `ok` coverage; any filesystem/I/O error fails nonzero.

  Make `api-semgrep-check` run, in order, the locked/no-sync API Python
  validator, the separate locked/no-sync Semgrep fixture scan, then the
  separate locked/no-sync full scan. Both Semgrep commands must use local
  config, disable metrics/version checks, and include
  `--baseline-commit ''`; the full scan is `--error`. Use shared Make variables
  or a single canonical command builder so the integration test exercises the
  exact production construction. Declare exactly the five root helpers and
  `services/api/` as source inputs; do not add other targets.

- [ ] **Step 4: Implement rule precision, setup, and relevance contracts.**

  Update rules to meet frozen YAML SafeLoader and raw-SQL shapes, including
  direct/same-block behavior only. Update `api-setup`, CI dependency setup, and
  devcontainer post-create setup to synchronize both projects; keep
  `api-check` no-sync and CI's only validation invocation `make api-check`.
  Update the classifier so `.semgrep/`, `.semgrepignore`, Makefile, API
  workflow, and the five helpers are relevant while all prior irrelevant paths
  stay irrelevant.

- [ ] **Step 5: Run narrow implementation verification against frozen tests.**

  ```bash
  make api-setup
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_developer_commands.py tests/test_backend_ci_relevance.py \
    tests/test_runtime_commands.py tests/test_semgrep_contract.py \
    tests/test_semgrep_integration.py
  make api-semgrep-check
  git diff --check
  ```

  Expected after implementation: GREEN with rule fixtures discovered, zero
  approved-scope findings, exact `paths.scanned`, baseline probe failure with
  the planted expected ID, and no API Semgrep dependency. If a genuine finding
  occurs, stop rather than suppress it.

- [ ] **Step 6: Task-level review and handoff.**

  Run fresh spec-compliance and code-quality reviews against the amendment and
  frozen tests, then commit only implementation-owned files. Provide commands,
  results, lock comparison, no-dev evidence, and any `NEEDS_CONTEXT` decision
  to Tasks 3 and 4. Do not modify test or documentation files.

### Task 3: Document the implemented isolated gate

**Files:**

- Modify: `.semgrep/README.md`, `services/api/README.md`,
  `docs/architecture.md`

**Interfaces:**

- Consumes: Task 2's reviewed Make/setup/validator/scope behavior and Task 1
  frozen acceptance contract.
- Produces: accurate contributor and architecture documentation; no executable
  changes.

- [ ] **Step 1: Confirm the reviewed implementation contract before editing prose.**

  Inspect the final Make targets, `.semgrepignore`, validator invocation,
  workflow, devcontainer setup, rules, and scan JSON contract. Record the
  exact two synchronization commands and validate the canonical command with:

  ```bash
  make api-setup
  make api-semgrep-check
  ```

  Stop for clarification if implementation differs from the approved
  amendment; do not document an unapproved behavior.

- [ ] **Step 2: Update rule-maintenance documentation.**

  In `.semgrep/README.md`, state TailTag ownership, rule naming and fixture
  discipline, the separate locked project and ignored virtual environment,
  validator preflight before Semgrep fixture testing, full effective scope,
  explicit empty baseline, and findings-stop policy. Describe only
  syntax-local/direct/same-block raw-SQL coverage and explicitly exclude
  arbitrary aliases, interprocedural flow, and unsupported concatenation.

- [ ] **Step 3: Update contributor and architecture documentation.**

  In `services/api/README.md`, document that setup synchronizes both locked
  projects, `api-semgrep-check` is deterministic/local/no-sync after setup,
  and `api-check` remains the single local/CI contract. In
  `docs/architecture.md`, state that CI first synchronizes both locked
  projects then invokes exactly `make api-check`, and retain the classifier
  boundary. Explicitly state no account/token/Registry/remote config/upload,
  no SCA/dependency or secrets scanning, no SARIF/AppSec integration, and no
  claim of complete or interfile coverage.

- [ ] **Step 4: Verify and review documentation.**

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q tests/test_runtime_commands.py
  ./scripts/doctor.sh
  git diff --check
  ```

  Run fresh specification-compliance and documentation-quality reviews,
  confirm no unsupported fixture-file restriction is reintroduced, and commit
  only the three documentation files.

### Task 4: Whole-change verification and final independent reviews

**Files:**

- Verify: all changed files from Tasks 1–3 and the approved amendment
- Add only review/remediation artifacts if a reviewer identifies a real issue;
  otherwise make no product changes in this task

**Interfaces:**

- Consumes: committed test, implementation, and documentation tasks; their
  review evidence; and the amendment.
- Produces: final acceptance evidence or a concrete `NEEDS_CONTEXT`/remediation
  handoff.

- [ ] **Step 1: Reproduce the deterministic gate and exact scope.**

  ```bash
  make api-setup
  make api-semgrep-check
  uv --directory services/api run --locked --no-sync pytest -q tests/test_semgrep_integration.py
  ```

  Confirm the standalone online/offline gate discovers fixtures, reports zero
  approved-scope findings, and `paths.scanned` exactly matches tracked API
  Python plus the frozen five-helper set, including API tests.

- [ ] **Step 2: Reproduce baseline, validator, and dependency acceptance.**

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q tests/test_semgrep_contract.py
  uv --directory services/api lock --check
  uv --directory .semgrep lock --check
  ```

  Confirm the test's isolated clone/worktree baseline probe uses symlinked
  synchronized environments, runs unmodified `make api-semgrep-check`, and
  detects the planted target despite inherited `SEMGREP_BASELINE_COMMIT`.
  Confirm byte-level API lock and parsed dependency-group comparison against
  `ede15f13bbde767f4816ffdb4f3b966d357ec78d`, plus no Semgrep in the current
  locked no-dev API tree/export.

- [ ] **Step 3: Run the authoritative repository gate and hygiene checks.**

  ```bash
  make api-check
  ./scripts/doctor.sh
  git diff --check
  git status --short
  ```

  Require a clean working tree after committed artifacts. Treat any genuine
  Semgrep finding, dependency-resolution mismatch, or required security-scope
  weakening as `NEEDS_CONTEXT`, not a cleanup task.

- [ ] **Step 4: Obtain fresh final reviews and integrate only approved fixes.**

  Give separate fresh reviewers the amendment and whole diff: one
  spec-compliance review, one code-quality review, and one security review.
  Each must independently pass. If any reviewer identifies a substantive
  issue, route it to a bounded new task with RED evidence and re-run all
  affected acceptance and final reviews; never weaken Task 1 tests to close a
  finding.

- [ ] **Step 5: Record completion evidence.**

  Report acceptance-contract coverage, exact commands/results, reviewer
  verdicts, dependency and security impact, and the absence of runtime/API/DB/
  deployment behavior changes. Do not claim SCA, secret scanning,
  comprehensive security, arbitrary SQL flow analysis, or interfile coverage.

## Plan self-review

- Amendment coverage: Tasks 1–4 cover dependency isolation, immutable API
  comparison, scope and relevance, fail-closed validator behavior, baseline
  resistance, YAML/SQL precision, documentation, deterministic verification,
  and `NEEDS_CONTEXT` triggers.
- Independence: test authorship and test adequacy approval precede the
  implementation task; the implementation owner has no test or docs authority;
  each task ends with fresh spec and quality review; final security review is
  separate.
- Placeholder scan: no deferred implementation marker is used; every task has
  explicit owned files, commands, RED/GREEN behavior, and handoff criteria.
- Contract consistency: commands use locked/no-sync validation after explicit
  two-project setup, and CI preserves exactly one `make api-check` validation
  command.

## Execution handoff

Plan saved to
`docs/superpowers/plans/2026-08-19-semgrep-final-review-remediation.md`.
Execute with Subagent-Driven Development: one fresh agent for Task 1, an
independent test-adequacy review before Task 2, one fresh agent each for Tasks
2 and 3, then fresh whole-change reviewers for Task 4.
