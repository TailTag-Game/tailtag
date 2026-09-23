# #207 preflight failure and recovery

The first live attempt stopped at `PREFLIGHT`, before source identity capture,
Railway tunnel creation, or any dump or restore. Its fixed sanitized outcome is
retained in `2026-09-22-issue-207-preflight-failure.json`.

**Cause classification: operator/environment error.** The operator launched
`scripts/api_staging_restore_drill.py` as a file with `PYTHONPATH=services/api`.
That launch omits the repository root from Python's module search path. A
same-form offline probe confirmed that `scripts` cannot be imported. The drill's
first public preflight call imports `scripts.api_staging_preflight`; the launch
therefore failed locally before an HTTP request. Railway HTTP logs showed no
health request in the failure window. This was not a #203 gate or Staging service
defect. No #203 code or acceptance rule was changed.

The corrective action was to use the existing documented module invocation,
`make api-staging-restore-drill`, which supplies the repository root and API path.
Before that run, the unchanged canonical preflight passed four times over 45
seconds with an identical identity. The serving revision matched the reviewed
schema revision; the approved deployment join and canonical API-to-Postgres
service/volume relationship passed. No service or configuration change was
needed. After the drill, the canonical preflight, deployment identity, and
database relationship still matched the recorded before-state.

The fresh run's complete GO evidence is in
`2026-09-22-issue-207-restore.json`. It used a real custom-format Staging dump,
isolated PostgreSQL 18 restore, the named integrity and read-only Django checks,
and verified cleanup. Its session, credential, and Catch representative reads
are `NOT_EXERCISED` because those source tables were empty at the captured
recovery point; their schema, constraints, and relationship checks passed.
