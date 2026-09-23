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
