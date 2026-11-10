# Field-beta operator authorization and audit

This runbook covers the nine existing sensitive Django-admin actions for
field-beta operations. It is not an operator-management UI, an audit viewer, or
a product API. Do not run the Staging procedure or mutate Staging without
separate explicit authorization.
The [replacement #243 live-evidence record](../development/staging-operator-validation-243-execution-attempts.md)
records the current bounded Staging validation result and its four Case 9 live
limitations. The [#205 handoff](../development/staging-operator-validation-205.md)
is historical context for the retired-generation gap.

## Authority and inspection matrix

Every sensitive operation requires an authenticated staff user. `is_staff=True`
never authorizes or grants sensitive operations. `change_*`, `delete_*`, and
`view_*` are generic model permissions. Generic model permissions neither
substitute nor authorize sensitive operations, nor are they an additional
prerequisite for a sensitive operation. Generic model permissions never
substitute for or authorize sensitive operations. The listed operation
permission is independently sufficient for its action; it does not require
generic model permission. The Catch exception is intentional:
`catches.delete_catch` is Django's built-in model permission, preserved solely
as the explicit Catch correction authority. It is not a generic substitution
for other sensitive actions.

| Audit action | Target | Operation and inspection boundary |
| --- | --- | --- |
| `remove_catch` | `catches.catch` | `catches.delete_catch` is independently sufficient for this correction action; `catches.view_catch` or `catches.delete_catch` permits inspection. `catches.change_catch` is not required. |
| `revoke_catch_credential` | `conventions.fursuitcatchcredential` | `conventions.revoke_catch_credential` is independently sufficient for this action; `conventions.view_fursuitcatchcredential` or `conventions.revoke_catch_credential` permits inspection. `conventions.change_fursuitcatchcredential` and `conventions.delete_fursuitcatchcredential` are not required. |
| `terminate_catch_session` | `conventions.fursuitcatchsession` | `conventions.terminate_catch_session` is independently sufficient for this action; `conventions.view_fursuitcatchsession` or `conventions.terminate_catch_session` permits inspection. `conventions.change_fursuitcatchsession` and `conventions.delete_fursuitcatchsession` are not required. |
| `deactivate_fursuit_activation` | `conventions.fursuitactivation` | `conventions.deactivate_fursuit_activation` is independently sufficient for this action; `conventions.view_fursuitactivation` or `conventions.deactivate_fursuit_activation` permits inspection. `conventions.change_fursuitactivation` and `conventions.delete_fursuitactivation` are not required. |
| `remove_convention_enrollment` | `conventions.conventionenrollment` | `conventions.remove_convention_enrollment` is independently sufficient for this action; normal explicit `conventions.view_conventionenrollment` is required for inspection, but generic permission is not required before executing the action. `conventions.change_conventionenrollment` and `conventions.delete_conventionenrollment` are not required. |
| `set_profile_enabled` | `profiles.playerprofile` | `profiles.set_profile_enabled` is independently sufficient for this action; normal explicit `profiles.view_playerprofile` is required for inspection, but generic permission is not required before executing the action. `profiles.change_playerprofile` and `profiles.delete_playerprofile` are not required. |
| `set_fursuit_enabled` | `fursuits.fursuit` | `fursuits.set_fursuit_enabled` is independently sufficient for this action; normal explicit `fursuits.view_fursuit` is required for inspection, but generic permission is not required before executing the action. `fursuits.change_fursuit` and `fursuits.delete_fursuit` are not required. |
| `set_convention_playability` | `conventions.convention` | `conventions.set_convention_playability` is independently sufficient for this action; normal explicit `conventions.view_convention` is required for inspection, but generic permission is not required before executing the action. `conventions.change_convention` and `conventions.delete_convention` are not required. |
| `revoke_fursuit_tag` | `fursuits.fursuittag` | `fursuits.revoke_fursuit_tag` is independently sufficient for this action. `fursuits.view_fursuittag` or `fursuits.revoke_fursuit_tag` permits inspection. `fursuits.change_fursuittag` and `fursuits.delete_fursuittag` are not required. The admin never shows a tag token or payload, and revocation creates no replacement. |

Normal `change_convention` still governs ordinary metadata corrections and
non-playable lifecycle changes; it does not cross the playability boundary.
Catch add/edit/bulk correction, credential replacement, session history edits,
activation/reactivation, enrollment creation/selection changes, playable
Convention creation/deletion, and other alternate gameplay-authority paths
remain unavailable.

## Normal Staging operator provisioning

The normal Staging operator is `is_staff=True`, `is_superuser=False`, and has
the exact explicit permissions in the matrix plus their listed inspection
permissions. The normal operator uses explicit permissions for every sensitive
operation. The named `TailTag Field Beta Operators` group is assignment
convenience only: authorization/admin checks use explicit permissions, never a
group-name check. Provisioning does not create or make a normal operator a
superuser.

Render Staging provisions the normal operator through one launcher. Run it from
the repository root in your own terminal:

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_render_ssh.py managed-create
```

[Operator commands over render ssh](../development/staging.md#operator-commands-over-render-ssh)
describes the launcher checks and results. The launcher accepts only the pinned
Render Staging service `tailtag-api-stg`. It rejects a wrong or different
target, a non-TTY, and a confirmation other than
`bootstrap Render Staging operator`. The
[replacement #243 execution record](../development/staging-operator-validation-243-execution-attempts.md)
documents the bounded operator evidence from the Railway era.

At the hidden, not echoed input prompts, enter the dedicated operator identifier,
password, and password confirmation. Never put an identifier, password, or
credential in a command argument or environment variable, and never retain one
in shell history, logs, chat, tickets, or committed evidence.

The command creates an unused dedicated identity, or rotates the password only
for an existing exact managed staff/non-superuser identity with the sole named
group and exact permission set. It fails closed for an ordinary player,
superuser, ambiguous account, group collision, unavailable permissions, or
database failure, without manually elevating an account. Do not run it
automatically during build, pre-deploy, startup, health check, or Gunicorn.

#504 added `fursuits.revoke_fursuit_tag` and `fursuits.view_fursuittag` to the
exact permission set. An operator made before #504 holds the previous set. The
operator inspector then reports `FAIL_MANAGED_OPERATOR_UPGRADABLE`. In that
state, the other managed and emergency commands stop at their precondition.

To upgrade, run the same launcher with `managed-upgrade` instead of
`managed-create`, after the promotion that carries #504:

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_render_ssh.py managed-upgrade
```

Enter the same confirmation phrase as for `managed-create`, the existing
operator identifier, and a new password twice. The command adds the two permissions,
sets the new password, and prints `Staging operator reconciled and upgraded.`
The launcher then requires the inspector result `PASS`. Any other permission
set fails closed with `FAIL_MANAGED_OPERATOR_PERMISSION`.

## Emergency superuser

A superuser is the emergency-only break-glass path, not the normal operator
role. Django's normal superuser bypass permits the sensitive operation, and the
durable audit record labels every such attempt
`actor_class=emergency_superuser`. This runbook adds no justification field or
break-glass account-management workflow.

## Durable audit evidence

`OperatorAuditEvent` is the authoritative durable database audit record. Its
closed minimum audit record schema fields are stable event ID, action, actor
application/Django user ID, actor class, affected record type, affected record
ID, outcome, and timestamp. There is no audit viewer; audit rows are inspected
only through approved database or operator procedures.

`succeeded` means the requested state transition committed with its audit row.
`denied` means an authenticated staff actor lacked the required permission.
`rejected` means an authorized actor requested an invalid current state or
domain-contract transition. `failed` means an unexpected failure occurred and
the requested transition did not commit. A lifecycle cascade records exactly one
top-level operator action, not separate operator intent for each consequence.

Django `LogEntry` is not authoritative, and structured application or platform
logs are not authoritative. OperatorAuditEvent audit records contain only the
closed allowed fields. They must not include secrets, credentials, tokens, Clerk
identifiers, provider identifiers, emails, QR payloads, private URLs, raw
request bodies, broad object snapshots, broad permission snapshots, broad group
snapshots, or exception detail.

Audit rows retain under normal application-data durability expectations: no
automatic V0 expiry applies, and retain them until a future documented retention
policy explicitly purges them. #204 may restore/reset disposable domain records,
but does not delete audit evidence. A catastrophic database failure can prevent
both the attempted work and a follow-up failure event; do not substitute log
retention for this database-backed contract.
