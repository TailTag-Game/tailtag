# Deterministic Semgrep validation

## Status

Approved design for adding repository-owned Semgrep Community Edition checks
to TailTag's canonical backend verification contract.

## Objective

Add a deterministic, noninteractive Semgrep security-analysis gate that runs
the same way for contributors and GitHub Actions. TailTag owns and reviews the
rules that can block a change. The scan requires no Semgrep account, token,
remote rule download, or scan-time network access.

This is development and CI tooling only. It does not change application
runtime behavior, deployment configuration, database state, or product APIs.

## Design

### Tool ownership and dependency boundary

Semgrep Community Edition is a locked backend development dependency managed
by the existing `services/api/pyproject.toml` and `services/api/uv.lock`
workflow. The production Docker stage continues to install with `--no-dev`, so
the scanner and its transitive dependencies do not enter the deployed API
image.

The lockfile is the authoritative resolved engine version. Updating the engine
or its transitive dependencies is an explicit reviewed lockfile change.

### Repository-owned rules

All blocking rules are authored for TailTag and checked into `.semgrep/rules/`.
They must not copy or vendor Semgrep Registry rules or other third-party rule
sets. This avoids mutable remote policy and third-party redistribution or
provenance ambiguity.

The initial high-confidence rule pack covers:

- dynamic Python execution through `eval` or `exec`;
- shell execution through `os.system` or `subprocess` with `shell=True`;
- unsafe Python deserialization through `pickle` or `marshal`;
- unsafe YAML loading without a safe loader;
- disabled TLS certificate verification in supported HTTP client call shapes;
- Django `mark_safe` use;
- dynamically constructed SQL passed to Django/raw database execution APIs;
- public S3-compatible object ACLs; and
- presigned upload operations such as `put_object`.

Every rule has positive and negative fixtures under `.semgrep/tests/`. A rule
cannot join the blocking suite without a fixture proving both a vulnerable
shape it catches and a nearby safe shape it permits. Rule identifiers use the
stable `tailtag.<area>.<behavior>` namespace.

The starter pack is deliberately narrow. New rule families are separate,
reviewed changes with their own fixtures. Semgrep is an additional
deterministic guard, not a claim of complete security coverage and not a
replacement for threat modeling, code review, or dependency vulnerability
analysis.

### Scan command and scope

The root Makefile exposes `make api-semgrep-check`. It first runs the custom
rule fixtures, then scans tracked Python code in:

- `services/api/`, including application code, migrations, and tests; and
- `scripts/api_smoke.py`, `scripts/api_auth_smoke.py`,
  `scripts/clerk_development_session.py`, and
  `scripts/backend_ci_relevance.py`.

Git-ignored virtual environments, caches, local `.env` files, documentation,
historical material, mobile code, and unrelated repository automation are not
scan targets.

The scan uses only the checked-in local configuration. Findings are errors.
Usage metrics and version checks are disabled by both explicit CLI options and
environment configuration where supported. The command must not use
`--config auto`, a Registry identifier, `semgrep ci`, a remote URL, a login,
or a token.

The Make target is a prerequisite of `make api-check` and runs before the
PostgreSQL-backed test suite so the cheap static failure is reported first.

### CI integration

GitHub Actions continues to run exactly one canonical command:
`make api-check`. It does not gain a Semgrep-specific action, service, account,
secret, token, permission, or duplicated command.

The existing backend relevance classifier treats `.semgrep/` as a
backend-relevant prefix. A rules-only pull request therefore runs the backend
suite. Existing explicitly irrelevant paths remain irrelevant.

### Baseline and findings policy

The first blocking scan must be clean on `main`. Blanket suppressions,
repository-wide `nosemgrep` annotations, and a committed ignore-baseline file
are not permitted.

If a proposed high-confidence rule reports existing code:

1. determine whether the finding is genuine or a false positive;
2. refine the rule only when the reported shape is safe and the refinement
   preserves the intended vulnerable fixture;
3. if the finding is genuine, stop this tooling implementation and surface it
   for an explicit remediation/scope decision; and
4. never weaken or suppress the rule merely to make CI green.

Narrow inline suppression may be considered only in a future reviewed change
that documents why the exact instance is safe. No such suppression is part of
this work item.

### Documentation

The API contributor guide documents `make api-semgrep-check`, its local-rule
and no-network boundary, and Semgrep's place in `make api-check`. Architecture
documentation lists Semgrep among the canonical backend validation gates and
does not imply dependency or secret scanning coverage.

## Acceptance Contract

1. A fresh locked dependency sync supplies a Python 3.13-compatible Semgrep CE
   executable locally, in the development container, and in GitHub Actions.
2. The production Docker dependency installation remains `--no-dev` and does
   not contain Semgrep.
3. `make api-semgrep-check` tests every TailTag rule and performs one blocking
   scan of the approved targets using only checked-in rules.
4. A vulnerable fixture for every rule fails if its rule stops matching, while
   the paired safe fixture remains accepted.
5. A Semgrep finding makes the Make target fail; an invalid rule or scanner
   failure also makes it fail.
6. The scan sends no metrics, performs no version check, downloads no rules,
   prompts for no input, and requires no credential or account.
7. `make api-check` includes the Semgrep target before PostgreSQL-backed tests
   and retains every existing validation gate.
8. GitHub Actions still invokes only `make api-check`, with `contents: read`
   permission and no Semgrep-specific secret or action.
9. Changes under `.semgrep/` require backend validation; unrelated paths retain
   their current relevance behavior.
10. The initial scan of `main` is clean without blanket ignores, baseline
    suppression, or runtime-code changes hidden inside the tooling work item.
11. Contributor and architecture documentation accurately describe the new
    gate and its intentionally limited coverage.
12. The repository's authoritative `make api-check`, `./scripts/doctor.sh`,
    and `git diff --check` pass before completion.

## Non-goals

- Semgrep AppSec Platform, `semgrep ci`, login, policy management, dashboards,
  or cloud result upload.
- Remote or automatically selected Registry rules.
- Vendored third-party rules.
- SARIF upload or GitHub code-scanning integration.
- Secrets scanning, dependency vulnerability scanning, SCA, or replacement of
  a future `pip-audit`/OSV work item.
- Autofix rules, automatic suppressions, or a historical findings baseline.
- Scanning mobile code, documentation, archived POC material, generated files,
  ignored local files, or the virtual environment.
- Fixing unrelated application findings without an explicit scope decision.
- Changing application, database, deployment, or product behavior.

## Rollout and rollback

This lands as one independently reviewed tooling pull request from
`chore/semgrep-validation`. No external provisioning is required. Rollback is
the ordinary code rollback of the dependency, rules, Make target, classifier,
tests, and documentation; it does not mutate application or external state.

After this work lands, feature branches such as `feat/v0-media-storage` should
rebase onto it and pass the new Semgrep gate before their own pull requests are
opened or updated.
