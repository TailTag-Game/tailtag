# TailTag Semgrep rules

This directory contains the local, blocking Semgrep Community Edition rules
owned and reviewed by TailTag. It contains no copied or vendored Registry or
other upstream rules. Rule IDs use the stable
`tailtag.<area>.<behavior>` naming convention.

Every rule must have both `ruleid` and `ok` fixtures before it can join the
blocking suite. Keep the rule and its paired fixtures together: the current
layout is `.semgrep/rules/tailtag-security.yml` and
`.semgrep/tests/tailtag-security.py`. Do not introduce a `.local.py` fixture;
the supported fixture file is `tailtag-security.py`.

## Run and maintain the gate

First synchronize the locked development dependencies, then run the canonical
gate from the repository root:

```bash
make api-setup
make api-semgrep-check
```

The command first verifies every fixture, then runs one blocking scan using
only the checked-in TailTag rules. Its scan targets are all tracked Python code
under `services/api/` (including application code, migrations, and tests),
plus `scripts/api_smoke.py`, `scripts/api_auth_smoke.py`,
`scripts/clerk_development_session.py`, and
`scripts/backend_ci_relevance.py`. It does not scan ignored virtual
environments, caches, local `.env` files, documentation, historical material,
mobile code, or unrelated repository automation.

This is deliberately local and deterministic: Semgrep account access, login,
tokens, Registry rules, remote configuration/downloads, result upload, usage
metrics, and version checks are forbidden. A finding, invalid rule, or scanner
failure fails the target. If a high-confidence new rule finds genuine existing
code, stop the tooling change and surface it for an explicit remediation or
scope decision; do not hide it with a blanket suppression, baseline, or a
weakened rule.

## Coverage boundary

The rule pack is a narrow, additional guard. It is not comprehensive security
coverage, interfile analysis, dependency/SCA scanning, or secret scanning, and
it does not replace threat modeling or code review.
