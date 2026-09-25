# #243 fixture-only Staging diagnosis — 2026-09-23

**Overall: `PREREQUISITE_REPAIR_REQUIRED`.** This is one bounded, authenticated,
read-only diagnosis of the earlier `FAIL_FIXTURE_STATE_MISMATCH` classification.
The [earlier attempt](staging-operator-validation-243-attempt-2026-09-23.md)
remains historical evidence and is not reclassified by this result.

| Target and execution fact | Sanitized observation |
| --- | --- |
| Diagnostic window | 2026-09-23 20:29:02–20:29:06 UTC |
| Public canonical preflight | `PASS`; `environment=staging`; source `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`; deployment `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Current target correlation | One active running Railway instance; exact deployment record, instance identity readback, approved [#202 receipt](staging-deployments/cbe83780-0256-49c2-b026-34709ddb69b0.json), and exact GitHub source commit agreed with the fresh public tuple |
| Execution | The reviewed fixture-only diagnostic from commit `0b66950` was streamed to that exact instance once. It returned one valid fixed-status payload: `FAIL_FIXTURE_STATE_MISMATCH`. Its nonzero exit is the expected exit for that classified mismatch, not an authenticated transport failure. |

The ownership column follows the frozen [#204/#243 map](staging-operator-validation-243-fixture-diagnosis.md).
No row values, object identifiers, media keys, or private configuration are
retained.

| Fixture invariant | Sanitized result | Ownership |
| --- | --- | --- |
| `registry` | `UNEXPECTED_STATE` | `PRESERVED_PREREQUISITE` |
| `identities` | `PASS` | `PRESERVED_PREREQUISITE` |
| `media` | `PASS` | `PRESERVED_PREREQUISITE` |
| `root_bindings` | `PASS` | `PRESERVED_PREREQUISITE` |
| `profiles` | `PASS` | `RESET_OWNED` |
| `profile_state` | `PASS` | `RESET_OWNED` |
| `convention` | `PASS` | `RESET_OWNED` |
| `convention_state` | `PASS` | `RESET_OWNED` |
| `fursuits` | `PASS` | `RESET_OWNED` |
| `fursuit_state` | `PASS` | `RESET_OWNED` |
| `ownership` | `PASS` | `PRESERVED_PREREQUISITE` |
| `enrollments` | `PASS` | `RESET_OWNED` |
| `activations` | `PASS` | `RESET_OWNED` |
| `catches` | `PASS` | `RESET_OWNED` |
| `sessions` | `PASS` | `RESET_OWNED` |
| `credentials` | `PASS` | `RESET_OWNED` |
| `closure` | `PASS` | `PRESERVED_PREREQUISITE` |

`registry=UNEXPECTED_STATE` means the existing #204 sentinel did not satisfy
the diagnostic's fixed singleton/environment binding check. The classification
does not disclose or establish the underlying registry values, and this task
did not inspect them further. The #204 reset preserves the sentinel and cannot
provision or repair it, so a normal guarded reset is **not sufficient** to
resolve this observed prerequisite mismatch. No plan/baseline contradiction was
observed. A separate, explicitly authorized #204 registry/configuration
reconciliation must establish the precise cause and an approved repair boundary
before any reset or #205 validation resumes.

The diagnostic did not inspect operator users, groups, or permissions. Matrix
cases 1–9 remain `NOT_EXERCISED`; #204 reset was not invoked. The executed
preflight, control-plane reads, instance identity readback, and diagnostic were
read-only. No Staging mutation occurred. Current fixture classifications are
point-in-time observations and do not establish operator readiness or #243
completion.
