# TailTag simulator

The repository-owned, black-box client for headless acceptance runs and, in later
issues, convention-scale simulation (#199). It is plain Python asyncio with httpx
([ADR 0008](../../docs/adrs/0008-use-asyncio-httpx-for-headless-simulation.md)).
Today it runs a manually invoked, authenticated `GET /api/me/` smoke against a local
API or Staging, manages a Staging synthetic identity pool, and provisions per-run
simulation fixtures on Staging. Design: [spec](../../docs/specs/2026-10-02-headless-simulation-harness.md).

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
    for `smoke`, or one client per pool identity (`pool-smoke`, `fixture-smoke`), each with an opaque token provider
    that returns only a current ordinary token. It has no prompt, no setup inputs, no
    lease channel, and no privileged access. Public API only.
  - RECONCILIATION gets only the recorded observations.
- Privileged access belongs only in SETUP and RECONCILIATION. Fixture setup (#220)
  extends SETUP; privileged read-only reconciliation (#222) extends RECONCILIATION.
  There is no plugin registry.
- Pool and fixture commands are host-only. The lease and fixture channels need the
  Railway CLI and the owner manifest, so they run from a maintainer machine through
  `make`, not in the container image.

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

## Simulation fixtures

`fixture-smoke` gives one run its own synthetic Convention, enrollments, photo-bearing
fursuits, and activations on Staging, then proves them through public reads (#220,
[spec](../../docs/specs/2026-10-02-simulation-fixture-provisioning.md)). It is the
host-only Staging proof and the template that journeys (#221) extend. Like the pool
commands it runs only from a maintainer machine with the Railway CLI, only against
Staging.

```bash
make sim-fixture-smoke POOL=p1                                  # defaults: 2 owners, 1 fursuit each, 2 catchers
make sim-fixture-smoke POOL=p1 OWNERS=4 FURSUITS=3 CATCHERS=10
```

- **Configuration:** `POOL` is required; `OWNERS`, `FURSUITS`, and `CATCHERS` map to
  `--owners` (default 2), `--fursuits` (fursuits per owner, default 1), and
  `--catchers` (default 2). The API accepts 1 to 50 owners, 1 to 200 catchers, and 1 to
  5 fursuits per owner; anything else is `FAIL_REQUEST` and nothing is written. The
  run leases `OWNERS + CATCHERS` identities, uses the first `OWNERS` indexes as
  owners, and prompts for the Clerk Staging secret on a hidden TTY (`Clerk Staging
  secret:`). It is used for SETUP only and is never stored. The
  [pool prerequisites](#identity-pool) apply, plus the `simulation_fixtures`
  migration, which reaches Staging through controlled promotion.
- **Phases:** SETUP reuses the pool smoke's allocate-and-open step (instance pin,
  marker checks, session redemption, profile onboarding), then calls the fixture
  channel's `provision` once with the run ID, owner indexes, catcher indexes, and
  fursuits per owner. Provisioning runs after every identity is onboarded and before
  SIMULATION, so it never interleaves with a lease update; the fixture run sends no
  heartbeat. SIMULATION receives only per-identity public clients: each identity reads
  `GET /api/conventions/active/`, and each owner also reads `GET /api/fursuits/` and
  that Convention's `fursuit-activations/` list. RECONCILIATION passes only when every
  identity reports the same active Convention and each owner has exactly `FURSUITS`
  enabled fursuits with photo URLs, all activated in that Convention. The run always
  ends the Clerk sessions and releases the leases, even after a failure.
- **Output:** fixed lines only, plus the run ID and counts:

  ```text
  PASS target staging source_sha=<sha>
  RUN run_id=<uuid>
  PASS setup identities=<owners+catchers> fursuits=<owners*per owner>
  PASS simulation
  PASS reconciliation
  PASS release
  ```

  Database IDs, Clerk IDs, handles, media keys, photo URLs, tokens, and secrets are
  never printed. The exit code is 0 only if every line passed.
- **Failures:** provisioning refusals print one line and the run still releases its
  leases: `FAIL setup result=<CODE>`, with ` quarantined=<n>` after `FAIL_DIRTY`.
  A shortfall or unusable identity prints the pool smoke's `FAIL setup needed=... available=...`
  or `FAIL setup quarantined=<i,j,...>`; any other setup error prints a plain
  `FAIL setup`. Public reads that cannot complete print `FAIL simulation`; state that does not
  match prints `FAIL reconciliation`; leases that cannot be released print
  `FAIL release`.

| Result | Meaning |
| --- | --- |
| `PASS` | The run's state was created and committed. |
| `FAIL_REQUEST` | Malformed or out-of-range request, or an unexpected request shape. Nothing written. |
| `FAIL_TARGET` | The runtime is not the Staging `api` service with the exact requested identity. Nothing written. |
| `FAIL_RUN_EXISTS` | The run ID already has a ledger row, provisioned or failed. A run ID is used at most once. Nothing written. |
| `FAIL_LEASE` | A listed slot is not available, not leased to this run, or its lease expired, or a handle does not resolve to an onboarded profile. Nothing written. |
| `FAIL_DIRTY` | An identity still holds state from an earlier run. Each dirty identity is quarantined, the count is reported, and nothing else is written. |
| `FAIL_INVARIANT` | A domain service rejected a creation step. Everything is rolled back, stored images are deleted, and a `failed` run with no objects is recorded. |
| `FAIL_ERROR` | Any other error in a creation step, with the same rollback and `failed` run. |
| `FAIL_RUN_UNKNOWN` | `status` only: the run ID has no ledger row. |
| `FAIL_LAUNCHER` | The launcher could not run, timed out, or printed anything but the exact response shape. Raised by the simulator, with no detail. |
| `FAIL_BOOTSTRAP` | The remote program failed before it could return a result; see the commit-time failure below. |

- **Commit-time failure:** if the final transaction commit itself fails (for example,
  a lost connection), the outcome is unknown. The relay returns `FAIL_BOOTSTRAP`,
  writes no `failed` run, and does not delete the images it stored, so the rows may
  or may not exist and stored images may remain for #223 to reconcile. Check `status`
  for the run ID before assuming either way.
- **Ledger and hand-off:** every created object (Convention, enrollments, fursuits
  with their media keys, activations) gets one `FixtureObject` row under a
  `FixtureRun` keyed by run ID. #222 (reconciliation) and #223 (cleanup) find a run's
  objects through that ledger. Today only `status` reads it, and it returns the run
  status and counts per kind, never IDs or keys. There is no CLI wrapper; send the
  request to the launcher on stdin from the repository root:

  ```bash
  printf '{"operation":"status","arguments":{"run_id":"<run id>"}}' | make -s api-sim-fixture-ssh
  ```

  An unknown run ID returns `FAIL_RUN_UNKNOWN`. #223 owns deleting a run's objects and
  images, closing its Convention, and readmitting its identities.
- **Quarantine consequence:** fixtures stay in place after the run, so every identity
  it used now owns fursuits and enrollments. The next `provision` that includes one
  quarantines it (`FAIL_DIRTY`). A `pool readmit` makes the slot allocatable again but
  does not remove its fixtures, so the identity keeps failing `provision` with
  `FAIL_DIRTY` until #223 cleanup removes them.
- **Repeated runs on one pool:** a run releases its identities as available, and
  allocation hands out the lowest available indexes first. The next `fixture-smoke`
  on the same pool therefore gets those dirty identities back, fails with
  `FAIL_DIRTY`, and quarantines them. The run after that uses the next fresh
  indexes. Until #223 lands, expect each repeat to fail once before it passes, or
  use a separate pool for each run. `pool-smoke` is unaffected, since it never
  provisions.
- **Relationship to #204:** the rehearsal baseline stays untouched. A fixture run never
  reads or changes the baseline Convention, its users, its fursuits, or its media key,
  and pool identities stay disjoint from them. Every run fursuit gets its own newly
  stored image.
- **Not created here:** no catch sessions, catch credentials, or avatars. Those are
  fursuiter behavior that SIMULATION and journeys (#221) perform through the public API.

## Later issues

Journeys (#221), privileged reconciliation
(#222), cleanup (#223), scenarios and seeds (#224), personas and traffic (#225, #226),
guardrail limits (#227), and the execution host (#228).
