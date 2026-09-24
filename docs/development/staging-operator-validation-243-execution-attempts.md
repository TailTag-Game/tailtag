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

## Read-only attempt: 2026-09-23 23:41:54.260518–23:42:00.810085 UTC

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

## Substantiated precondition result: 2026-09-23 23:46:56.246313–23:47:02.191628 UTC

**Overall: `LIMITED_OPERATOR_REMEDIATION_REQUIRED`; #243 remains blocked
before mutation.** The reviewed launcher at `9d4e420` executed once under
the bounded autonomous authorization. Its sanitized receipt established:

| Fact | Result |
| --- | --- |
| Environment | `staging` |
| Source SHA | `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` |
| Deployment ID | `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Approved identities, fresh/repeated public preflight, receipt and sole running-instance selection | `PASS` |
| Exact-instance build/runtime identity agreement | `PASS` (`target_verified=true`) |
| Phase | `exact_instance_inspector` |
| Inspector result | `FAIL_LIMITED_OPERATOR_MISSING` |
| Bounded fixture prerequisite | `PASS` (the inspector reached both role checks) |
| Managed operator | `PASS` for the exact frozen managed group, staff/non-superuser, credential shape, direct-permission and group-permission contract |
| Limited operator | `MISSING` through the approved independent candidate lookup |

The inspector returns at the first failed guard. Reaching the limited-role
lookup therefore supports the preceding fixture and managed-role results.
`MISSING` means no candidate was found outside the managed group with either
of the two approved profile permissions. It does **not** distinguish a
nonexistent underlying User from an existing identity without those
permissions, and does not justify guessing an identity or granting access.
No identity values, role memberships or permission snapshots were retained.

This fixture result covers only the inspector's maintained baseline/structure
checks. It does not replace the earlier 17-invariant fixture observations or
refresh the separate private-config/registry/database reconciliation.

### Nine-case disposition

| #205 case | Result | Supported limitation |
| --- | --- | --- |
| 1. Ordinary-player denial | `NOT_EXERCISED` | Live matrix stopped at missing limited-role prerequisite |
| 2. Staff-without-target-permission denial | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 3. Permitted non-superuser success | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 4. Cross-permission denial | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 5. Emergency-superuser success/classification | `NOT_EXERCISED` | Matrix not started; emergency identity not inspected in this attempt |
| 6. Exactly one successful top-level audit event | `NOT_EXERCISED` | No successful action submitted |
| 7. Exactly one denied-submission audit event | `NOT_EXERCISED` | No denied action submitted |
| 8. Representative cascade/top-level intent | `NOT_EXERCISED` | No cascade action or session preparation performed |
| 9. Forbidden alternate authority paths | `NOT_EXERCISED` | Finite matrix checks not started |

Success/denial audit outcomes, emergency-superuser classification, cascade
behavior, forbidden paths, and #204 reset/audit-retention interaction are
unsubstantiated by this attempt. No reset, operator provisioning, credential
change, fixture preparation, audit-row creation or Staging mutation occurred.
The read-only process exited; no remote source files were written and no
restoration was required. No additional live call followed this result.

### Required decision and repair boundary

The approved plan explicitly stops when the separate limited role is
unavailable and requires a separately reviewed fixture plan. The existing
`bootstrap_staging_operator` establishes the full managed permission set;
it cannot supply this one-action role unchanged. Reusing that managed actor,
stripping its authority, elevating a player or manually granting permissions
would cross the approved boundary.

The smallest next task is to approve a guarded provisioning/fixture plan for
a **separate** staff, non-superuser identity with only
`profiles.set_profile_enabled` and `profiles.view_playerprofile`, including
its credential-handling and cleanup boundary. Provisioning would mutate
Staging and needs explicit authorization after that plan is reviewable.
No such provisioning was implemented or executed in this task.

[#243](https://github.com/TailTag-Game/tailtag/issues/243) remains the owner of
this missing live evidence and its precondition handoff. #208 OR-6 remains
`BLOCKING` and #208 remains open at NO-GO. #205's historical closure, #207's
restore evidence and #241's non-blocking limitation are unchanged.

Local test cleanup: the task's disposable PostgreSQL container was stopped
and removed, with no task container or custom network left running. The
initial anonymous test volume was preserved under the repository's data
preservation policy; the final test container used temporary memory storage.

Final independent evidence review passed with no material finding. The
record preserves both failed attempts, the supported role result and the
unexercised matrix boundary. Local documentation links and diff checks passed.


## Repository-only feasibility stop — 2026-09-24 00:31 UTC

Classification: `BLOCKED_BEFORE_MUTATION` / `PLAN_CONTRACT_GAP`.
This is a local planning/review result, not an authenticated Staging attempt.
No fresh target tuple was established; the earlier observations above remain
point-in-time historical evidence. Cases 1–9 remain `NOT_EXERCISED`.

The maintainer authorized a narrow limited-role provisioning path and then
approved mixed evidence for absent Catch/credential object-level case-9
checks. That amendment expressly excludes other missing live proof.
Independent acceptance review found another unresolved boundary:

- The frozen #204 baseline has active FursuitActivation records.
- The approved profile and fursuit disables terminate sessions/revoke existing
  credentials, but do not make those activation records inactive.
- The real activation admin form exposes an editable, checked `is_active`
  checkbox on the active owned record. An active-to-active submission does
  not exercise the inactive-to-active rejection in `save_model`.
- Local deterministic tests and exact-deployment control review can support
  that rejection, but cannot replace its missing live proof under the current
  plan's Catch/credential-only exception. Calling this subcheck live `PASS`
  or merely calling its control unavailable would overstate the evidence.

Accordingly, no limited operator was provisioned and no live matrix started.
No authenticated Staging call, reset, fixture change, operator change, audit
write or other Staging mutation occurred during this repository work.
No Staging restoration is required by this work; current live state was not
reinspected. Prior fixture, registry and operator observations are unchanged.

The smallest decision is an explicit evidence-mode amendment for activation
reactivation: retain its live empirical result `NOT_EXERCISED`, separately
record the observed active form/control, exact-deployed-code review and
existing deterministic inactive-to-active denial tests, and disclose the
limitation in any satisfied case-level result. This would authorize no new
fixture, deactivation/reactivation transition or gameplay object. Without
that amendment, case 9 remains incomplete; no final #243 PASS is available.
No such amendment is inferred or applied by this record.

Local work remains in progress on the isolated #243 branch. The limited-role
command (53 focused tests), active-role inspector (44 focused tests) and
interactive lifecycle transport (41 focused tests) passed their bounded
reviews. Matrix executor/launcher tests are unfinished acceptance work with
production entry points absent; their expected red state is not a completed
repository gate. The proposed exact decommission proof also remains pending.
No final full-suite, execution or evidence approval is claimed.

#243 remains open and #208 remains NO-GO / OR-6 `BLOCKING`. #205's historical
closure, #207's restore GO and #241's non-blocking limitation remain unchanged.

Local cleanup after this stop: the task-owned temporary-memory PostgreSQL
container `tailtag-243-limited-tests` was stopped and removed. A subsequent
container listing confirmed it absent. No unrelated containers, persistent
volumes or reusable images were removed.
