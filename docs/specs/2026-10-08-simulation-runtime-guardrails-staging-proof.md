# Simulation runtime guardrails: Staging proof

AC25 passed on 2026-10-08. This is the final observed integration evidence for
[#227](https://github.com/TailTag-Game/tailtag/issues/227), supplementing the
[approved design](2026-10-08-simulation-runtime-guardrails.md) and
[implementation plan](2026-10-08-simulation-runtime-guardrails-implementation-plan.md).

## Source and authorization

All runs used clean simulator commit
`578ebc0a377549289a92efc59a37dacf0b9ca00e`, Python 3.13.14 and HTTPX 0.28.1.
The Staging identity stayed healthy and unchanged:

- Source: `e8aedd0d2b4e0e0787edf6bcafc7fbcbb95d4902`
- Deployment: `9359c0a2-4915-42cd-9994-521ce7bc740e`
- Environment: `staging`

The user explicitly approved two supervised runs with two identities, selected
`demo`, approved provisioning exactly two marked synthetic identities, then
separately approved one corrected normal retry. Clerk credentials were entered
only at hidden local Terminal prompts; credential input was never recorded.

## Bounds and actual outcomes

Baseline convention v2, seed 0, no injected effects: one casual attendee, one
normal owner, one fursuit, 30 seconds of scheduled traffic at 0.2 arrivals/second,
maximum six entries, one active actor/request, 100 workload attempts, and
15-second drain. Shared policy: 500 execution requests/600 seconds, two ordinary
requests plus one reserved control request, population two, and a single final
reserve of 100 requests/300 seconds.

| Run | Observed outcome | Recovery |
| --- | --- | --- |
| Original normal `40e9e9de-5d69-4f75-8c21-ba610d786b26` | Exit 1, failed; correctness passed 14 checks. The generation ceiling of 30 seconds included owner preparation and left 28.296 seconds for the 30-second schedule. No safety abort. | Bounded retention, session closure and release passed; exact named cleanup removed owned fixtures and readmitted both identities. |
| Operator stop `385ccbfb-daa9-41ff-a043-ba0ed6c570a9` | Exit 1, aborted; first cause `resource_saturation`. Exact PID verified; SIGUSR1 delivered during simulation after one actual completion while one ordinary request was in flight. | Reconciliation explicitly skipped; bounded retention, session closure and release passed. Exact named cleanup removed owned fixtures and readmitted both identities. |
| Approved normal retry `d7a67f2c-5d50-45e8-b4ad-3f7d98cb5df2` | Exit 0, passed; correctness passed 14 checks. Actual traffic generation 30.001 seconds, six offered, five admitted/completed, one skipped by actor bounds, 24 workload sends. No unresolved, transient, injected or exhausted work and no safety abort. | Automatic cleanup, Clerk session closure and lease release passed. No retained state or manual cleanup needed. |

Only the retry's narrower generation ceiling changed from 30 to 45 seconds to
allow preparation. Actual scheduled traffic and all other limits were unchanged.
No application change or report weakening was required.

The retry used 88 execution requests in 76.447 seconds and nine final requests in
5.827 seconds, within their separate ceilings. Ordinary/control concurrency peaks
were 1/1; all final active counts were zero. All 15 preflight checks and six
periodic probes passed. Cleanup acknowledged one convention, two enrollments,
one fursuit, activation, catch, session, credential and image. No unacknowledged
remote rollback is assumed.

## Validation and final state

All three schema 4 reports passed `make sim-report-validate REPORT=<absolute-path>`.
The local sanitized reports remain in `tools/simulator/reports/227-normal`,
`227-stop`, and `227-normal-retry`; reports are intentionally ignored by Git.
Their SHA-256 digests identify the exact validated artifacts:

| Run ID | Report SHA-256 |
| --- | --- |
| `40e9e9de-5d69-4f75-8c21-ba610d786b26` | `c41a474b43edc6dfed6b5e5d084a917b05c0bd6b5a59533c550a9053e671f667` |
| `385ccbfb-daa9-41ff-a043-ba0ed6c570a9` | `296547d306129f193cadb6a66dfd1a478bfaab1d432494cd8852a76022d5ab4d` |
| `d7a67f2c-5d50-45e8-b4ad-3f7d98cb5df2` | `4228027b9433cfcff32c059337383e7efbce374aaa8a93db4c90f9bca9e36e8c` |

Final guarded checks:

- `make sim-pool-status POOL=demo`: total 2, available 2, leased 0, quarantined 0.
- `make sim-retained`: retained 0, unfinished 0.
- All task processes exited and all four owned Terminal windows closed.
- Two reusable marked synthetic identities intentionally remain provisioned.
  No server, container, network or deployment was created for the live proof.

Code and test inputs remained unchanged after authoritative `make sim-check`
(1,100 tests, strict types, lint and Semgrep passed) and `make api-check`
(3,948 tests and canonical backend gates passed). Unit and whole-change independent
ADW reviews passed SPEC, QUALITY, TEST, SCOPE, SECURITY, DATA INTEGRITY and
RELIABILITY. Doctor required checks and diff/scope checks passed at the original
implementation gate. The publication-time doctor rerun could not pass its Docker
daemon prerequisite because the previously stopped engine had been restored to
stopped after testing; other required checks passed. No test/code inputs changed.

## Limits

Automatic resource monitoring is unavailable. The operator signal proves the
supervised stop mechanism; it does not demonstrate measured saturation. This
small integration proof makes no capacity, performance or SLO claim. Reports
truthfully preserve the original failed attempt and the aborted operator run.
No further retry, deployment or merge was performed. Normal cleanup and named
recovery were acknowledged; both identities and retained-run state were checked
through guarded commands after execution.
