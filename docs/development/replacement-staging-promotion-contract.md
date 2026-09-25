# Replacement Staging exact-SHA promotion contract

Status: repository implementation handoff; no replacement promotion has run.
This updates only the canonical Railway target binding in the existing
[#202 promotion procedure](../specs/2026-09-16-controlled-staging-promotion.md)
and [#201 deployment identity join](../specs/2026-09-16-backend-build-deployment-identity.md)
after the replacement environment became canonical. The retired project's
promotion receipts remain historical.

## Acceptance contract

1. Load the replacement `staging` API project, environment, and service selectors
   from the existing owner-only rebuild target manifest and require the existing
   code-owned fingerprint pins. Missing, malformed, inaccessible, or mismatched
   selectors stop before any GitHub/Railway operation or deployment submission.
   Never fall back to the retired project or accept selectors from CLI arguments
   or environment variables.
2. Use the one loaded selector tuple throughout a promotion attempt: Railway
   configuration/autodeploy preflight, exact-SHA submission, exact-deployment
   lifecycle and active-set checks, and exact-instance SSH readback. A record
   belonging to another project, environment, or service cannot pass.
3. The independent deployment-identity command loads and validates the same
   replacement selector authority before its exact-ID Railway lookup. It joins
   only the canonical replacement project/API and retains its existing
   allowlisted output shape. Preserve `join_deployment(identity, record)` for
   the existing restore caller; that function also requires the replacement
   pin and cannot silently accept an old-project record.
4. Preserve #202's eligibility rule (accepted `main` ancestor with successful
   exact-SHA push workflow), one submission, durable safe S/D checkpoint,
   migration/startup/readiness checks, exact-instance identity, canonical HTTP
   smoke, final active-set proof, and fail-closed no-retry behavior.
   On the replacement generation, the required configured pre-deploy command
   is exactly `python -m config.replacement_migrate`, as approved by the
   [replacement API launch contract](../specs/2026-09-24-replacement-api-launch.md).
   The retired generation's direct `manage.py migrate` command is historical
   and must fail replacement promotion preflight.
5. Preserve GitHub and Railway identity gates and sanitized evidence. No raw
   manifest contents, provider response, database URL, secret, or private
   target identifier enters the receipt or an error message.
6. Update the Staging runbook to identify the replacement-only command and
   make the retired target procedure historical. Do not run a live promotion
   merely to test the repository change; first merge approved code and require
   a qualifying successful push workflow on the accepted source commit.

## Test surface and scope guard

Use the existing offline command seams and synthetic Railway/GitHub responses
in `test_api_staging_promote.py` and `test_api_deployment_identity.py`. Stub only
the existing reviewed replacement target-loader seam with synthetic selector
tuples for unit tests; keep the actual owner-only manifest parsing and fingerprint
pins covered by their current tests. Add negative cases for unavailable/wrong
selectors before external work and wrong target identity after submission.

Change only the two operator scripts, their focused tests, the Staging runbook,
and this contract unless an evidenced required integration surface emerges.
Do not change Django product behavior, Railway configuration, the target
manifest, #204 reset behavior, unrelated #243 validation tooling, or the
successful-promotion predicate.
