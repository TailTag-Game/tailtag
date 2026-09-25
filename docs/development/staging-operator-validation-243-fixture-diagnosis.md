# #243 fixture-only read-only diagnosis

This diagnostic narrows the earlier `FAIL_FIXTURE_STATE_MISMATCH` result. That
earlier attempt remains `BLOCKED_BEFORE_MUTATION`; it did not reach operator
checks, matrix cases, or reset. The diagnostic reads only the registered #204
synthetic closure and designated asset. Its fixed classifications do not
authorize a reset or fixture preparation.
The [one bounded live fixture result](staging-operator-validation-243-fixture-result-2026-09-23.md)
found a preserved registry prerequisite mismatch; no remediation followed.

The approved [#243 plan](staging-operator-validation-243-plan.md) uses the
frozen [#204 manifest](../specs/2026-09-17-staging-synthetic-reset-reseed.md).
The ownership classes below determine whether a later, separately authorized
guarded #204 reset could restore a mismatch. A `PRESERVED_PREREQUISITE`
failure must not be treated as reset-owned.

| Diagnostic invariant | Ownership | Frozen contract boundary |
| --- | --- | --- |
| `registry` | `PRESERVED_PREREQUISITE` | Explicit Staging singleton sentinel and environment binding; reset cannot provision or replace it. |
| `identities` | `PRESERVED_PREREQUISITE` | Two distinct existing, non-staff synthetic Users bound to reusable identities; reset preserves them. |
| `media` | `PRESERVED_PREREQUISITE` | Designated pre-provisioned media must remain readable; reset reuses it. |
| `root_bindings` | `PRESERVED_PREREQUISITE` | Registered root references must be complete and resolvable, or all absent for the guarded initial creation path; reset cannot repair a partial or dangling binding. |
| `profiles`, `profile_state` | `RESET_OWNED` | Two completed, enabled synthetic profiles with canonical manifest attributes. |
| `convention`, `convention_state` | `RESET_OWNED` | One canonical active/playable Convention with manifest dates. |
| `fursuits`, `fursuit_state` | `RESET_OWNED` | Two registered, enabled Fursuits with canonical identity and asset binding. |
| `ownership` | `PRESERVED_PREREQUISITE` | The guarded reset refuses a registered Fursuit owned by another User before reconciling the row. |
| `enrollments`, `activations` | `RESET_OWNED` | Two active enrollments and two active activations for the registered closure. |
| `catches`, `sessions`, `credentials` | `RESET_OWNED` | No owned Catch, session or credential history in the baseline. |
| `closure` | `PRESERVED_PREREQUISITE` | Unowned dependencies or conflicting ownership deny reset; reset does not expand deletion scope. |

A pre-existing active catch session is `NOT_243_REQUIRED`: the approved plan
may start one normal synthetic session later if the cascade case can safely be
exercised. The reset baseline itself requires zero sessions and credentials.
Unrelated Staging records are also `NOT_243_REQUIRED` and are outside this
diagnostic.

Each invariant emits only `PASS`, `MISSING`, `UNEXPECTED_STATE`,
`UNEXPECTED_COUNT`, `RELATIONSHIP_MISMATCH`, `EXTERNAL_ASSET_UNAVAILABLE`, or
`INDETERMINATE`. Target/input/execution failures use fixed top-level classes.
The output contains no fixture values, user IDs, identities, media keys,
timestamps, raw errors, or permission data. A failed prerequisite, unknown
ownership, or indeterminate result stops the decision before reset.
