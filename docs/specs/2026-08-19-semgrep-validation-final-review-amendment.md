# Deterministic Semgrep validation — final-review amendment

## Status and authority

This is the approved remediation contract resulting from final review of
`2026-08-19-semgrep-validation.md`. It supersedes that specification's
conflicting implementation details, including its backend-development
dependency placement and narrower explicit scan-target description. The
original objective and all original non-goals remain in force unless this
amendment expressly refines their implementation boundary.

Final-review evidence established that the initial implementation could affect
the API dependency resolution, did not make the complete effective scan scope
independently observable, and needed stronger fixture validation and inherited
baseline resistance. The following decisions freeze the remediation scope.

## Frozen decisions

### Dependency isolation and command contract

- Semgrep CE `1.173.0` moves to a separate non-package project:
  `.semgrep/pyproject.toml`, `.semgrep/uv.lock`, and ignored
  `.semgrep/.venv`. Semgrep is invoked and synchronized through
  `uv --directory .semgrep`.
- Remove Semgrep from `services/api/pyproject.toml` and
  `services/api/uv.lock`. Restore the API runtime resolution, including
  `jsonschema`, so production dependency output is unchanged from `main`.
- For one-time branch-completion evidence, compare the API dependency baseline
  with immutable commit `ede15f13bbde767f4816ffdb4f3b966d357ec78d`:
  `services/api/uv.lock` must be byte-identical, and parsed
  `[project].dependencies` plus `[dependency-groups]` in
  `services/api/pyproject.toml` must be equal. Unrelated tool configuration,
  such as Pyright includes, may differ. The current locked no-dev dependency
  tree or export must contain no Semgrep. This is not a permanent future
  dependency freeze.
- `make api-setup`, CI dependency setup, and devcontainer setup synchronize
  both locked projects. `make api-check` remains no-sync.
- GitHub Actions still executes exactly one validation command,
  `make api-check`; no Semgrep-specific action, account, token, secret,
  permission, remote policy, or result upload is introduced.

### Effective scan scope and relevance

- Check in root `.semgrepignore` as the complete repository-owned Semgrep
  ignore policy. It must not exclude tests.
- The main scan must effectively include every tracked `.py` file under
  `services/api/` and exactly these explicit root helper targets:
  `scripts/api_smoke.py`, `scripts/api_auth_smoke.py`,
  `scripts/clerk_development_session.py`,
  `scripts/backend_ci_relevance.py`, and the new stdlib-only
  `scripts/validate_semgrep_contract.py`. No other target drift is allowed.
- Add a deterministic black-box test that compares Semgrep JSON
  `paths.scanned` with the exact Git-tracked expected set. This is the
  acceptance evidence for effective scope. The test must exercise the
  canonical main-scan configuration and shared command construction, while
  freezing the expected helper set independently; it must not reconstruct
  targets from implementation operands alone.
- `.semgrep/`, root `.semgrepignore`, every explicit root scan or validator
  helper, the Makefile, and the API workflow are backend-relevant. Existing
  unrelated-path classification remains unchanged.

### Fail-closed rule fixtures

Before `semgrep scan --test`, run
`scripts/validate_semgrep_contract.py` using the locked, no-sync API Python.
The validator must fail nonzero for any filesystem or I/O error and when any
of these are invalid:

- zero rule or fixture files;
- rule YAML and fixture basename pairing;
- unsupported files or extensions in the rule or fixture directories;
- duplicate, ambiguous, or noncanonical rule-ID declarations;
- unknown or malformed fixture annotations; or
- a rule without at least one `ruleid` and one `ok` annotation.

Empty, mismatched, and partial fixtures must therefore fail before the actual
Semgrep fixture scan. `semgrep scan --test` remains required after successful
validator execution and remains responsible for complete YAML and pattern
validity; the validator does not replace Semgrep's fixture test.

### Deterministic local execution

