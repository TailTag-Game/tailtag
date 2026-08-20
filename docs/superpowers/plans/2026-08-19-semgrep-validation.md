# Deterministic Semgrep Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a locked, repository-owned Semgrep CE security gate to TailTag's canonical local and GitHub backend validation workflow.

**Architecture:** Semgrep is a development-only dependency executed through the existing `uv` project. A root `.semgrep/` directory owns one high-confidence TailTag ruleset and its positive/negative fixtures. The root Makefile is the single execution boundary; `make api-check` composes the Semgrep target, while GitHub Actions continues to invoke only `make api-check`.

**Tech Stack:** Semgrep CE 1.173.0, Python 3.13, uv lockfiles, GNU Make, pytest, GitHub Actions.

## Global Constraints

- All blocking rules are TailTag-authored and checked into `.semgrep/rules/`; do not copy, vendor, or fetch third-party or Registry rules.
- The scan must use no Semgrep account, token, remote config, rule download, metrics, version check, prompt, or scan-time dependency synchronization.
- Use `semgrep scan`, local `--config`, `--error`, `--metrics=off`, `--disable-version-check`, `SEMGREP_SEND_METRICS=off`, and `SEMGREP_ENABLE_VERSION_CHECK=0`.
- Execute Semgrep through `uv --directory services/api run --locked --no-sync` so `make api-setup`/CI owns dependency installation.
- Scan `services/api/` and exactly the four root Python helpers already covered by Ruff/Pyright: `scripts/api_smoke.py`, `scripts/api_auth_smoke.py`, `scripts/clerk_development_session.py`, and `scripts/backend_ci_relevance.py`.
- Do not scan docs, mobile code, ignored `.env` files, caches, virtual environments, archived material, or unrelated automation.
- Findings, invalid rules, and scanner errors are blocking. Do not add blanket `nosemgrep`, a findings baseline, or repository-wide ignores.
- If the initial scan finds a genuine existing vulnerability, stop and return `NEEDS_CONTEXT`; do not fix runtime code or weaken a rule inside this tooling plan.
- GitHub Actions must retain exactly one `run: make api-check`, `contents: read`, and no Semgrep-specific action, secret, token, account, or permission.
- The production Docker stage must retain `uv sync --locked --no-dev --no-install-project`; Semgrep must remain absent from production dependencies.
- No application behavior, API, model, migration, database, deployment, or external service changes are in scope.

---

### Task 1: Freeze the Semgrep acceptance contract

**Files:**
- Modify: `services/api/tests/test_backend_ci_relevance.py`
- Modify: `services/api/tests/test_developer_commands.py`
- Modify: `services/api/tests/test_runtime_commands.py`
- Create: `.semgrep/tests/tailtag-security.py`

**Interfaces:**
- Consumes: the approved design in `docs/specs/2026-08-19-semgrep-validation.md`.
- Produces: frozen pytest command/CI assertions and Semgrep `ruleid`/`ok` fixtures for Task 2.

- [ ] **Step 1: Add RED backend-relevance cases**

Add these parametrized cases to `test_classification_matches_the_backend_path_contract`:

```python
([".semgrep/rules/tailtag-security.yml"], True),
([".semgrep/tests/tailtag-security.py"], True),
```

Keep every existing irrelevant-path case unchanged.

- [ ] **Step 2: Add RED developer-command assertions**

Extend `test_help_lists_the_canonical_backend_commands` with:

```python
"api-semgrep-check": "Run deterministic TailTag Semgrep security analysis.",
```

Extend `test_check_composes_every_required_backend_validation` to require both
`semgrep scan --test` and `semgrep scan`, and assert the first Semgrep command
appears before `pytest -q`.

Add a focused test named
`test_semgrep_check_is_local_locked_noninteractive_and_credential_free`. It
runs `make -n api-semgrep-check` and asserts:

```python
assert completed.returncode == 0, completed.stderr
assert "uv --directory services/api run --locked --no-sync semgrep scan" in completed.stdout
assert "--test" in completed.stdout
assert f"--config {REPOSITORY_ROOT / '.semgrep' / 'rules'}" in completed.stdout
assert str(REPOSITORY_ROOT / ".semgrep" / "tests") in completed.stdout
assert "--error" in completed.stdout
assert "--metrics=off" in completed.stdout
assert "--disable-version-check" in completed.stdout
assert "SEMGREP_SEND_METRICS=off" in completed.stdout
assert "SEMGREP_ENABLE_VERSION_CHECK=0" in completed.stdout
assert "--config auto" not in completed.stdout
assert "semgrep ci" not in completed.stdout
assert "SEMGREP_APP_TOKEN" not in completed.stdout
assert "SEMGREP_API_TOKEN" not in completed.stdout
assert "https://" not in completed.stdout
```

