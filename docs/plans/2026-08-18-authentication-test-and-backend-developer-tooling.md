# Authentication Test and Backend Developer Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Issue:** [#99 — Add authentication test and backend developer tooling](https://github.com/TailTag-Game/tailtag/issues/99)

**Spec:** [`docs/specs/2026-08-18-authentication-test-and-backend-developer-tooling.md`](../specs/2026-08-18-authentication-test-and-backend-developer-tooling.md)

**Goal:** Add reusable offline authentication test support and one atomic, interactive, Development-only Clerk-authenticated smoke command for the local or exact-configured Railway development TailTag API.

**Architecture:** Keep reusable pytest support entirely inside `services/api/tests/`. Keep privileged live logic in repository-root scripts so it is not copied into the production API image: one module owns guarded command orchestration and one owns the Clerk Backend API/Frontend API adapter and cleanup state. The Make target runs those scripts with the locked API environment, while ordinary tests replace external boundaries and remain outbound-network prohibited.

**Tech Stack:** Python 3.13, Django 6.0, Django REST Framework 3.16, pytest, `clerk-backend-api==7.0.0`, `cryptography`, Python standard-library HTTP/cookie/TTY utilities, Ruff, Pyright, GNU Make.

## Global Constraints

- Do not modify or weaken issue #96 session-token-only, `sid`, `sub`, signature, issuer, time, or `authorizedParties` verification.
- The only tooling Origin is the non-configurable literal `http://localhost:3000`; the resulting `azp` must equal it exactly.
- The default TailTag target is exactly `http://127.0.0.1:8000`; a non-default target must pass the exact `TAILTAG_DEVELOPMENT_API_BASE_URL` policy in the spec.
- Validate the target and run credential-free baseline smoke before prompting or contacting Clerk.
- Accept a Clerk secret only from the interactive hidden prompt `Clerk Development secret:`; require a TTY and provide no noninteractive fallback.
- Treat `sk_test_` only as an early form guard; Clerk instance metadata is the authoritative Development-instance check.
- Provider locations are not configurable and all Backend API and Frontend API work remains bound to the same validated Clerk Development instance.
- Use the configured persistent `CLERK_SMOKE_USER_ID`; never provision, select by profile, replace, modify, or delete that Clerk user.
- The corresponding TailTag user is intentionally persistent. Tickets, sessions, and bearer tokens are ephemeral per invocation.
- Request a 60-second ticket. Independently require the normal session JWT's numeric `iat` and `exp` to describe a positive lifetime no greater than 60 seconds, as established by the successful FAPI spike.
- Never print, log, persist, or expose secrets, tickets, bearer tokens, Clerk identifiers, session identifiers, raw sensitive responses, or sensitive claims.
- Required cleanup runs after resource creation on all exits. Cleanup failure is unsuccessful; combined failure preserves sanitized primary-stage and cleanup-incomplete indications.
- `GET /api/me/` never follows redirects and must return HTTP 200 with exactly `{"id": <integer>}`.
- All reusable pytest authentication support lives under `services/api/tests/`; add no `factory_boy`, production test helper, application-facing testing API, migration, custom JWT template, production Clerk behavior, or new dependency.
- Ordinary automated tests prohibit outbound network. `api-smoke`, `api-check`, and CI remain credential-free and noninteractive; only explicit `make api-auth-smoke` reaches Clerk Development.

## File Structure