Both Semgrep commands use the separately locked executable and checked-in
local rules. Both disable metrics and version checks and explicitly pass
`--baseline-commit ''`, so an inherited `SEMGREP_BASELINE_COMMIT` cannot
suppress the full scan. Neither command may use remote configuration, a
Registry rule identifier, account/login/token access, network rule download,
or result upload.

The baseline-resistance acceptance test uses an isolated local clone or
worktree of the current branch. It shares or symlinks the already-synchronized
API and Semgrep environments, without network synchronization; commits an
approved-target Python file containing a known vulnerable fixture; sets
inherited `SEMGREP_BASELINE_COMMIT` to that commit/`HEAD`; and runs the actual
`make api-semgrep-check` with no command overrides. The command must fail
nonzero and report the expected TailTag rule ID. This proves the explicit
`--baseline-commit ''` behavior on the canonical full scan; a separately
reconstructed scan does not qualify.

### Rule precision and documented boundary

- Unsafe YAML negatives must keep
  `yaml.load(..., Loader=yaml.SafeLoader)`, `yaml.CSafeLoader`, and their
  directly imported aliases unreported. Unsafe `yaml.load` without one of
  those exact safe loaders remains detected.
- Raw-SQL positive fixtures must detect direct interpolated f-string, `%`, and
  `.format(...)` query expressions passed to `execute` for `cursor`, any
  identifier ending `_cursor`, `connection`, `conn`, `db`, and `self.cursor`.
  They must also detect direct interpolated f-string calls through
  `connection.cursor().execute(...)` and
  `self.connection.cursor().execute(...)`, a same-lexical-block
  `query = f"...{user_input}..."` followed by `cursor.execute(query)` (and
  supported receiver equivalents where the implementation can share that
  constraint), Django `$MODEL.objects.raw(f"...{value}...")`, and imported or
  qualified Django `RawSQL(f"...{value}...", ...)`.
- Raw-SQL negative fixtures must include unrelated `Writer.execute` and
  `writer.execute`, an unapproved receiver such as `executor.execute`, a
  constant f-string or statically assigned query, and a parameterized cursor
  query.
- Documentation must state the deliberately syntax-local, high-confidence
  direct/same-block-flow receiver boundary. Arbitrary aliases, interprocedural
  flow, and concatenation outside supported shapes are limitations, not
  claimed coverage.

### Tests first and documentation follow-up

Independent acceptance and regression tests must be RED before remediation
implementation begins. Parsing and validation logic requires strong
invalid-case tests, including mutation-style scenarios; this does not add a
new mutation-testing framework.

After implementation, update command, setup, effective-scope, and limitation
documentation. The work still excludes SCA, dependency vulnerability scanning,
secret scanning, SARIF, AppSec Platform integration, and changes to runtime,
API, database, deployment, or product behavior.

## Final acceptance evidence

Completion requires all of the following fresh evidence:

1. The standalone online/offline gate discovers rule tests and produces zero
   findings on the approved scope.
2. The isolated-worktree inherited-baseline probe runs the actual canonical
   target and still detects its planted target with the expected rule ID.
3. The exact scanned-set assertion uses the canonical main-scan configuration,
   includes API tests, and freezes the helper set independently.
4. Both `uv` locks validate.
5. The immutable API dependency-baseline comparison passes, and the API
   production dependency tree contains no Semgrep or tooling-driven downgrade.
6. Full `make api-check`, `./scripts/doctor.sh`, and `git diff --check` pass
   with a clean working tree.
7. Fresh final specification, code, and security reviews each pass.

## Replan triggers

Return `NEEDS_CONTEXT` rather than continuing implementation if any of the
following occurs:

- a rule identifies a genuine repository finding;
- the API runtime resolution, including `jsonschema`, cannot be restored to
  its `main` behavior; or
- satisfying the remediation would require weakening the approved security
  scope.

These conditions require an explicit remediation, dependency, or scope
decision; they must not be hidden through suppression, baseline behavior, or
unreviewed rule relaxation.