Assert the dry-run scan contains `services/api` and the absolute paths of the
four root helpers. Assert it does not contain a command that reads `.env`,
invokes Docker, applies migrations, or executes the authenticated smoke helper.
The helper's file path is allowed only as a Semgrep scan target.

- [ ] **Step 3: Add RED dependency and CI-thinness assertions**

Add `test_semgrep_is_locked_as_a_development_only_dependency` to
`test_developer_commands.py`. Read `pyproject.toml`, `uv.lock`, and the
production Dockerfile and assert:

```python
assert '"semgrep==1.173.0"' in pyproject
assert 'name = "semgrep"' in lockfile
assert "uv sync --locked --no-dev --no-install-project" in dockerfile
```

Extend `test_contributor_commands_and_ci_share_the_api_foundation_contract` in
`test_runtime_commands.py` to require `make api-semgrep-check` in the API
README while retaining `workflow.count("run: make api-check") == 1`. Add
`semgrep scan` and `api-semgrep-check` to the duplicated-workflow commands that
must not appear in `.github/workflows/api.yml`. Assert the workflow contains no
`SEMGREP_APP_TOKEN`, `SEMGREP_API_TOKEN`, `semgrep.dev`, or Semgrep-specific
GitHub Action.

- [ ] **Step 4: Create rule fixtures before rules exist**

Create `.semgrep/tests/tailtag-security.py` as parseable Python containing a
`# ruleid: <id>` vulnerable example for every `pattern-either` branch in the
planned rules and at least one `# ok: <id>` safe neighbor for each exact ID:

```text
tailtag.python.dynamic-execution
tailtag.python.shell-execution
tailtag.python.unsafe-deserialization
tailtag.python.unsafe-yaml-load
tailtag.http.disabled-tls-verification
tailtag.django.mark-safe
tailtag.django.dynamic-raw-sql
tailtag.storage.public-object-acl
tailtag.storage.presigned-upload
```

Use these vulnerable/safe pairs:

```python
import ast
import json
import marshal
import os
import pickle
import subprocess

import httpx
import requests
import yaml
from django.db.models.expressions import RawSQL
from django.utils.html import format_html
from django.utils.safestring import mark_safe

user_input = "untrusted"

# ruleid: tailtag.python.dynamic-execution
eval(user_input)
# ruleid: tailtag.python.dynamic-execution
exec(user_input)
# ok: tailtag.python.dynamic-execution
ast.literal_eval(user_input)

# ruleid: tailtag.python.shell-execution
os.system(user_input)
# ruleid: tailtag.python.shell-execution
subprocess.run(user_input, shell=True, check=True)
# ok: tailtag.python.shell-execution
subprocess.run(["git", "status"], check=True)

# ruleid: tailtag.python.unsafe-deserialization
pickle.load(source_file)
# ruleid: tailtag.python.unsafe-deserialization
pickle.loads(user_input.encode())
# ruleid: tailtag.python.unsafe-deserialization
marshal.load(source_file)
# ruleid: tailtag.python.unsafe-deserialization
marshal.loads(user_input.encode())
# ok: tailtag.python.unsafe-deserialization
json.loads(user_input)

# ruleid: tailtag.python.unsafe-yaml-load
yaml.load(user_input)
# ok: tailtag.python.unsafe-yaml-load
yaml.safe_load(user_input)

# ruleid: tailtag.http.disabled-tls-verification
requests.get("https://example.test", verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.get("https://example.test", verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.Client(verify=False)
# ruleid: tailtag.http.disabled-tls-verification
httpx.AsyncClient(verify=False)
# ok: tailtag.http.disabled-tls-verification
requests.get("https://example.test", verify=True)

# ruleid: tailtag.django.mark-safe
mark_safe(user_input)
# ruleid: tailtag.django.mark-safe
django.utils.safestring.mark_safe(user_input)
# ok: tailtag.django.mark-safe
format_html("{}", user_input)

# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = '%s'" % user_input)
# ruleid: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = '{}'".format(user_input))
# ruleid: tailtag.django.dynamic-raw-sql
User.objects.raw(f"SELECT * FROM users WHERE name = '{user_input}'")
# ruleid: tailtag.django.dynamic-raw-sql
RawSQL(f"SELECT id FROM users WHERE name = '{user_input}'", ())
# ok: tailtag.django.dynamic-raw-sql
cursor.execute("SELECT * FROM users WHERE name = %s", [user_input])

# ruleid: tailtag.storage.public-object-acl
s3_client.put_object(Bucket="bucket", Key="key", Body=b"x", ACL="public-read")
# ruleid: tailtag.storage.public-object-acl
s3_client.put_object(
    Bucket="bucket", Key="key", Body=b"x", ACL="public-read-write"
)
# ok: tailtag.storage.public-object-acl
s3_client.put_object(Bucket="bucket", Key="key", Body=b"x")

# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("put_object", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("upload_part", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("create_multipart_upload", Params={})
# ruleid: tailtag.storage.presigned-upload
s3_client.generate_presigned_post(Bucket="bucket", Key="key")
# ok: tailtag.storage.presigned-upload
s3_client.generate_presigned_url("get_object", Params={})
```

