# #243 bounded validation: stopped pre-mutation inspection

**Outcome: `BLOCKED_BEFORE_MUTATION`.** This is a failure record for the
approved attempt against the [#243 plan](staging-operator-validation-243-plan.md),
not a result for any of the nine #205 matrix cases. The attempt occurred on
2026-09-23 after the `c4a450c` plan commit and before this diagnosis. Exact
start and end times were not retained.

| Retained observation | Sanitized result |
| --- | --- |
| Canonical credential-free preflight | PASS: healthy `staging` identity; source `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`; deployment `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Approved deployment correlation | PASS: the approved deployment receipt and exact running Railway instance returned the same source/deployment/environment tuple |
| Failed guard phase | Read-only combined synthetic-fixture and operator/permission inspection, before any matrix action |
| Retained failure class/message | Inspector emitted `FAIL readonly fixture/role inspection` and exited nonzero after suppressing the underlying exception |
| Authenticated access | Exact-instance deployment readback had passed; the inspector ran remotely and emitted its own failure sentinel. No access failure was observed, but this does not establish the fixture or role state. |
| Matrix cases 1–9 | `NOT_EXERCISED` in this attempt; no case-level PASS or FAIL is inferred |
| #204 reset | Not invoked |
| Staging mutation | None: only preflight, deployment readback and the read-only inspection command ran |
| Cleanup/final state | The inspection process exited. It created no intended remote files, containers or fixtures. Post-failure readiness, fixture state and operator state were not checked and remain unknown. |

## Local diagnosis

The one-off inspection command used
`User.objects.filter(is_staff=True, is_superuser=False, is_active=True)` for
the proposed limited operator and an analogous superuser query. TailTag's
`accounts.User` maps `is_staff` and `is_superuser`, but does **not** map
`is_active` as a database field. Django's inherited `User.is_active=True` is
a class attribute. A disposable local Django setup reproduced a `FieldError`
from the query without opening a database connection. Therefore this command
contains a deterministic **inspection-tool defect**. The remote command's
generic catch also covered earlier registry/profile/fursuit reads, so the
retained remote message does not prove which exception occurred there. Actual
Staging fixtures and operator permissions remain **INDETERMINATE**.

The command checked sensitive `profiles.set_profile_enabled` and
`fursuits.set_fursuit_enabled` permissions and normal profile inspection; it
did not rely on generic `change_*` or `delete_*` authority. Its role target was
the plan's **one-action limited operator**, not the documented managed normal
operator. The documented managed-operator shape is staff, not superuser,
belongs to the sole named managed group, has no direct permissions, and
receives the exact full set of sensitive and inspection permissions. In
particular, that shape has **both** profile and fursuit action permissions.
The approved bootstrap command cannot
establish the plan's one-action limited role; it creates the full managed role
or rotates an already exact managed role's password. No Staging role shape was
observed in the failed inspection, and no bootstrap or permission change is
proposed from this evidence.

The #204 registry preserves two designated non-staff Users and explicitly
registered Convention/Fursuit roots. Its reset restores the small domain
baseline and preserves Users and admin permissions; it does not promise a
one-action limited operator or a pre-existing catch session. The plan already
requires a separate safe session-start check for cascade proof and stops if
the required fixture is unavailable. The failed command yielded no fixture
result. #204 reset cannot be justified by this failure.

Existing deterministic #205 tests cover bootstrap's full managed permission
set, refusal of ambiguous identities, and permission/audit behavior. They do
not exercise this one-off inspection command or distinguish its exception
from a live Staging precondition failure. The local model/query reproduction
does distinguish the command defect without claiming live state.

## One remediation path: correct the inspection tooling

Before any new authenticated Staging task, replace the one-off read-only
inspector with a small repository-reviewed guard that:

1. Removes `is_active=True` from ORM filters for `accounts.User`; if an active
   account condition is needed, evaluates the model's documented attribute
   after retrieval. It must not add a new User field or alter authentication.
2. Reports separate allowlisted booleans for the #204 owned baseline, audit
   availability, the exact managed normal-operator shape, the plan's distinct
   one-action limited role, and an emergency superuser. It must not infer that
   the full managed operator satisfies the limited role. It emits no identity,
   raw ID, credential, row value or broad permission snapshot.
3. Classifies registry/fixture, role/permission, audit-access and inspector
   execution failures separately while preserving fail-closed exit behavior.
   Unexpected exceptions remain sanitized but cannot silently become a
   fixture or permission verdict.

The smallest tests use disposable local Django data to reject an unmapped
`is_active` filter, accept the exact managed shape, distinguish full managed
and one-action limited roles, and verify sanitized failure classification.
They need no new production API or Staging deployment. Correcting the read-only
query and error reporting does not grant permissions, change fixtures or weaken
any pre-mutation guard. A new **separately authorized authenticated read-only**
task must then run the corrected guard once against the exact canonical
deployment. That observation may reveal a role or fixture precondition failure;
do not assume one now. The nine-case validation, operator bootstrap, #204
reset, and all Staging mutations remain stopped pending that result and any
required revised approval.