- Create `services/api/tests/authentication_support.py`: typed factories and the two approved test-authentication modes.
- Create `services/api/tests/test_authentication_support.py`: behavioral contract for the reusable pytest support.
- Create `services/api/tests/test_clerk_development_session.py`: offline acceptance tests for Development metadata, ticket/FAPI/token verification, binding, cleanup, and sanitization.
- Create `services/api/tests/test_api_auth_smoke.py`: offline acceptance tests for target policy, sequencing, TTY prompt, `/api/me/`, combined outcomes, and output sanitization.
- Modify `services/api/tests/test_current_user_api.py`: consume endpoint-isolation and composed-authentication helpers.
- Modify `services/api/tests/test_drf_identity_authentication.py`: consume the reusable composed fake without changing its behavioral coverage.
- Modify `services/api/tests/test_developer_commands.py`: cover the Make entry point and prove `api-check`/ordinary commands remain non-live.
- Create `scripts/clerk_development_session.py`: fixed-provider Clerk Development adapter, FAPI ticket flow, claims/verifier checks, and cleanup state.
- Create `scripts/api_auth_smoke.py`: target validation, baseline sequencing, hidden prompt, authenticated `/api/me/`, sanitized result composition, and CLI entry point.
- Modify `Makefile`: add only the atomic `api-auth-smoke` interface and include both scripts in static checks without adding it to `api-check`.
- Modify `services/api/pyproject.toml`: include both new root scripts in strict Pyright coverage; add no dependency.
- Modify `services/api/.env.example`: document only the non-secret Development smoke-user/target inputs and fixed authorized party, never a Clerk secret variable.
- Modify `README.md` and `services/api/README.md`: document setup, local/remote invocation, persistent versus ephemeral state, failure/cleanup behavior, and production prohibition.

---

### Task 1: Independently Author the Acceptance Tests

**Owner:** Fresh `test_author` context. This task changes tests only and must not inspect or author the production implementation.

**Files:**
- Create: `services/api/tests/test_authentication_support.py`
- Create: `services/api/tests/test_clerk_development_session.py`
- Create: `services/api/tests/test_api_auth_smoke.py`
- Modify: `services/api/tests/test_developer_commands.py`

**Interfaces:**
- Consumes: The approved spec and the interface names listed below.
- Produces: Independent failing acceptance tests for Tasks 2–5.

The tests may import these planned internal interfaces but must assert behavior, not private decomposition:

```python
# services/api/tests/authentication_support.py
def create_test_user(*, clerk_user_id: str | None = None) -> User: ...
def force_authenticated_client(*, user: User) -> APIClient: ...
def fake_clerk_session_verification(
    monkeypatch: MonkeyPatch,
    *,
    subject: str,
) -> list[HttpRequest]: ...

# scripts/api_auth_smoke.py
def validate_api_target(environment: Mapping[str, str]) -> str: ...
class SmokeRuntime(Protocol):
    def run_baseline(self, *, base_url: str) -> bool: ...
    def prompt_secret(self) -> str: ...
    def validate_clerk(
        self,
        *,
        secret: str,
        user_id: str,
    ) -> ClerkDevelopmentSession: ...
    def request_current_user(
        self,
        *,
        base_url: str,
        bearer_token: str,
    ) -> None: ...
def run(environment: Mapping[str, str], runtime: SmokeRuntime) -> SmokeOutcome: ...
def main() -> int: ...

# scripts/clerk_development_session.py
class ClerkDevelopmentSession:
    @classmethod
    def validate(cls, *, secret: str, user_id: str) -> ClerkDevelopmentSession: ...
    def create_verified_token(self) -> str: ...
    def cleanup(self) -> None: ...
```

- [ ] **Step 1: Add the reusable-support acceptance matrix**

Write tests proving unique opaque IDs, persistence, explicit override, real-user `force_authenticate()`, and a fake at exactly `ClerkSessionVerifier.verify` that leaves the real DRF authenticator and resolver active. Reject helper return values that make `VerifiedClerkIdentity` the downstream endpoint convention.

```python
@pytest.mark.django_db
def test_user_factory_persists_unique_opaque_clerk_identities() -> None:
    first = create_test_user()
    second = create_test_user()

    assert first.pk is not None
    assert second.pk is not None
    assert first.clerk_user_id != second.clerk_user_id
    assert User.objects.filter(pk__in=(first.pk, second.pk)).count() == 2

@pytest.mark.django_db
def test_composed_fake_retains_authenticator_and_resolver(
    monkeypatch: MonkeyPatch,
) -> None:
    requests = fake_clerk_session_verification(
        monkeypatch,
        subject="user_test_composed_acceptance",
    )
    response = Client().get("/api/me/", HTTP_AUTHORIZATION="Bearer synthetic")

    user = User.objects.get(clerk_user_id="user_test_composed_acceptance")
    assert response.json() == {"id": user.pk}
    assert len(requests) == 1
```

