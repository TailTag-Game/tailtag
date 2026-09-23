# #243 read-only operator execution attempts

These records preserve the chronological pre-mutation evidence. They do not
substantiate any of the nine #205 live matrix cases.

## Stopped attempt: 2026-09-23 23:27:33–23:27:40 UTC

- Retained result: `FAIL_EXECUTION_OR_TARGET`.
- Phase: `exact_instance_inspector`.
- Approved GitHub/Railway identity, fresh canonical public preflight, approved
  deployment receipt and exact running-instance selection passed beforehand.
- The fresh public source/deployment tuple was checked internally but was not
  retained in the failure output. The earlier tuple must not be substituted.
- The execution did not return an accepted inspector classification. Raw
  stdout/stderr were not retained. Transport, startup and output-contract
  failure cannot be distinguished from this record.
- Managed and limited operator state: unknown. Neither a role `PASS` nor a
  role mismatch can be inferred.
- Matrix cases 1–9: `NOT_EXERCISED`; reset/provisioning: not invoked;
  Staging mutation: none. No retry occurred in that attempt.
- No restoration was needed because no mutation began. No fresh fixture or
  operator final-state assertion is supported.

## Subsequent local diagnosis

Streaming the inspector with `python -` at filesystem root reproducibly raises
`IndexError` in the module-level repository-path calculation before the
sanitized guard. Streaming the same source from a nested working directory
returns the intended fixed invalid-input classification. This is a proven
startup defect and a missing execution-mode regression; the retained prior
attempt does **not** prove its remote working directory or root cause.

The correction makes stdin startup independent of directory depth. A bounded
runner uses the established isolated-Python transport pattern, explicitly
sets the application import root, validates exact-instance identity before
ORM inspection and enforces a PostgreSQL read-only transaction. Its fixed
execution phases and strict output schema preserve failure categories and
any established public tuple without retaining raw diagnostics. Managed and
limited role contracts are unchanged. Local tests cannot establish live
operator state.

## Local correction verification

Before a new live attempt, the startup regression and runner acceptance tests
passed, as did 330 focused #204/#205/#243 tests. The final `make api-check`
passed all 2,213 tests, formatting, lint, strict types, Semgrep, Django checks,
migration-drift check, schema validation and Gunicorn configuration. Explicit
Ruff/Pyright and Semgrep checks also covered the new launcher; Semgrep found
no findings. Doctor, local documentation links and diff checks passed.

Independent review found and resolved a fail-closed CLI exit-status defect:
non-`PASS` receipts now exit nonzero, with a regression proving the behavior.
The final review found no material issue and approved bounded read-only use.
These are local verification facts, not live #205 acceptance evidence.

## Read-only attempt: 2026-09-23 23:41:54–23:42:01 UTC

The reviewed launcher at `3d87bad` made one newly preflighted attempt:

| Fact | Observed result |
| --- | --- |
| Public environment | `staging` |
| Public source SHA | `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` |
| Public deployment ID | `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Identity, public preflight, approved receipt, running-instance selection | Passed before SSH |
| Launcher result / phase | `FAIL_TRANSPORT` / `exact_instance_inspector` |
| Accepted exact-instance verification | Not established by the retained result |
| Managed / limited roles | Unknown / unknown |
| Cases 1–9 | `NOT_EXERCISED` |
| Reset / provisioning / Staging mutation | None |

The raw transport streams were discarded. This classification alone cannot
establish whether the remote inspector ran or which role state it observed.
The submitted program contained only target checks and read-only inspection;
no mutation sequence started and no restoration was needed. No final live
operator-state assertion is supported.

### Subsequent transport-contract diagnosis

Railway CLI version `5.57.2` writes a key-selection announcement to stderr
even when an already registered key is selected successfully. This is
explicit in the [version-pinned upstream implementation](https://github.com/railwayapp/cli/blob/v5.57.2/src/commands/ssh/native.rs#L128-L139).
The launcher incorrectly required completely empty stderr. Local tests can
therefore reproduce rejection of a valid, target-verified inspector receipt
accompanied by this normal notice. The retained attempt does not prove that
this was its sole failure, and no historical role result can be recovered
from discarded output.

The bounded correction recognizes only that documented one-line notice and
never retains its identity/path payload. A nonzero transport exit, any other
stderr, extra stdout or invalid inspector receipt still fails closed. This
does not change identity selection, credentials, target guards or role rules.

The notice correction passed 58 focused inspector tests and the full
`make api-check` gate (2,220 tests). Explicit launcher Ruff/Pyright and
Semgrep checks, doctor, local documentation links and diff checks passed.
Independent review approved the narrow exception with no material finding.
It authorizes no inference about the discarded prior remote result.
