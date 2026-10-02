# Headless acceptance and simulation harness

Issue: [#218](https://github.com/TailTag-Game/tailtag/issues/218) (SIM-1).
Parent: #199. Decision: [ADR 0008](../adrs/0008-use-asyncio-httpx-for-headless-simulation.md).
Staging foundations consumed: #200 (Staging), #201 (`/health/identity`), #203
(environment safety). Later consumers: #219 to #230.

Amendment (#219, 2026-10-02): the
[synthetic simulation identity pool](2026-10-02-synthetic-identity-pool.md)
spec (decision D5) replaces decision 7's strictly sequential phases and A-4's
single token: SIMULATION receives per-user token providers, refreshed by a
setup-owned component that runs alongside it. A-10 is unchanged.

## Status and phase ledger

Execution: STANDARD EXPANDED. Assurance: SECURITY (bearer tokens, target
safety, privilege boundary), RELIABILITY (fail-closed target validation).
Completed: scope review and research; maintainer approval of decisions 1 to 10
below (2026-10-02), with decision 1 revised after research (see decision 1).
Implemented 2026-10-02: tests by an independent author, implementation by an
independent implementer, then independent review (no BLOCKER or HIGH). Review
fixes: M-1 the client refuses paths resolving to another origin; M-2 a size-cap
test; L-1 ignore rules; L-2 container local-host notes; N-1 documented
`source_sha` output.
Live Staging smoke passed (2026-10-02): the maintainer ran `make sim-smoke
TARGET=staging` with a synthetic user's portal token. Output: `PASS target
staging source_sha=b1d8a7e0b3a16c8d64c36442f93ebbc70e2a36eb`, then `PASS setup`,
`PASS simulation`, and `PASS reconciliation`. A live local run was not made.

## Objective

Establish `tools/simulator/`, the repository-owned black-box client that later
#199 children extend. It proves the boundary with one manually invoked,
authenticated `GET /api/me/` smoke run against a local API or Staging.

## Decisions

1. **Staging authentication is operator-supplied in #218.** The #200 spec
   forbids Backend session creation, Backend token minting, sign-in tickets,
   a Frontend API client, and origin spoofing for Staging, and Staging accepts
   only the hosted Account Portal `azp`. The harness therefore takes an
   ordinary session token from a hidden TTY prompt in SETUP, the same source
   the #200 smoke uses. The simulator holds no Clerk secret and has no Clerk
   dependency. Automated Staging minting and its authorized-party decision are
   deferred to #219 (identity pool), which needs them anyway. The originally
   approved Staging ticket sign-in spike is withdrawn (maintainer, 2026-10-02).
2. **Long-lived tokens are deferred.** A smoke run makes two requests within
   the 60-second ordinary token lifetime. Token lifetime and refresh belong to
   #219 and #221.
3. **Package location.** `tools/simulator/` with its own `pyproject.toml`,
   `uv.lock`, and `Dockerfile`, on Python 3.13 and uv 0.9.17 like the API.
   It is not a deployed service and does not run inside the API environment.
4. **Tool.** Custom asyncio with httpx, recorded in ADR 0008.
5. **Boundary enforcement.** The simulator's locked environment excludes
   Django, PostgreSQL drivers, ORMs, and the Clerk SDK, and a test proves they
   are not importable. A simulator-only Semgrep rule set rejects those imports,
   dynamic imports, and HTTP mock transports in package code.
6. **CI.** `make sim-check` runs format, lint, strict Pyright, tests, and the
   simulator Semgrep rules. A path-filtered workflow runs it and builds the
   image. No Dependabot change.
7. **Phases.** SETUP, SIMULATION, and RECONCILIATION are three functions run in
   order, each receiving only its own context. There is no plugin registry.
8. **Target safety.** A closed target set (`local`, `staging`) plus two
   agreeing `/health/identity` reads before any bearer token is sent. Limits,
   abort thresholds, and confirmations remain #227.
9. **Smoke request.** `GET /api/me/`. On first use of a Clerk identity the API
   creates its application user (`accounts/resolution.py`); that idempotent
   write is the only side effect. Profile endpoints are not called.
10. **Rehearsal baseline.** `services/api/rehearsal/` is untouched. Future
    simulation state must stay disjoint from the #204 baseline.

## Acceptance contract

- A-1 `tools/simulator/` is a separate uv project. Its README documents the
  boundary: separate from Django code and backend tests, public API only during
  SIMULATION, privileged access only in SETUP and RECONCILIATION.
- A-2 `make sim-smoke TARGET=local` and `make sim-smoke TARGET=staging` (and
  the equivalent container invocation) run SETUP, SIMULATION, and
  RECONCILIATION in order and exit 0 only when every phase passes.
- A-3 SETUP validates the target, then obtains a bearer token from a hidden
  TTY prompt. Without a TTY it fails closed. A value that is not three
  non-empty base64url segments is rejected before any request carries it.
- A-4 SIMULATION receives only a public API client bound to the validated
  origin and token; a path resolving to any other origin is refused unsent. It cannot reach SETUP inputs, prompts, or anything
  privileged. It makes two `GET /api/me/` requests.
- A-5 RECONCILIATION receives only the recorded observations. It passes only
  when both responses were 200 JSON objects whose `id` is the same positive
  integer. Privileged read access is a documented #222 extension point, not
  built here.
- A-6 Target names other than `local` and `staging` are rejected; there is no
  way to name Production or Development. `staging` is exactly
  `https://staging.tailtag.app` with no override. `local` accepts only
  `http://127.0.0.1:8000` (default), `http://localhost:8000`, and
  `http://host.docker.internal:8000`.
- A-7 Before the token prompt, two `/health/identity` reads must each be a 200
  JSON object with exactly `source_sha`, `deployment_id`, and `environment`,
  and must agree. `staging` requires `environment` `staging`, a 40-character
  lowercase hex `source_sha`, and a canonical UUID `deployment_id`. `local`
  requires `environment` and `deployment_id` to be null. Anything else fails
  closed.
- A-8 No request follows redirects; a redirect is a failure. Responses are
  read with a size cap and a timeout.
- A-9 Output is a fixed set of phase and stage lines. The target line may show
  the verified public `source_sha`. Tokens, other response content, and user IDs
  never appear in output or exceptions.
- A-10 The simulator environment cannot import `django`, `rest_framework`,
  `psycopg`, `psycopg2`, `asyncpg`, `sqlalchemy`, or `clerk_backend_api`.
- A-11 `make sim-check` passes and includes the simulator Semgrep rules and
  their fixtures. `make sim-image` builds the container. CI runs both for
  relevant changes.
- A-12 ADR 0008 records asyncio with httpx and the rejected alternatives.
- A-13 No API, Production, Development-load, frontend, or gameplay change.

## Test surface contract

Tests live in `tools/simulator/tests/` and run with pytest in the simulator
environment. The external HTTP boundary is replaced with
`httpx.MockTransport`, and the token prompt with an injected callable. These
are the only substitutes; phase and target code run for real.

Failure modes to protect:

- An unknown, Production-like, or overridden target is accepted (A-6).
- A bearer token is sent before or despite a failed identity check, including
  disagreeing reads, wrong environment, extra keys, or a non-200 (A-7).
- A token is sent to a redirect location (A-8).
- A malformed token is sent (A-3).
- SIMULATION results are reported as passing when `/api/me/` returned 401,
  non-JSON, or differing IDs (A-5).
- A token or response body leaks into output (A-9).
- A forbidden library becomes importable (A-10).

The Semgrep rules are proven by `ruleid`/`ok` fixtures under `.semgrep/`.

## Scope guard

Expected files: `tools/simulator/**`, `.semgrep/simulator-rules/**`,
`.semgrep/simulator-tests/**`, `.github/workflows/simulator.yml`, `Makefile`,
`docs/adrs/0008-*.md`, this spec, and short pointers in existing docs.

Non-goals: Clerk minting or an identity pool (#219), fixtures (#220),
journeys (#221), privileged reconciliation (#222), cleanup (#223), scenarios
and seeds (#224), personas and traffic (#225, #226), guardrail limits (#227),
the execution host (#228), and any change to `scripts/` or `services/api/`.

Reversibility: two-way door. The package is additive and no runtime consumes
it. ADR 0008 is the only durable commitment and can be superseded.
