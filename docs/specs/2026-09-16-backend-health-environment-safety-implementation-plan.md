# Backend health and environment safety implementation plan

> **For agentic workers:** Use ADW with independent test authorship,
> implementation, and Compact review. Use executing-plans for tracked execution.

**Goal:** Implement #203's credential-free, fail-closed Staging preflight and
configuration-aware readiness.

**Architecture:** Keep existing liveness/readiness success contracts. Add a small
public three-field identity endpoint using #201's canonical component. A separate
standard-library script validates the canonical origin before making bounded,
redirect-free HTTP checks; it never contacts Railway.

**Tech stack:** Existing Python 3.13, Django 6, PostgreSQL, pytest, urllib,
cryptography, Ruff, Pyright, and Semgrep. No dependencies added.

## Global constraints

- Canonical origin: exactly `https://staging.tailtag.app`.
- Public identity: exactly `source_sha`, `deployment_id`, `environment`.
- No timestamp requirement, timestamp delivery mechanism, Railway authentication,
  vendor probes, expected-SHA pinning, or #199 orchestration.
- Preserve `/health/live` and `/health/ready` success bodies and `no-store`.
- Follow the [frozen contract](2026-09-16-backend-health-environment-safety.md).
- No schema/data changes; no unrelated cleanup or new test infrastructure.
- Verify Finn identity before each authenticated operation and immediately before
  mutations. Publication/deployment require authorization; neither is performed
  by running local checks. Do not create commits as a routine plan step.

## File responsibilities and frozen interfaces

- Create `services/api/health/configuration.py`: local effective-configuration
  validation only. `validate_configuration() -> None` reads effective Django
  settings and #201 runtime identity; raises `ImproperlyConfigured` with a fixed
  message on configuration denial. No network or storage client initialization.
- Modify `services/api/health/views.py`: integrate configuration readiness and add
  `identity(request: HttpRequest) -> JsonResponse`.
- Modify `services/api/config/urls.py`: register `/health/identity`.
- Create `scripts/api_staging_preflight.py`: `validate_target(base_url: str) ->
  BackendIdentity`, where `BackendIdentity` is a TypedDict with three non-null
  string fields. `TargetSafetyError` is a fixed sanitized denial exception.
  Internal `_fetch_json(url: str) -> object` is the normal network boundary.
  `main() -> int` accepts one positional base URL, prints only successful identity
  JSON or a fixed error, returns 0/1. Missing arguments do not default to a target.
- Extend `services/api/tests/test_health.py`; create
  `services/api/tests/test_api_staging_preflight.py` following existing script-test
  imports and urllib mocks. Extend existing configuration tests only where shared
  loader behavior must change; do not weaken existing loader contracts.
- Modify `Makefile` and `services/api/pyproject.toml` only to include the new script
  in formatter/linter/type-check lists. Confirm Semgrep and CI relevance coverage
  in existing configuration; add explicit entries only where absent.
- Update `services/api/README.md` health surfaces and readiness failure meanings.
- Update `docs/development/staging.md` with invocation, meanings, denial semantics,
  public identity versus optional operator correlation, and sanitized validation.

## Task 1: Environment and independent acceptance tests

- [x] Inspect current runtime/dependencies and test services. Use `make api-setup`
  only if locked dependencies are missing; establish `make api-check` baseline
  before test/implementation agents. Track any task-started containers and their
  initial state. No broad Docker cleanup or persistent-volume deletion.
- [x] Give an independent test author the frozen spec and interface section,
  without a proposed implementation. Map every test to AC-1 through AC-10.
- [x] Characterize existing health success/failure bodies and cache headers.
  Add connection-establishment failure alongside existing query failure. Assert
  liveness ignores invalid configuration, unavailable DB, and invalid identity.
- [x] Add deployed configuration cases: disabled/malformed Clerk; missing or
  malformed media settings; storage backend/options contradictions; missing,
  malformed, unknown environment or invalid required SHA/deployment ID; unsafe
  effective Django settings. Preserve explicit local Development behavior.
