# #243 registry diagnostic correction and future reconciliation

This repository-only correction follows the [local defect review](staging-operator-validation-243-registry-tooling-review-2026-09-23.md).
The [September 23 fixture output](staging-operator-validation-243-fixture-result-2026-09-23.md)
remains historical. No new Staging observation is implied by this document.

## Fixture-level contract

The fixture diagnostic checks that the #204 registry has one row with its
constrained singleton key, a structurally valid **random reset UUID**, decimal
cluster identifier and valid non-`postgres` database name. It separately
checks registered root completeness/resolution and the owned fixture graph.
It does not receive the privately retained #204 configuration or query the
database's actual system identity. Its `binding_equality=NOT_CHECKED` field
means private/registry/database agreement is outside this command. Railway's
environment UUID is used only to identify the Staging runtime target; it is
never compared to the reset UUID.

The prior `identities`, `media`, `root_bindings`, `profiles`, `profile_state`,
`convention`, `convention_state`, `fursuits`, `fursuit_state`, `ownership`,
`enrollments`, `activations`, `catches`, `sessions`, `credentials`, and `closure`
results came from independent checks and remain supported as observations
from that bounded run. The prior `registry=UNEXPECTED_STATE` result was caused
by an invalid comparison and cannot establish sentinel drift. A corrected
fixture baseline and current private/registry/database agreement require
fresh, separately authorized live evidence.

## Separate three-way read-only path

The future reconciliation takes the existing protected, current-operator-owned
`~/.config/tailtag/staging-reset.env` through the #204 strict file parser and
passes its values to one exact Staging instance through SSH stdin only. The
launcher reuses canonical public preflight, approved Railway identity, sole
active deployment/instance selection, and the API/Postgres resource URL
fingerprint join. The remote worker checks the exact build/runtime tuple and
selected resource before reading one registry row and the connected database's
name and PostgreSQL system identifier. It makes no database writes.

The output consists only of fixed structural/equality classifications for:

| Authority comparison | Output key |
| --- | --- |
| Private reset UUID ↔ persisted registry reset UUID | `reset_environment_id` |
| Private database name ↔ registry database name | `database_name_private_registry` |
| Private cluster identifier ↔ registry cluster identifier | `cluster_identifier_private_registry` |
| Actual connected database name ↔ private database name | `database_name_actual_private` |
| Actual connected database name ↔ registry database name | `database_name_actual_registry` |
| Actual connected cluster identifier ↔ private cluster identifier | `cluster_identifier_actual_private` |
| Actual connected cluster identifier ↔ registry cluster identifier | `cluster_identifier_actual_registry` |
| Privately designated owner/catcher/media ↔ registered bindings | `owner_binding_private_registry`, `catcher_binding_private_registry`, `media_binding_private_registry` |
| Effective database connection host/port ↔ private host/port | `database_host_runtime_private`, `database_port_runtime_private` |

The worker also reports `registry_singleton`, `registry_structure`, and
`root_completeness` as separate fixed classifications.
A random reset UUID disagreement is a disagreement only; neither side is
automatically authoritative. Database and cluster three-way outcomes may
identify a candidate drift direction, but cannot authorize repair. Missing or
malformed configuration, target ambiguity, and query failure fail closed with
fixed status and no compared values.

**Future command, requiring separate live approval:** from the repository root,
with the approved identity available to the operator:

```sh
uv --directory services/api run --locked --no-sync python \
  ../../scripts/api_staging_registry_reconcile.py \
  --config ~/.config/tailtag/staging-reset.env
```

This command must not be run as part of the repository-only correction. The
private file, exact instance, and live database have not been inspected here.
No registry/configuration/fixture repair, reset, provisioning, operator
inspection or #205 matrix execution is authorized by this documentation.