- [ ] **Step 2: Add exhaustive target-policy and sequencing tests**

Parameterize accepted and rejected values. Cover absent default, explicit default with one trailing slash, HTTPS exact remote equality, empty values, alternate loopback names, URL credentials, non-HTTPS remote, query, fragment, path, mismatches, suffix tricks, ports, encoded values, and extra trailing slashes. Record runtime events and assert the required order.

```python
def test_baseline_precedes_prompt_and_provider() -> None:
    runtime = RecordingRuntime()

    outcome = auth_smoke.run(
        {
            "CLERK_SMOKE_USER_ID": "user_synthetic",
            "API_BASE_URL": "http://127.0.0.1:8000",
        },
        runtime,
    )

    assert outcome.succeeded
    assert runtime.events == [
        "baseline:http://127.0.0.1:8000",
        "prompt",
        "provider-validate",
        "provider-create-token",
        "api-me",
        "cleanup",
    ]

@pytest.mark.parametrize("environment", DISALLOWED_TARGETS)
def test_disallowed_target_stops_before_baseline_prompt_or_provider(
    environment: Mapping[str, str],
) -> None:
    runtime = RecordingRuntime()
    outcome = auth_smoke.run(environment, runtime)

    assert outcome.primary_stage == "target configuration invalid"
    assert runtime.events == []
```

- [ ] **Step 3: Add prompt, provider-binding, token, and `/api/me/` tests**

Prove stdin and prompt stream TTY requirements, hidden prompt use, exact prompt text, no secret env/argument path, `sk_test_` early rejection, metadata-authoritative Development validation, opaque user lookup, no auto-provision, provider-location binding, fixed Origin, 60-second ticket input, normal token endpoint, exact claim checks, unchanged verifier use, redirect rejection, and exact JSON object/type.

```python
@pytest.mark.parametrize(
    "body",
    (
        {"id": True},
        {"id": "1"},
        {"id": 1, "clerk_user_id": "user_synthetic"},
        {},
        [1],
    ),
)
def test_api_me_rejects_every_nonexact_response(body: object) -> None:
    runtime = RecordingRuntime(api_me_body=body)
    assert not auth_smoke.run(VALID_ENVIRONMENT, runtime).succeeded
```

- [ ] **Step 4: Add cleanup and combined-failure tests**

Inject a failure after each resource-creation step and prove supported cleanup runs. Cover unconsumed ticket revocation, consumed ticket handling, session revocation, no persistent-user deletion, cleanup-only failure, and primary-plus-cleanup failure retaining two sanitized stage categories.

```python
def test_primary_and_cleanup_failures_are_both_sanitized() -> None:
    runtime = RecordingRuntime(
        api_me_error=SensitiveSyntheticError(SENSITIVE_VALUES),
        cleanup_error=SensitiveSyntheticError(SENSITIVE_VALUES),
    )

    outcome = auth_smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.primary_stage == "authenticated API response invalid"
    assert outcome.cleanup_incomplete
    assert not outcome.succeeded
```

- [ ] **Step 5: Add adversarial sanitization and offline-network tests**

Inject synthetic secret-like values, tickets, JWTs, Clerk user/session IDs, raw response bodies, and decoded sensitive claims into each external exception path. Capture stdout, stderr, logs, exception rendering, and returned outcome rendering; assert none appears. Monkeypatch standard-library HTTP and Clerk SDK request methods to fail if any ordinary automated path escapes a test fake.

```python
SENSITIVE_VALUES = (
    "sk_test_synthetic_credential_material",
    "ticket_synthetic_sensitive_material",
    "eyJsynthetic.header.payload",
    "user_synthetic_sensitive_identifier",
    "sess_synthetic_sensitive_identifier",
    '"private_claim":"synthetic-sensitive-value"',
)

def assert_supported_outputs_are_sanitized(
    outcome: SmokeOutcome,
    captured: CaptureResult[str],
    caplog: LogCaptureFixture,
) -> None:
    rendered = "\n".join((repr(outcome), captured.out, captured.err, caplog.text))
    for value in SENSITIVE_VALUES:
        assert value not in rendered
```