Undefined fixture-only names such as `cursor` and `s3_client` are intentional;
the file is parsed by Semgrep, not executed by pytest.

- [ ] **Step 5: Verify RED for the expected missing contract**

Run:

```bash
uv --directory services/api run pytest -q \
  tests/test_backend_ci_relevance.py \
  tests/test_developer_commands.py \
  tests/test_runtime_commands.py
```

Expected: only the new Semgrep expectations fail because `.semgrep/` is not
classified, the dependency/lock entry and Make target do not exist, and the
README does not document the command. Existing assertions remain green.

Attempt the future rule-test command:

```bash
uv --directory services/api run semgrep scan --test \
  --config ../../.semgrep/rules ../../.semgrep/tests
```

Expected: command failure because Semgrep and the rules do not yet exist. Record
this separately from the pytest RED evidence.

- [ ] **Step 6: Run test-file static checks and commit**

Run:

```bash
uv --directory services/api run ruff format --check \
  tests/test_backend_ci_relevance.py \
  tests/test_developer_commands.py \
  tests/test_runtime_commands.py
uv --directory services/api run ruff check \
  tests/test_backend_ci_relevance.py \
  tests/test_developer_commands.py \
  tests/test_runtime_commands.py
uv --directory services/api run pyright
git diff --check
```

Commit:

```bash
git add .semgrep/tests/tailtag-security.py \
  services/api/tests/test_backend_ci_relevance.py \
  services/api/tests/test_developer_commands.py \
  services/api/tests/test_runtime_commands.py
git commit -m "test: freeze Semgrep validation contract"
```

---

### Task 2: Implement the locked local Semgrep gate

**Files:**
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/uv.lock`
- Modify: `Makefile`
- Modify: `scripts/backend_ci_relevance.py`
- Create: `.semgrep/rules/tailtag-security.yml`

**Interfaces:**
- Consumes: the frozen pytest assertions and `.semgrep/tests/tailtag-security.py` from Task 1.
- Produces: `make api-semgrep-check`, nine TailTag-owned blocking rules, and `.semgrep/` CI relevance.

- [ ] **Step 1: Re-run the focused RED contract**

Run the Task 1 pytest command and confirm the new failures still identify the
missing dependency, Make target, relevance prefix, and docs. Do not edit tests.

- [ ] **Step 2: Add and lock Semgrep CE**

Add this exact development dependency to `services/api/pyproject.toml`:

```toml
"semgrep==1.173.0",
```

Run:

```bash
uv --directory services/api lock
uv --directory services/api sync --all-groups --locked
uv --directory services/api run --locked --no-sync semgrep --version
```

Expected version: `1.173.0`. Review the lock diff and ensure existing direct
dependency versions do not change unexpectedly.

- [ ] **Step 3: Implement the TailTag-owned ruleset**

Create `.semgrep/rules/tailtag-security.yml` with `languages: [python]`,
`severity: ERROR`, `metadata.owner: tailtag`, and `metadata.confidence: HIGH`
for each rule. Implement these exact behaviors:

```yaml
rules:
  - id: tailtag.python.dynamic-execution
    message: Dynamic Python execution is not allowed in TailTag code.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: eval(...)
      - pattern: exec(...)

  - id: tailtag.python.shell-execution
    message: Shell command execution is not allowed; pass an argument vector without shell=True.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: os.system(...)
      - pattern: subprocess.$FUNC(..., shell=True, ...)

  - id: tailtag.python.unsafe-deserialization
    message: Pickle and marshal deserialization are not allowed for TailTag data.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: pickle.load(...)
      - pattern: pickle.loads(...)
      - pattern: marshal.load(...)
      - pattern: marshal.loads(...)

  - id: tailtag.python.unsafe-yaml-load
    message: Use yaml.safe_load instead of yaml.load.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern: yaml.load(...)

  - id: tailtag.http.disabled-tls-verification
    message: TLS certificate verification must remain enabled.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: requests.$METHOD(..., verify=False, ...)
      - pattern: httpx.$METHOD(..., verify=False, ...)
      - pattern: httpx.Client(..., verify=False, ...)
      - pattern: httpx.AsyncClient(..., verify=False, ...)

  - id: tailtag.django.mark-safe
    message: Use contextual escaping such as format_html instead of mark_safe.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: mark_safe(...)
      - pattern: django.utils.safestring.mark_safe(...)

  - id: tailtag.django.dynamic-raw-sql
    message: Pass SQL values as database parameters instead of constructing SQL dynamically.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: $CURSOR.execute(f"...", ...)
      - pattern: $CURSOR.execute($SQL % $VALUE, ...)
      - pattern: $CURSOR.execute($SQL.format(...), ...)
      - pattern: $MODEL.objects.raw(f"...", ...)
      - pattern: RawSQL(f"...", ...)

  - id: tailtag.storage.public-object-acl
    message: TailTag object storage must remain private.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: $CLIENT.$METHOD(..., ACL="public-read", ...)
      - pattern: $CLIENT.$METHOD(..., ACL="public-read-write", ...)

  - id: tailtag.storage.presigned-upload
    message: Presigned upload operations are not allowed in the V0 media boundary.
    languages: [python]
    severity: ERROR
    metadata: {owner: tailtag, confidence: HIGH}
    pattern-either:
      - pattern: $CLIENT.generate_presigned_url("put_object", ...)
      - pattern: $CLIENT.generate_presigned_url("upload_part", ...)
      - pattern: $CLIENT.generate_presigned_url("create_multipart_upload", ...)
      - pattern: $CLIENT.generate_presigned_post(...)
