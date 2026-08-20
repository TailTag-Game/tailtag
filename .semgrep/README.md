# TailTag Semgrep rules

This directory contains the local, blocking Semgrep Community Edition rules
owned and reviewed by TailTag. It contains no copied or vendored Registry or
other upstream rules. Rule IDs use the stable
`tailtag.<area>.<behavior>` naming convention.

Every rule must have both `ruleid` and `ok` fixtures before it can join the
blocking suite. Keep each rule file and fixture file paired by basename: the
current layout is `.semgrep/rules/tailtag-security.yml` and
`.semgrep/tests/tailtag-security.py`. The preflight validator fails closed on
missing, ambiguous, malformed, unknown, or incomplete rule/fixture metadata;
Semgrep then validates the complete YAML and patterns with its fixture test.

## Run and maintain the gate

First synchronize the locked development dependencies, then run the canonical
gate from the repository root:

```bash
make api-setup
make api-semgrep-check
```

`make api-setup` synchronizes two locked projects: the API project at
`services/api/` and this separate, non-package Semgrep project. Its local
virtual environment, `.semgrep/.venv`, is intentionally ignored. After setup,
`make api-semgrep-check` is a locked, no-sync command: it first runs
`scripts/validate_semgrep_contract.py`, then Semgrep's fixture test, then the
blocking scan.

The blocking scan uses only checked-in TailTag rules and explicitly clears the
baseline (`--baseline-commit ''`), so an inherited
`SEMGREP_BASELINE_COMMIT` cannot suppress findings. Its effective scope is all
tracked Python under `services/api/`—including application code, migrations,
and tests—plus these five repository-root helpers:

- `scripts/api_smoke.py`
- `scripts/api_auth_smoke.py`
- `scripts/clerk_development_session.py`
- `scripts/backend_ci_relevance.py`
- `scripts/validate_semgrep_contract.py`

The root `.semgrepignore` is the complete repository-owned ignore policy. It
excludes virtual environments, caches, and generated dependencies, but not
tests. The gate does not scan documentation, historical material, mobile code,
or unrelated repository automation.

This is deliberately local and deterministic: Semgrep account access, login,
tokens, Registry rules, remote configuration/downloads, result upload, usage
metrics, and version checks are forbidden. A finding, invalid rule, or scanner
failure fails the target. If a high-confidence new rule finds genuine existing
code, stop the tooling change and surface it for an explicit remediation or
scope decision; do not hide it with a blanket suppression, baseline, or a
weakened rule.

## Coverage boundary

The rule pack is a narrow, additional guard. It is not comprehensive security
coverage, interfile analysis, dependency/SCA scanning, secret scanning, SARIF
output, or an AppSec-platform integration, and it does not replace threat
modeling or code review.

The unsafe-YAML rule recognizes only the actual `yaml.SafeLoader` and
`yaml.CSafeLoader` identities, including direct imports and aliases; other
`yaml.load` uses remain findings. The raw-SQL rule intentionally covers only
high-confidence syntax-local forms: approved direct receivers and direct
interpolated calls, plus the supported same-lexical-block query assignment
shape. It also covers the documented Django `RawSQL` spellings. It does not
claim coverage for arbitrary aliases, interprocedural flow, or concatenation
outside those supported shapes.