- [x] Test identity endpoint exact allowlist, `no-store`, sanitized invalid
  identity response, and absence of timestamp. Test with two valid identities to
  reject hard-coded fixtures; verify it calls the canonical #201 component.
- [x] Test canonical preflight success and rejection matrix: invalid origins
  make zero transport calls; missing/null/extra fields; wrong types; invalid SHA
  or UUID; non-Staging identity; wrong status/body; redirects; invalid/oversized
  JSON; timeout/transport failure; identity changing during preflight. Mock urllib
  transport separately to prove redirects and ambient proxies are disabled.
- [x] Parent approves adequacy/scope and observes expected failures on the old
  implementation. Import failures alone are not evidence of behavioral coverage.

Illustrative acceptance assertion at the approved transport seam:

```python
def test_unknown_origin_denied_before_network(monkeypatch):
    from scripts import api_staging_preflight as preflight

    def unexpected_fetch(url):
        raise AssertionError("unsafe origin reached transport")

    monkeypatch.setattr(preflight, "_fetch_json", unexpected_fetch)
    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_target("https://unknown.example")
```

Run focused tests with the repository environment, e.g.
`uv --directory services/api run --locked --no-sync pytest -q tests/test_health.py tests/test_api_staging_preflight.py`.
Use existing environment-loading setup from `make api-test` if needed; do not
print environment values or connection strings to diagnose setup.

## Task 2: Health and effective local configuration

- [x] Implement `validate_configuration()` against settings actually consumed
  by the application. Reconstruct allowlisted input mappings from effective
  Clerk/S3 configuration and feed existing loaders to reuse parsing rules. Do not
  reload unrelated environment values and accidentally validate configuration
  different from what authentication/storage will use.
- [x] Require configured PostgreSQL engine, host, and database, a nonempty secret,
  and valid effective host/origin configuration using existing Django checks or
  existing validators. Local settings retain intentional disabled authentication
  and filesystem storage; deployed settings require enabled Clerk and S3.
- [x] For deployed settings, require a recognized `development` or `staging`
  Railway environment, service `api`, `DEBUG == False`, secure session/CSRF
  settings, and locally valid Clerk/S3 configuration. Unknown or absent deployed
  environment fails. Staging additionally requires its canonical host to be
  allowed and valid non-null #201 SHA/deployment ID. Do not demand Staging identity
  from Development images or local builds that intentionally lack baked SHA.
- [x] Check effective default storage backend and options against effective
  `MEDIA_STORAGE_CONFIGURATION`; reject contradictory credentials/endpoint/bucket/
  region rather than validating an unused dataclass. Do not initialize S3 clients.
- [x] Reject deployed wildcard hosts and malformed configured origins. Reuse
  existing validators rather than tightening Clerk/S3 global syntax. Do not hard
  code private Clerk parties, keys, or storage resource identities: this contract
  proves local validity, not isolation or remote credential authorization.
- [x] Readiness first validates configuration, then performs existing PostgreSQL
  connection/query. Expected config/identity/file-access/database failures become
  fixed `503 {"status":"unavailable"}` with `no-store`. No exception text appears
  in the HTTP body. Do not wrap programmer errors with an indiscriminate catch.
- [x] Identity endpoint calls `config.build_identity.get_identity()` directly.
  Success returns its three-field safe tuple with `no-store`; invalid/unreadable
  identity returns fixed sanitized 503. Preserve explicit null local identity;
  preflight rejects it. No vendor, database, or control-plane calls here.
- [x] Run health/configuration and existing #201 identity tests; confirm old local
  behavior, auth tests, and storage tests remain stable.

Expected view flow (not a new test-only seam):

```text
ready: validate_configuration -> ensure_connection -> SELECT 1 -> fixed success
identity: get_identity -> exact three-field JSON
live: fixed success, independent of both flows
```