```

If Semgrep 1.173.0 rejects a syntactic spelling, make the smallest equivalent
syntax correction that preserves the fixture behavior and record it in the task
report. Do not broaden or weaken a rule to obtain a passing scan.

- [ ] **Step 4: Add the canonical Make target**

Add absolute path variables near the existing root script variables:

```make
SEMGREP_RULES ?= $(CURDIR)/.semgrep/rules
SEMGREP_TESTS ?= $(CURDIR)/.semgrep/tests
SEMGREP_TARGETS ?= $(CURDIR)/services/api \
	$(SMOKE_SCRIPT) \
	$(AUTH_SMOKE_SCRIPT) \
	$(CLERK_DEVELOPMENT_SESSION_SCRIPT) \
	$(CI_RELEVANCE_SCRIPT)
SEMGREP ?= $(API_UV) run --locked --no-sync semgrep
```

Add `api-semgrep-check` to `.PHONY`, help output, and `api-check` immediately
before `api-test`. Implement:

```make
api-semgrep-check: ## Run deterministic TailTag Semgrep security analysis.
	@printf '%s\n' 'Testing TailTag Semgrep rules...'
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 \
		$(SEMGREP) scan --test \
		--config $(SEMGREP_RULES) \
		--metrics=off \
		--disable-version-check \
		$(SEMGREP_TESTS)
	@printf '%s\n' 'Running TailTag Semgrep security analysis...'
	SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0 \
		$(SEMGREP) scan \
		--config $(SEMGREP_RULES) \
		--error \
		--metrics=off \
		--disable-version-check \
		$(SEMGREP_TARGETS)
```

Preserve `.NOTPARALLEL: api-check` and every existing prerequisite.

- [ ] **Step 5: Make `.semgrep/` backend-relevant**

Change the classifier prefix constant to:

```python
BACKEND_RELEVANT_PREFIXES = ("services/api/", ".semgrep/")
```

Do not broaden other prefixes or files.

- [ ] **Step 6: Verify rules and the clean main baseline**

Run:

```bash
make api-semgrep-check
```

Expected:

- all nine rule IDs have their annotated vulnerable findings;
- all `ok` examples remain unreported;
- the repository scan reports zero findings;
- the command exits zero without a login, prompt, Registry fetch, metrics, or
  version request.

Also run with outbound resolution deliberately unavailable:

```bash
HTTPS_PROXY=http://127.0.0.1:1 \
HTTP_PROXY=http://127.0.0.1:1 \
ALL_PROXY=http://127.0.0.1:1 \
NO_PROXY= \
UV_OFFLINE=1 \
make api-semgrep-check
```

Expected: identical success using the already-synchronized dependency and
local rules.

If the repository scan reports a genuine existing vulnerability, return
`NEEDS_CONTEXT` without changing runtime code or suppressing the finding.

- [ ] **Step 7: Make the focused contract GREEN**

Run the Task 1 pytest command. Expected: relevance, dependency, Make command,
and CI-thinness assertions pass; only the README documentation assertion may
remain RED for Task 3.

Run:

```bash
uv --directory services/api run ruff format --check \
  ../../scripts/backend_ci_relevance.py \
  tests/test_backend_ci_relevance.py \
  tests/test_developer_commands.py
