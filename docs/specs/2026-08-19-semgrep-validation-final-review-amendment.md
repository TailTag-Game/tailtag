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
- `make api-setup`, CI dependency setup, and devcontainer setup synchronize
  both locked projects. `make api-check` remains no-sync.
- GitHub Actions still executes exactly one validation command,
  `make api-check`; no Semgrep-specific action, account, token, secret,
  permission, remote policy, or result upload is introduced.

### Effective scan scope and relevance

- Check in root `.semgrepignore` as the complete repository-owned Semgrep
  ignore policy. It must not exclude tests.
- The main scan must effectively include every tracked `.py` file under
  `services/api/` and every explicit root helper target, including the new
  stdlib-only `scripts/validate_semgrep_contract.py`.
- Add a deterministic black-box test that compares Semgrep JSON
  `paths.scanned` with the exact Git-tracked expected set. This is the
  acceptance evidence for effective scope, rather than an assertion about
  command-line operands alone.
- `.semgrep/`, root `.semgrepignore`, every explicit root scan or validator
  helper, the Makefile, and the API workflow are backend-relevant. Existing
  unrelated-path classification remains unchanged.

### Fail-closed rule fixtures

Before `semgrep scan --test`, run
`scripts/validate_semgrep_contract.py` using the locked, no-sync API Python.
The validator must fail nonzero when any of these are invalid:

- rule YAML and fixture basename pairing;
- duplicate rule IDs;
- unknown fixture annotations; or
- a rule without at least one `ruleid` and one `ok` annotation.

Empty, mismatched, and partial fixtures must therefore fail before the actual
Semgrep fixture scan. `semgrep scan --test` remains required after successful
validator execution; the validator does not replace Semgrep's fixture test.

### Deterministic local execution

Both Semgrep commands use the separately locked executable and checked-in
local rules. Both disable metrics and version checks and explicitly pass
`--baseline-commit ''`, so an inherited `SEMGREP_BASELINE_COMMIT` cannot
suppress the full scan. Neither command may use remote configuration, a
Registry rule identifier, account/login/token access, network rule download,
or result upload.

### Rule precision and documented boundary

- The unsafe-YAML rule must allow `yaml.SafeLoader` and `yaml.CSafeLoader`
  forms.
- The dynamic raw-SQL rule and fixtures must cover supported connection and
  cursor receiver forms, including a same-block variable-mediated dynamic
  query.
- Documentation must state the deliberately syntax-local, high-confidence
  receiver boundary. It must not claim comprehensive SQL data-flow or
  interprocedural analysis.

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
2. An inherited-baseline probe still detects a planted scan target.
3. The exact scanned-set assertion includes API tests.
4. Both `uv` locks validate.
5. The API production dependency tree contains no Semgrep or tooling-driven
   downgrade and matches `main`'s production dependency output.
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
