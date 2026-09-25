# #243 read-only registry reconciliation — 2026-09-23

**Result: `PASS` for the bounded three-way registry comparison.** This is
read-only evidence, not a #205 matrix result or authorization to reset/repair.

The reviewed reconciler at commit `1854162af2d7aca6463843a23fb31c4c33a95ffc`
was run once during the bounded 2026-09-23 23:09 UTC observation window. Its
guarded path verified the approved GitHub and Railway identities, canonical
credential-free Staging preflight, approved deployment receipt, exact sole
running instance, API/Postgres resource binding, and runtime build/target
identity before querying the registry and connected database. A follow-up
credential-free preflight returned the same public tuple:

| Public target fact | Observed value |
| --- | --- |
| Environment | `staging` |
| Source SHA | `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` |
| Deployment ID | `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Approved receipt | [Matching active successful deployment](staging-deployments/cbe83780-0256-49c2-b026-34709ddb69b0.json) |

The single command returned the following fixed, value-free checks:

| Check | Result |
| --- | --- |
| `registry_singleton` | `PASS` |
| `registry_structure` | `PASS` |
| `root_completeness` | `PASS` |
| `reset_environment_id` | `MATCH` |
| `database_name_private_registry` | `MATCH` |
| `cluster_identifier_private_registry` | `MATCH` |
| `database_name_actual_private` | `MATCH` |
| `database_name_actual_registry` | `MATCH` |
| `cluster_identifier_actual_private` | `MATCH` |
| `cluster_identifier_actual_registry` | `MATCH` |
| `owner_binding_private_registry` | `MATCH` |
| `catcher_binding_private_registry` | `MATCH` |
| `media_binding_private_registry` | `MATCH` |
| `database_host_runtime_private` | `MATCH` |
| `database_port_runtime_private` | `MATCH` |

The old [fixture output](staging-operator-validation-243-fixture-result-2026-09-23.md)
remains unchanged. Its `registry=UNEXPECTED_STATE` was caused by the invalid
Railway/reset UUID comparison and never established drift. This new result
establishes registry structure and private/registry/connected-database
agreement at this observation only. It does not re-evaluate all 17 fixture
invariants, establish current operator permissions, or substantiate any of
the nine #205 cases. Matrix cases 1–9 remain `NOT_EXERCISED` in this sequence.

No operator inspection, #204 reset/provisioning, fixture repair, #205 matrix
action, registry/configuration change, Railway resource change, or Staging
mutation occurred. No private compared values or raw query output were
retained. The next bounded #243 pre-mutation inspection remains separately
authorized work; this result alone does not close #243 or #208.