- [ ] **Step 6: Extend Make-command contract tests**

Require `make help` to list `api-auth-smoke`; require its dry run to invoke the new atomic script through the locked API project; prove `make -n api-check`, ordinary `api-smoke`, and CI workflow text contain no auth-smoke invocation, prompt, or Clerk secret variable.

- [ ] **Step 7: Run the independent tests and record the expected red state**

Run:

```bash
make api-test
```

Expected: FAIL only because planned support/scripts/Make wiring do not exist or do not satisfy the newly frozen behavior. Existing tests must not newly fail for unrelated reasons.

- [ ] **Step 8: Commit the acceptance tests without production changes**

```bash
git add services/api/tests
git commit -m "test(auth): freeze issue 99 tooling acceptance"
```

---

### Task 2: Implement Repository-Internal Authentication Test Support

**Owner:** Fresh `implementer` context; do not weaken Task 1 tests.

**Files:**
- Create: `services/api/tests/authentication_support.py`
- Modify: `services/api/tests/test_current_user_api.py`
- Modify: `services/api/tests/test_drf_identity_authentication.py`
- Test: `services/api/tests/test_authentication_support.py`

**Interfaces:**
- Consumes: `accounts.User`, `APIClient.force_authenticate()`, `ClerkSessionVerifier.verify`, and `VerifiedClerkIdentity`.
- Produces: `create_test_user()`, `force_authenticated_client()`, and `fake_clerk_session_verification()` with the exact signatures from Task 1.

- [ ] **Step 1: Run the focused tests and confirm the support module is the failure**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_authentication_support.py tests/test_current_user_api.py tests/test_drf_identity_authentication.py
```

Expected: new support tests fail because `tests.authentication_support` is absent; existing authentication behavior remains green.

- [ ] **Step 2: Implement explicit typed factories and helpers**

Use UUID4 only to generate an opaque unique test identifier; persist through the existing user manager. Patch only the verifier class method and return captured Django requests for assertions.

```python
def create_test_user(*, clerk_user_id: str | None = None) -> User:
    subject = clerk_user_id or f"user_test_{uuid4().hex}"
    return User.objects.create_user(clerk_user_id=subject)