uv --directory services/api run ruff check \
  ../../scripts/backend_ci_relevance.py \
  tests/test_backend_ci_relevance.py \
  tests/test_developer_commands.py
uv --directory services/api run pyright
uv --directory services/api lock --check
git diff --check
```

- [ ] **Step 8: Commit the operational gate**

```bash
git add .semgrep/rules/tailtag-security.yml Makefile \
  scripts/backend_ci_relevance.py \
  services/api/pyproject.toml services/api/uv.lock
git commit -m "chore(api): add deterministic Semgrep gate"
```

---

### Task 3: Document the security-analysis workflow

**Files:**
- Create: `.semgrep/README.md`
- Modify: `services/api/README.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: `make api-semgrep-check`, the local rule/test directories, and the final scan scope from Task 2.
- Produces: contributor operation and rule-maintenance guidance without changing executable behavior.

- [ ] **Step 1: Confirm the documentation assertion is RED**

Run:

```bash
uv --directory services/api run pytest -q tests/test_runtime_commands.py
```

Expected: the new `make api-semgrep-check` README assertion fails while the
existing CI-thinness assertions pass.

- [ ] **Step 2: Document rule ownership beside the rules**

Create `.semgrep/README.md` documenting:

- TailTag owns every blocking rule; no Registry or copied upstream rules;
- rule IDs use `tailtag.<area>.<behavior>`;
- every rule requires `ruleid` and `ok` fixtures;
- run `make api-semgrep-check` after `make api-setup`;
- metrics, version checks, login, tokens, and remote configs are forbidden;
- a genuine existing finding stops a tooling change rather than being hidden;
- Semgrep does not provide dependency or secrets scanning in this setup.

Include the exact files `.semgrep/rules/tailtag-security.yml` and
`.semgrep/tests/tailtag-security.py`.

- [ ] **Step 3: Update the API contributor command contract**

In `services/api/README.md`:

- add `make api-semgrep-check` to the canonical command table with the same help
  description as the Makefile;
- add Semgrep rule tests and the local blocking scan to the enumerated
  `make api-check` stages;
- state that the gate uses checked-in TailTag rules with no Semgrep account,
  token, remote rule download, or result upload; and
- link to `.semgrep/README.md` for authoring rules.

Do not describe Semgrep as dependency, secrets, interfile, or complete security
coverage.

- [ ] **Step 4: Update architecture verification language**

In `docs/architecture.md`, extend the existing backend CI validation paragraph
to list deterministic TailTag-owned Semgrep CE analysis after strict Pyright
and before PostgreSQL-backed pytest. Preserve the single `make api-check`
local/CI contract and the relevance-classifier description.

- [ ] **Step 5: Verify docs and commit**

Run:

```bash
uv --directory services/api run pytest -q tests/test_runtime_commands.py
./scripts/doctor.sh
git diff --check
```

Expected: runtime-command contract passes, doctor passes (a missing Dev
Container CLI remains only the repository's established warning), and the diff
is clean.

Commit:

```bash
git add .semgrep/README.md services/api/README.md docs/architecture.md
git commit -m "docs: explain deterministic Semgrep validation"
```

---

### Task 4: Run whole-change verification

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: all prior task commits.
- Produces: fresh deterministic completion evidence for review.

- [ ] **Step 1: Run the Semgrep gate independently**

```bash
make api-semgrep-check
```

Expected: rule tests pass, repository scan has zero findings, and exit status is
zero.

- [ ] **Step 2: Run the authoritative backend gate**

```bash
make api-check
```

Expected: Ruff format/lint, strict Pyright, Semgrep, PostgreSQL pytest, Django
checks, migration drift, schema validation, and Gunicorn configuration all pass.

- [ ] **Step 3: Run repository completion checks**

```bash
./scripts/doctor.sh
git diff --check main...HEAD
git status --short
```

Expected: doctor passes with only its established optional Dev Container CLI
warning, the diff check is clean, and the worktree has no uncommitted files.

- [ ] **Step 4: Record limitations for handoff**

The completion report must state:

- Semgrep CE uses only TailTag-owned local rules;
- there is no account/token/result upload;
- there is no dependency, secret, SARIF, or Semgrep AppSec coverage;
- no application/runtime/database/migration behavior changed; and
- the initial repository scan is clean without suppressions.