If these checks expose a need to change approved authentication/storage semantics
or another subsystem, stop and return for focused replanning.

## Task 3: Credential-free Staging preflight

- [x] Implement exact origin equality before creating a request/opener. No origin
  override, normalization, slash stripping, or default localhost target.
- [x] Use proxy-free urllib opener and no-redirect handler following authenticated
  smoke patterns. Use ordinary HTTPS certificate verification, GET only, a
  five-second request timeout, and at most 4096 bytes per JSON response (read 4097
  to detect excess). Require HTTP 200 and JSON object responses. Errors are fixed
  sanitized denials, not raw response bodies or transport exceptions.
- [x] Fetch `/health/identity`, require exact three fields, non-null 40-character
  lowercase hex SHA, canonical UUID, and environment `staging`. Reuse #201
  structural validation via a shared narrow pure helper if needed; do not import
  or invoke its Railway operator command or duplicate build identity sourcing.
  Keep any helper extraction behavior-preserving and covered by #201 tests.
- [x] Fetch `/health/ready`; require exact `{"status":"ok"}`. Fetch identity again
  and require equality with the first tuple so an observed deployment change
  during preflight denies traffic. Return the captured tuple only after all
  checks. This bounds the observation; it is not remote attestation or a guarantee
  against subsequent changes. No retry against another origin or deployment.
- [x] Implement argument/output handling and test exit 0/1, sanitized failures,
  and absence of timestamp/Railway subprocesses/credentials. No simulator/report
  implementation or synthetic traffic beyond these health/identity GETs.
- [x] Include script in existing deterministic check lists and run focused tests.

Example invocation after implementation:

```bash
uv --directory services/api run --locked --no-sync python ../../scripts/api_staging_preflight.py https://staging.tailtag.app
```

## Task 4: Review, documentation, and final evidence

- [x] Run `make api-check` including Semgrep before independent Compact review.
  Reviewer checks spec compliance, failure paths, scope, test adequacy, and
  SECURITY/RELIABILITY lenses. Resolve AC violations and BLOCKER/HIGH findings.
- [x] Perform explicit plausible-mutant analysis from the spec, including a guard
  that checks only origin/environment/status, accepts redirects, skips config,
  accepts null identity, requires Railway enrichment, or leaks raw errors.
- [x] Update Staging runbook: independent liveness, local config plus DB readiness,
  credential-free preflight command and exact three-field capture, optional #201
  exact-D timestamp correlation, and observed-identity limitations. Keep existing
  generic smoke's local/Development policy intact.
- [x] After authorized publication/promotion through #202, validate canonical
  Staging endpoints and preflight. Capture only safe observed identity/status
  evidence. Invalid URL rejection can be validated locally without live traffic;
  simulate unhealthy configuration/dependencies only in tests, not live chaos.
- [x] Repeat authoritative verification after final changes; run
  `./scripts/doctor.sh` and `git diff --check` for documentation. Stop/remove only
  disposable task-created test containers/networks; restore pre-existing started
  containers to their initial stopped state and preserve data/images.
- [x] Report AC coverage, files/tests changed, deterministic results, review and
  mutant-analysis evidence, Staging proof or pending authorization, and retained
  resource/operational limitations. Do not claim #203 complete before Staging proof.

## Plan coverage and current handoff

AC-1/2: Tasks 1/2; AC-3/4: effective configuration and no vendor calls in Task 2;
AC-5/6/7: origin/identity/readiness and capture in Task 3; AC-8: privilege and
evidence distinction in Tasks 3/4; AC-9: exact safe responses and errors in Tasks
1–3; AC-10: deterministic review and Staging evidence in Task 4.

Environment baseline and independent acceptance tests are complete and approved.
Production implementation and authoritative local verification are complete;
independent Compact review passed with no material findings. Live Staging
validation passed on 2026-09-17; the contract and runbook retain the evidence. The approved behavioral
contract has no remaining timestamp delivery blocker.
