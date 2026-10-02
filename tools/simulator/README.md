# TailTag simulator

The repository-owned, black-box client for headless acceptance runs and, in later
issues, convention-scale simulation (#199). It is plain Python asyncio with httpx
([ADR 0008](../../docs/adrs/0008-use-asyncio-httpx-for-headless-simulation.md)).
Today it runs a manually invoked, authenticated `GET /api/me/` smoke against a local
API or Staging, and manages a Staging synthetic identity pool. Design: [spec](../../docs/specs/2026-10-02-headless-simulation-harness.md).

## Boundary

- This is a separate uv project (`pyproject.toml`, `uv.lock`, `Dockerfile`). It is
  not a Django app, runs outside the API environment, and never imports `services/api`
  or `scripts/`. Its locked environment excludes Django, DRF, PostgreSQL drivers,
  SQLAlchemy, and the Clerk SDK; a test proves they are not importable and the
  simulator Semgrep rules (`.semgrep/simulator-rules/`) reject those imports, dynamic
  imports, and mock transports in package code.
- A run has three phases, each a function that receives only its own context
  (`tailtag_simulator/phases.py`, `pool.py`):
  - SETUP gets the verified target and the token prompt and returns credentials. In a
    pool run it also holds the Clerk Staging secret and the lease channel, only while
    SETUP runs; the secret is never stored.
  - SIMULATION gets only public API clients bound to the verified origin: one token
    for `smoke`, or one client per pool identity, each with an opaque token provider
    that returns only a current ordinary token. It has no prompt, no setup inputs, no
    lease channel, and no privileged access. Public API only.
  - RECONCILIATION gets only the recorded observations.
- Privileged access belongs only in SETUP and RECONCILIATION. Fixture setup (#220)
  extends SETUP; privileged read-only reconciliation (#222) extends RECONCILIATION.
  There is no plugin registry.
- Pool commands are host-only. The lease channel needs the Railway CLI and the owner
  manifest, so they run from a maintainer machine through `make`, not in the container
  image.

## Targets and safety

- Targets are a closed set: `local` and `staging`. Production and Development cannot
  be named. `staging` is exactly `https://staging.tailtag.app` with no override.
  `local` accepts `http://127.0.0.1:8000` (default), `http://localhost:8000`, and
  `http://host.docker.internal:8000` through `--base-url`.
- Before the token prompt, two `/health/identity` reads must each be a 200 JSON object
  with exactly `source_sha`, `deployment_id`, and `environment`, and must agree.
  Staging requires environment `staging`, a 40-character lowercase hex `source_sha`,
  and a canonical UUID `deployment_id`. Local requires `environment` and
  `deployment_id` to be null. Anything else fails closed.
- Redirects are never followed and any redirect is a failure. Responses are read with
  a 4096-byte cap and a 10-second timeout.
- Output is fixed stage lines (`PASS target <name>`, `PASS setup`, `PASS simulation`,
  `PASS reconciliation`, or `FAIL <stage>`). `PASS target` also shows the verified
  public `source_sha` when the API reports one. Tokens, other response content, and
  user IDs are never printed. The exit code is 0 only if every stage passed.
- The token is read from a hidden TTY prompt only. Without a TTY the run fails closed;
  there is no environment-variable or argument input. A token must be three non-empty
  base64url segments, or it is rejected before any request carries it.

## Getting a token

`smoke` holds no Clerk secret and cannot mint tokens. Automated tokens for pool
identities come from the identity pool below.

- **Staging:** this follows the token handling #217 used against replacement Staging
  (see the [Staging runbook](../../docs/development/staging.md)). Disable clipboard
  history and sync, sign a marked synthetic user in at the hosted Staging Account
  Portal (`https://accounts.staging.tailtag.app`), and only when the simulator
  prompts, run `copy(await Clerk.session.getToken({skipCache:true}))` in that page's
  browser console. Paste it only into the hidden prompt, clear the clipboard, and sign
  out afterwards. Never put a token in an argument, environment variable, file, log,
  or chat. Ordinary tokens last about 60 seconds, enough for the two requests of a run.
- **Local:** the local API must run with Clerk authentication enabled
  (`CLERK_AUTHENTICATION_ENABLED`, `CLERK_JWT_KEY`) and a `CLERK_AUTHORIZED_PARTIES`
  value that matches the token's `azp`; see `services/api/.env.example`.

`GET /api/me/` creates the application user on first use of a Clerk identity
(`accounts/resolution.py`). That idempotent write is the only side effect. Profile
endpoints are not called.

## Commands

Run from the repository root.

```bash
make sim-setup                      # sync locked dependencies
make sim-check                      # format, lint, strict Pyright, tests, Semgrep
make sim-smoke TARGET=local         # optional BASE_URL=http://localhost:8000
make sim-smoke TARGET=staging
make sim-image                      # build tailtag-simulator:local
docker run --rm -it tailtag-simulator:local smoke --target local --base-url http://host.docker.internal:8000
```

The container needs `-it` so the hidden prompt has a TTY. For the local target, the
local API must also accept the `host.docker.internal` host: add it to
`DJANGO_ALLOWED_HOSTS`, or Django answers 400 and the run fails at `target`. On Linux,
also pass `--add-host=host.docker.internal:host-gateway` to `docker run`. No secrets are baked into the
image. CI (`.github/workflows/simulator.yml`) runs `make sim-check` and `make sim-image`
with no secrets and no network target.

## Identity pool

A durable pool of synthetic Staging identities that a run leases, uses through the real
authentication boundary, and releases (#219,
[spec](../../docs/specs/2026-10-02-synthetic-identity-pool.md)). Pool commands run only
from a maintainer machine with the Railway CLI, and only against Staging.

```bash
make sim-pool-provision POOL=p1 SIZE=50   # create missing users and slots; idempotent
make sim-pool-status POOL=p1              # counts only
make sim-pool-smoke POOL=p1 COUNT=3       # allocate, GET /api/me/ across a token lifetime, release
make sim-pool-readmit POOL=p1 INDEX=7     # re-admit a repaired quarantined identity
```

- **Prerequisites:** canonical Staging readiness requires both authorized parties, so
  the variable and the code must change together, in this order: merge; stage
  `CLERK_AUTHORIZED_PARTIES=https://accounts.staging.tailtag.app,https://simulator.staging.tailtag.app`
  with `--skip-deploys` (applying it without that flag redeploys `main` outside
  controlled promotion); promote the merged SHA through controlled promotion, which
  applies the `simulation_pool` migration; confirm readiness; then provision. Roll
  back the variable and the code together. Provision and `pool-smoke`
  prompt for the Clerk Staging secret on a hidden TTY (`Clerk Staging secret:`). It is
  used for SETUP only and is never stored.
- **Names:** a pool name is 1 to 12 lowercase letters or digits. Index `i` is Clerk
  external ID `sim-pool-<pool>-<i>` and profile handle `sp_<pool>_<i>`.
- **Run:** `pool-smoke` leases `COUNT` identities, revokes their leftover sessions,
  signs each in with a single-use ticket, onboards never-onboarded profiles once through
  `PUT /api/profile/`, then calls `GET /api/me/` before and after one token lifetime. It
  always ends the sessions and releases the leases, even after a failure. Output is
  `PASS`/`FAIL` stage lines and counts only.
- **Insufficient pool:** if fewer than `COUNT` identities are available, nothing is
  leased and the run prints `FAIL setup needed=<COUNT> available=<n>`. Check
  `pool status`, then provision more or readmit.
- **Quarantine:** an identity whose Clerk user is missing, banned, locked, or unmarked,
  whose sign-in fails, or whose profile has drifted is quarantined and excluded from
  allocation. The run releases the rest and prints
  `FAIL setup quarantined=<i,j,...>` with the indexes in ascending order. To recover,
  inspect those users in the Clerk Staging dashboard (external ID
  `sim-pool-<pool>-<i>`), repair or retire each, then run
  `make sim-pool-readmit POOL=<pool> INDEX=<i>`. Quarantine never deletes anything. If
  every allocated identity fails, none is quarantined (that points at the environment,
  not the identities); the run releases all of them and prints a plain `FAIL setup`.
- **Crashed run:** leases expire after 1800 seconds and become reclaimable. Leftover
  Clerk sessions are revoked the next time the identity is allocated.
- **Baseline:** pool identities never enroll in the #204 rehearsal baseline Convention or
  touch its fursuits. Pool runs call only `/api/me/` and `/api/profile/`.

## Later issues

Fixtures (#220), journeys (#221), privileged reconciliation
(#222), cleanup (#223), scenarios and seeds (#224), personas and traffic (#225, #226),
guardrail limits (#227), and the execution host (#228).
