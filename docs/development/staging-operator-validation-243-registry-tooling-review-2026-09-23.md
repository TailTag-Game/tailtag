# #243 registry classification: local contract review

**Disposition: `PLAN_OR_TOOLING_ERROR` for the prior fixture diagnostic's
`registry=UNEXPECTED_STATE` classification.** This is a repository-only review;
no fresh Staging target, private configuration, registry row, or connected
database value was inspected. The earlier [fixture result](staging-operator-validation-243-fixture-result-2026-09-23.md)
remains unchanged as a record of what that diagnostic emitted. Its registry
classification is not evidence that the persisted sentinel drifted.

The frozen [#204 reset contract](../specs/2026-09-17-staging-synthetic-reset-reseed.md)
requires a separately generated random v4 reset environment UUID in private
operator configuration. `rehearsal.safety.load_configuration` parses that value
from `TAILTAG_STAGING_RESET_ID` while separately validating Railway's fixed
Staging environment selector. Provisioning persists the **reset UUID** in
`StagingResetIdentity.environment_id`. `validate_identity` compares the row to
the private reset configuration. The [#243 fixture diagnostic](../../scripts/api_staging_fixture_diagnose.py)
instead compares the row's `environment_id` to Railway's environment ID. Those
are different contract fields; equality is not required. This incorrect
comparison is sufficient to produce `UNEXPECTED_STATE` for a correctly
provisioned sentinel. It does not prove that the current sentinel is correct.

| Registry/binding condition | What the prior fixture result establishes |
| --- | --- |
| Singleton row count | Exactly one row was read; missing or multiple rows were not reported. The diagnostic's `pk=1` condition and wrong UUID comparison were combined, so the emitted status alone does not isolate either condition. The model/migration constrains `id=1`; current live constraint state was not separately checked here. |
| Persisted reset environment UUID versus private expected reset UUID | **Unverified.** The diagnostic compared the persisted value to Railway's environment UUID instead. |
| Persisted cluster identifier and database name versus private expected values | **Unverified.** The diagnostic did not read or compare these fields. |
| Actual connected database name and cluster identifier versus registry/private values | **Unverified.** The diagnostic did not query these live database facts. |
| Owner/catcher shape | `identities=PASS` established distinct, existing, non-staff, non-superuser registered Users with nonempty provider bindings. Equality to the two privately designated bindings remains unverified. |
| Media | `media=PASS` established readability of the registered asset. Equality to the privately designated media binding remains unverified. |
| Convention/Fursuit roots | `root_bindings=PASS`, `ownership=PASS`, and `closure=PASS` established the diagnostic's registered root resolution, owner, and dependency checks at that observation. Private registry binding values were not compared. |

The original #204 proof records a preserved sentinel and private configuration,
but the public sanitized record does not expose a safe equality receipt capable
of adjudicating a present-day random reset UUID disagreement. Neither the
private configuration nor persisted row may be chosen as authoritative solely
because it exists. No `REGISTRY_REPAIR_CANDIDATE`,
`PRIVATE_CONFIG_REPAIR_CANDIDATE`, or database-binding conclusion follows from
the prior fixture result.

The correct repair boundary is **repository tooling first**: replace the
invalid Railway-ID comparison with a reviewed, value-free three-way check of
private expected configuration, persisted registry, and positively identified
actual database facts. It must preserve indeterminacy for a random reset UUID
disagreement without independent historical proof. Only after local tests and
review may a separately authorized one-time read-only Staging reconciliation
run. No registry, configuration, resource, or fixture repair is authorized by
this review.

No authenticated Staging call, operator inspection, #205 matrix case, #204
reset, provisioning, or mutation occurred in this review. The user-required
local material-issue gate stopped the live sequence before identity/preflight.