def force_authenticated_client(*, user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def fake_clerk_session_verification(
    monkeypatch: MonkeyPatch,
    *,
    subject: str,
) -> list[HttpRequest]:
    requests: list[HttpRequest] = []

    def verify(
        _verifier: ClerkSessionVerifier,
        request: HttpRequest,
    ) -> VerifiedClerkIdentity:
        requests.append(request)
        return VerifiedClerkIdentity(subject=subject)

    monkeypatch.setattr(ClerkSessionVerifier, "verify", verify)
    return requests
```

- [ ] **Step 3: Replace duplicated endpoint setup with the approved support**

Use `create_test_user()` plus `force_authenticated_client()` for isolated `/api/me/` tests and `fake_clerk_session_verification()` for composed paths. Keep every assertion that proves the real resolver, request type, bearer header, permission, error, and exact response behavior.

- [ ] **Step 4: Run the focused support and authentication tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_authentication_support.py tests/test_current_user_api.py tests/test_drf_identity_authentication.py tests/test_clerk_authentication.py
```

Expected: PASS with no outbound provider request.

- [ ] **Step 5: Commit the test-support deliverable**

```bash
git add services/api/tests
git commit -m "test(auth): add reusable TailTag authentication support"
```

---

### Task 3: Implement the Development-Only Clerk Session Adapter

**Owner:** Fresh `implementer` context; use current official Clerk documentation matching the repository's locked SDK and do not change approved tests.

**Files:**
- Create: `scripts/clerk_development_session.py`
- Test: `services/api/tests/test_clerk_development_session.py`
- Modify: `services/api/pyproject.toml`

**Interfaces:**
- Consumes: `clerk-backend-api==7.0.0`, `ClerkSessionVerifier`, `ClerkVerificationConfiguration`, the fixed tooling Origin, and the persistent Clerk user ID.
- Produces: `ClerkDevelopmentSession.validate(secret=..., user_id=...)`, `create_verified_token()`, `cleanup()`, and sanitized stage exceptions for Task 4.

- [ ] **Step 1: Confirm the provider tests fail without the adapter**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_clerk_development_session.py
```

Expected: FAIL because the root adapter module is absent.

- [ ] **Step 2: Add non-sensitive adapter state and sanitized errors**

State fields containing the secret, ticket, session ID, and bearer token must use `repr=False`. Publicly rendered exceptions contain a closed stage enum only and use `raise ... from None` at third-party boundaries.

```python
TOOLING_ORIGIN: Final = "http://localhost:3000"
MAX_SESSION_TOKEN_LIFETIME_SECONDS: Final = 60
SIGN_IN_TICKET_LIFETIME_SECONDS: Final = 60


class ClerkFlowStage(StrEnum):
    INSTANCE = "Clerk instance not validated as Development"
    USER = "configured smoke user unavailable"
    TICKET = "provider ticket flow unsuccessful"
    TOKEN = "provider session-token flow unsuccessful"
    CLAIMS = "token claims or lifetime invalid"
    VERIFIER = "TailTag verifier rejected the token"
    CLEANUP = "cleanup incomplete"


@dataclass(slots=True)
class ClerkDevelopmentSession:
    _secret: str = field(repr=False)
    _user_id: str = field(repr=False)
    _ticket_id: str | None = field(default=None, repr=False)
    _ticket_consumed: bool = False
    _session_id: str | None = field(default=None, repr=False)
    _token: str | None = field(default=None, repr=False)
```

- [ ] **Step 3: Implement authoritative instance and user validation**

Reject non-`sk_test_` input before constructing `Clerk`. Construct `Clerk(bearer_auth=secret)` without `server_url`, debug logger, or caller-supplied endpoint. Call `instance_settings.get()` and require `environment_type == "development"`; then call `users.get(user_id=user_id)` and require the returned opaque ID to match exactly. Normalize all SDK failures to the corresponding safe stage without rendering the SDK exception.

- [ ] **Step 4: Implement the documented FAPI ticket exchange**

Create `CreateSignInTokenRequestBody(user_id=user_id, expires_in_seconds=60)` through `clerk.sign_in_tokens.create()`. Derive the Frontend API authority only from the sign-in URL returned by that validated instance; do not accept a configured authority. Use a private cookie jar and standard-library opener to perform the documented Frontend API `2026-05-12` sequence:

```text
POST /v1/dev_browser
POST /v1/client
POST /v1/client/sign_ins     strategy=ticket, ticket=<in-memory ticket>
POST /v1/client/sessions/<session-id>/tokens
```

All relevant Frontend API calls carry `Origin: http://localhost:3000`, use URL-encoded form bodies where required by the upstream contract, have finite timeouts, reject redirects, and keep response bodies private. Require an active session belonging to the configured user and obtain the normal token endpoint response; never call a JWT-template endpoint.

- [ ] **Step 5: Validate claims and invoke the unchanged verifier**

Decode only the JWT header/payload needed to select the matching JWK and test `sid`, `sub`, `azp`, `iat`, and `exp`; never log the decoded object. Build an RSA PEM key from the matching validated-instance JWK with `cryptography`, then pass a Django request containing the Bearer value to the existing verifier.

```python
lifetime = exp - iat
if (
    sid != self._session_id
    or sub != self._user_id
    or azp != TOOLING_ORIGIN
    or type(iat) is not int
    or type(exp) is not int
    or not 0 < lifetime <= MAX_SESSION_TOKEN_LIFETIME_SECONDS
    or exp <= int(time.time())
):
    raise ClerkFlowFailure(ClerkFlowStage.CLAIMS)

identity = ClerkSessionVerifier(
    ClerkVerificationConfiguration(
        jwt_key=public_key_pem,
        authorized_parties=(TOOLING_ORIGIN,),
    )
).verify(request)
if identity is None or identity.subject != self._user_id:
    raise ClerkFlowFailure(ClerkFlowStage.VERIFIER)
```

- [ ] **Step 6: Implement supported cleanup state transitions**

If a session ID exists, call `clerk.sessions.revoke(session_id=...)`. If a ticket exists and was not consumed, call `clerk.sign_in_tokens.revoke(sign_in_token_id=...)`. A consumed single-use ticket needs no unsupported deletion. Attempt every applicable cleanup action even if an earlier one fails; after attempts, raise only the sanitized cleanup stage when any required action failed. Never call a user delete/update method.

- [ ] **Step 7: Pass provider, sanitization, and network-isolation tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_clerk_development_session.py tests/test_clerk_authentication.py
uv --directory services/api run --locked --no-sync ruff check ../../scripts/clerk_development_session.py tests/test_clerk_development_session.py
uv --directory services/api run --locked --no-sync pyright ../../scripts/clerk_development_session.py
```

Expected: PASS. Test requests remain fully fake and no test contacts Clerk.

- [ ] **Step 8: Commit the provider adapter**

```bash
git add scripts/clerk_development_session.py services/api/tests/test_clerk_development_session.py services/api/pyproject.toml
git commit -m "feat(auth): add guarded Clerk Development session adapter"
```

---

### Task 4: Implement Atomic Authenticated Smoke Orchestration

**Owner:** Fresh `implementer` context; preserve Task 1 tests and use the Task 3 adapter as the only provider path.

**Files:**
- Create: `scripts/api_auth_smoke.py`
- Test: `services/api/tests/test_api_auth_smoke.py`
- Modify: `services/api/pyproject.toml`

**Interfaces:**
- Consumes: `ClerkDevelopmentSession`, root `scripts/api_smoke.py`, environment mappings, hidden TTY input, and standard-library HTTP.
- Produces: `validate_api_target()`, behavioral `run()` with injectable external runtime operations for offline tests, `SmokeOutcome`, and `main()`.

- [ ] **Step 1: Confirm orchestration tests fail without the command module**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_api_auth_smoke.py
```

Expected: FAIL because the orchestration module is absent.

- [ ] **Step 2: Implement exact target parsing and canonical comparison**

Use `urlsplit()` only for structural rejection. Canonicalization removes one root trailing slash and performs no other transformation. Catch invalid ports and malformed parsing without echoing input.

```python
DEFAULT_API_BASE_URL: Final = "http://127.0.0.1:8000"


def _remove_root_trailing_slash(value: str) -> str:
    return value[:-1] if value.endswith("/") else value


def validate_api_target(environment: Mapping[str, str]) -> str:
    configured = environment.get("API_BASE_URL")
    if configured is None:
        target = DEFAULT_API_BASE_URL
    elif configured == "":
        raise SmokeFailure(SmokeStage.TARGET)
    else:
        target = _validate_root_url(configured)

    target = _remove_root_trailing_slash(target)
    development = environment.get("TAILTAG_DEVELOPMENT_API_BASE_URL")
    validated_development = (
        _validate_https_root_url(development) if development is not None else None
    )
    if target != DEFAULT_API_BASE_URL and (
        validated_development is None
        or target != _remove_root_trailing_slash(validated_development)
    ):
        raise SmokeFailure(SmokeStage.TARGET)
    return target
```

Require no whitespace/backslash ambiguity, lowercase HTTPS for remote, no credentials/query/fragment, and path only `""` or `"/"`. When the Development value is present, validate it even for the local target.

- [ ] **Step 3: Implement baseline and hidden-prompt sequencing**

Reject every command-line argument or option before target validation; the
module has no CLI inputs. Run the existing `scripts/api_smoke.py` with the
validated `API_BASE_URL` as a credential-free subprocess before
checking/prompting for the secret. Do not pass any secret because none exists
yet. Require `sys.stdin.isatty()` and the prompt stream TTY before calling
`getpass.getpass("Clerk Development secret:")`.

- [ ] **Step 4: Implement `/api/me/` without redirects**

Use a dedicated `HTTPRedirectHandler` that returns no redirect request, finite timeout, and an in-memory Authorization header. Require status 200, JSON content, `type(body) is dict`, `set(body) == {"id"}`, and `type(body["id"]) is int`; this explicitly rejects booleans.

- [ ] **Step 5: Compose primary and cleanup outcomes**

After `ClerkDevelopmentSession.validate()` succeeds, create the token and call `/api/me/` inside a `try` whose `finally` always calls cleanup once any ticket may exist. Keep the first sanitized primary stage, separately mark cleanup incomplete, and never render caught third-party exceptions.

```python
@dataclass(frozen=True, slots=True)
class SmokeOutcome:
    primary_stage: str | None = None
    cleanup_incomplete: bool = False

    @property
    def succeeded(self) -> bool:
        return self.primary_stage is None and not self.cleanup_incomplete
```

Print only bounded stage success/failure copy in `main()`. The outcome representation itself must contain no sensitive values.

- [ ] **Step 6: Pass orchestration, ordering, and sanitization tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_api_auth_smoke.py
uv --directory services/api run --locked --no-sync ruff check ../../scripts/api_auth_smoke.py tests/test_api_auth_smoke.py
uv --directory services/api run --locked --no-sync pyright ../../scripts/api_auth_smoke.py
```

Expected: PASS with all outbound operations replaced and zero injected sensitive values in supported outputs.

- [ ] **Step 7: Commit the atomic orchestrator**

```bash
git add scripts/api_auth_smoke.py services/api/tests/test_api_auth_smoke.py services/api/pyproject.toml
git commit -m "feat(auth): add atomic authenticated API smoke workflow"
```

---

### Task 5: Wire the Command and Document Development Operation

**Owner:** Fresh `implementer` context.

**Files:**
- Modify: `Makefile`
- Modify: `services/api/tests/test_developer_commands.py`
- Modify: `services/api/.env.example`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Test: `services/api/tests/test_developer_commands.py`

**Interfaces:**
- Consumes: `python -m scripts.api_auth_smoke` and all approved configuration names.
- Produces: the sole supported `make api-auth-smoke` entry point and complete contributor documentation.

- [ ] **Step 1: Confirm Make contract tests fail before wiring**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_developer_commands.py
```

Expected: FAIL only on the new `api-auth-smoke` expectations.

- [ ] **Step 2: Add the atomic Make target without changing ordinary commands**

Run from the repository root while using the locked `services/api` project so the root `scripts` namespace is importable. Do not add dependencies from `api-check`, `api-smoke`, or CI.

```make
api-auth-smoke: ## Authenticated smoke test with an interactive Clerk Development secret.
	uv run --project $(API_DIRECTORY) --locked --no-sync python -m scripts.api_auth_smoke
```

Add both new script paths to Ruff formatting/lint arguments and strict Pyright includes. Keep the target phony and non-mutating with respect to database schema.

- [ ] **Step 3: Document safe non-secret configuration**

In `.env.example`, provide commented Development-only examples for `CLERK_SMOKE_USER_ID`, `TAILTAG_DEVELOPMENT_API_BASE_URL`, and adding the fixed tooling origin to development `CLERK_AUTHORIZED_PARTIES`. Do not add a secret variable or imply that the command automatically loads `.env`; invocation docs must explain exporting/prefixing only non-secret values.

- [ ] **Step 4: Document setup and local/Railway operation**

Update both READMEs with:

```text
Local:
CLERK_SMOKE_USER_ID=<opaque-development-user-id> make api-auth-smoke

Railway development:
API_BASE_URL=https://<exact-development-api-host> \
TAILTAG_DEVELOPMENT_API_BASE_URL=https://<exact-development-api-host> \
CLERK_SMOKE_USER_ID=<opaque-development-user-id> \
make api-auth-smoke
```

Explain manual one-time dedicated-user creation, fixed synthetic origin, no frontend requirement, hidden per-run prompt, metadata authority, persistent Clerk/TailTag user state, ephemeral ticket/session/token state, cleanup, sanitized failures, exact `/api/me/`, and all production/CI prohibitions. Preserve the statement that the API verifier itself requires no Clerk secret.

- [ ] **Step 5: Pass command, documentation, and non-live boundary tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_developer_commands.py tests/test_api_auth_smoke.py tests/test_clerk_development_session.py
make -n api-check
./scripts/doctor.sh
git diff --check
```

Expected: PASS; `make -n api-check` contains no `api-auth-smoke`, prompt, or Clerk live flow.

- [ ] **Step 6: Commit wiring and documentation**

```bash
git add Makefile services/api/pyproject.toml services/api/.env.example services/api/tests/test_developer_commands.py README.md services/api/README.md
git commit -m "docs(auth): document authenticated development smoke"
```

---

### Task 6: Deterministic Integration and Sanitized Live Validation

**Owner:** Orchestrator, followed by fresh specification and code-quality reviewers.

**Files:**
- Verify all issue #99 files against the approved spec.
- Modify only files required to remediate confirmed issue #99 findings.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: authoritative offline verification, independent review evidence, and one explicitly initiated sanitized Development live result.

- [ ] **Step 1: Run focused offline acceptance tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_authentication_support.py \
  tests/test_clerk_development_session.py \
  tests/test_api_auth_smoke.py \
  tests/test_developer_commands.py \
  tests/test_clerk_authentication.py \
  tests/test_current_user_api.py \
  tests/test_drf_identity_authentication.py
```

Expected: PASS with outbound network prohibited.

- [ ] **Step 2: Run repository-owned deterministic gates**

```bash
make api-check
./scripts/doctor.sh
git diff --check
```

Expected: PASS. If the repository exposes Semgrep through its authoritative checks, it must pass; otherwise record that no repository-owned Semgrep command is available rather than introducing unrelated tooling.

- [ ] **Step 3: Run independent specification-compliance review**

Give a fresh reviewer only the approved spec, plan, and complete diff. Require explicit coverage of target sequencing, provider binding, persistent/ephemeral state, unchanged verifier, sanitization, cleanup, and non-live CI boundaries. Remediate confirmed findings and rerun focused tests.

- [ ] **Step 4: Run independent code-quality and security review**

Give another fresh reviewer the diff without the first reviewer's verdict. Require review of URL parsing, redirect handling, secret lifetime/exposure, raw exception containment, cleanup state transitions, provider response validation, and test strength. Remediate confirmed findings and rerun deterministic gates.

- [ ] **Step 5: Run the explicit live Development validation**

Only after offline gates and review pass, manually configure the persistent smoke-user ID and both development authorized-party settings, then invoke:

```bash
make api-auth-smoke
```

Enter the `sk_test_` credential only at the hidden prompt. Confirm sanitized stage output, exact `/api/me/` success, and cleanup completion. Do not capture or paste the secret, ticket, token, Clerk IDs, TailTag ID, claims, headers, or raw responses into logs or completion notes.

- [ ] **Step 6: Re-run final cheap checks and inspect the complete diff**

```bash
git diff --check origin/main...HEAD
git status --short
git log --oneline origin/main..HEAD
```

Expected: only issue #99 files and intentional commits are present; no credential, generated artifact, or ephemeral resource data is tracked.

- [ ] **Step 7: Commit any reviewed remediation**

```bash
git add <only-reviewed-issue-99-files>
git commit -m "fix(auth): address issue 99 review findings"
```

Skip this commit when review requires no changes.

## Rollback

Rollback removes the `api-auth-smoke` Make target, its two root scripts, the new test-support module/tests, and the related documentation/config examples. No migration or production authentication behavior needs reversal. The dedicated Clerk Development user and corresponding TailTag development user are intentional external test state; deleting either is a separate explicit Development-operator decision, not an automated rollback action.
