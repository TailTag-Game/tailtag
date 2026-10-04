# TailTag simulator

The repository-owned, black-box client for headless acceptance runs and, in later
issues, convention-scale simulation (#199). It is plain Python asyncio with httpx
([ADR 0008](../../docs/adrs/0008-use-asyncio-httpx-for-headless-simulation.md)).
Today it runs a manually invoked, authenticated `GET /api/me/` smoke against a local
API or Staging, manages a Staging synthetic identity pool, provisions per-run
simulation fixtures on Staging, runs the 13 V0 acceptance journeys against them, and
cleans up or retains each run's state. Design: [spec](../../docs/specs/2026-10-02-headless-simulation-harness.md).

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
    for `smoke`, or one client per pool identity (`pool-smoke`, `fixture-smoke`, `journeys`), each with an opaque token provider
    that returns only a current ordinary token. It has no prompt, no setup inputs, no
    lease channel, and no privileged access. Public API only.
  - RECONCILIATION gets only the recorded observations. For `journeys` (#222) it gets
    three things: the expectations, the role-to-client and role-to-index maps (the
    clients only for history reads), and the read-only inspection channel.
- Privileged access belongs only in SETUP, RECONCILIATION and the run's final CLEANUP or
  RETAIN. Fixture setup (#220) extends SETUP; privileged read-only reconciliation (#222)
  extends RECONCILIATION; cleanup and retention (#223) run after RECONCILIATION, once
  SIMULATION has finished. There is no plugin registry.
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
  a 65536-byte cap (a page of presigned image URLs is tens of KB) and a 10-second timeout.
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
host-only Staging proof and the template that the journeys below extend. Like the pool
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
  PASS cleanup <counts>
  PASS release
  ```

  `PASS cleanup` and the lifecycle lines around it are described under
  [Run lifecycle](#run-lifecycle). Database IDs, Clerk IDs, handles, media keys, photo
  URLs, tokens, and secrets are never printed. The exit code is 0 only if every line
  passed.
- **Failures:** provisioning refusals print one line and the run still releases its
  leases: `FAIL setup result=<CODE>`, with ` quarantined=<n>` after `FAIL_DIRTY`.
  A shortfall or unusable identity prints the pool smoke's `FAIL setup needed=... available=...`
  or `FAIL setup quarantined=<i,j,...>`; any other setup error prints a plain
  `FAIL setup`. Public reads that cannot complete print `FAIL simulation`; state that does not
  match prints `FAIL reconciliation` (and the run is retained, see
  [Run lifecycle](#run-lifecycle)); leases that cannot be released print
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
  or may not exist and stored images may remain as unattributable
  [orphans](#limitations). Check `status`
  for the run ID before assuming either way.
- **Ledger and hand-off:** every created object (Convention, enrollments, fursuits
  with their media keys, activations) gets one `FixtureObject` row under a
  `FixtureRun` keyed by run ID. Reconciliation (#222) and cleanup (#223) find a run's
  objects through that ledger. `status` returns the run status and counts per kind,
  never IDs or keys. There is no CLI wrapper; send the
  request to the launcher on stdin from the repository root:

  ```bash
  printf '{"operation":"status","arguments":{"run_id":"<run id>"}}' | make -s api-sim-fixture-ssh
  ```

  An unknown run ID returns `FAIL_RUN_UNKNOWN`.
- **Cleanup:** a passing run deletes its own state, and a failing run is retained. See
  [Run lifecycle](#run-lifecycle).
- **Repeated runs on one pool:** a passing run cleans its identities and releases them
  clean, so the next run on the same pool provisions them again. A failing run
  quarantines its identities and keeps its state until `sim-cleanup` readmits them. A
  `pool readmit` makes a slot allocatable again but does not remove its fixtures, so
  an identity that still owns state fails `provision` with `FAIL_DIRTY`.
- **Relationship to #204:** the rehearsal baseline stays untouched. A fixture run never
  reads or changes the baseline Convention, its users, its fursuits, or its media key,
  and pool identities stay disjoint from them. Every run fursuit gets its own newly
  stored image.
- **Not created here:** no catch sessions, catch credentials, or avatars. Those are
  fursuiter behavior that the journeys perform through the public API.

## Run lifecycle

`fixture-smoke` and `journeys` share one lifecycle (#223,
[spec](../../docs/specs/2026-10-03-simulation-cleanup.md)). A passing run cleans itself.
A failing run is retained so the state can be investigated, and a maintainer cleans it
later.

```text
PASS cleanup convention=<n> enrollment=<n> fursuit=<n> activation=<n> catch=<n> session=<n> credential=<n> image=<n>
FAIL cleanup result=<CODE>
RETAIN reason=<reason> quarantined=<n>
FAIL retain
WARN retained=<n> unfinished=<m>
```

- **CLEANUP** runs after RECONCILIATION and before RELEASE, only when setup, every
  journey and reconciliation passed. It goes through the fixture channel while every
  slot is still leased, deletes exactly the run's state (its Convention, enrollments,
  fursuits, activations, catches, catch sessions and credentials, and its images),
  verifies that every identity is clean again; RELEASE then frees the slots. Pool users and
  profiles survive. Cleanup refuses and changes nothing when the state is not provably
  the run's own (`FAIL_ATTRIBUTION`), which includes anything touching the #204
  baseline.
- **RETAIN** runs once provision has passed and the run did not pass: it quarantines
  the run's slots and keeps all state in place. The ledger row becomes `retained` with
  one reason: `journeys` (a journey failed and reconciliation completed, including a
  mismatch or a failed `inspect`), `reconciliation` (a mismatch or failed `inspect`
  with every journey passing, or a reconciliation stage error such as an unknown
  Convention),
  `cleanup` (CLEANUP failed), or `interrupted` (any other exception or an interrupt, including a failed fixture-smoke
  SIMULATION). A failed retain prints `FAIL retain`. RELEASE still ends the Clerk
  sessions and runs last. A setup failure before provision passes behaves as before:
  nothing is cleaned or retained.
- **Cap:** before leasing anything, the run asks which runs are retained or
  unfinished. At 5 or more retained runs it prints `FAIL setup
  result=FAIL_RETAINED_LIMIT` and leases nothing, so clean some with `sim-cleanup`
  first. When any run is retained or unfinished below the cap, it prints the `WARN`
  line and goes on. An unfinished run is a crashed run, or one from before #223, that
  has no live lease.
- **Report:** the run's fixed stdout lines, starting at `RUN run_id=`, are its report;
  capture them. The ledger row keeps its status, reason, counts and times. A report
  file is #224's.

### Maintainer commands

```bash
make sim-retained                          # list retained and unfinished runs
make sim-cleanup POOL=p1 RUN_ID=<run id>   # clean one run and readmit its identities
```

Both are host-only, need no Clerk secret and no API target, and exit 0 only after a
`PASS` line.

```text
RETAINED run_id=<id> pool=<p> reason=<reason|unfinished> age_days=<d>    (one per run)
PASS retained retained=<n> unfinished=<m>
PASS cleanup <the eight counts> readmitted=<n>
FAIL retained result=<CODE>
FAIL cleanup result=<CODE>
```

`sim-cleanup` works on a `retained` or `provisioned` run (not one that is `cleaned` or
`failed`). It readmits the run's quarantined slots, and clears expired leases,
only after the cleanup verified clean; it never readmits after a failed one. A
`FAIL_STORAGE` run can be re-run and resumes at the image phase.

| Result | Meaning |
| --- | --- |
| `FAIL_ATTRIBUTION` | Cleanup refused and changed nothing: the run is already cleaned or failed or in another pool, a slot is leased to another run, state exists outside the run Convention, an image key is shared or is the #204 key, or an identity cannot be resolved. |
| `FAIL_RUN_UNKNOWN` | The run ID has no ledger row. |
| `FAIL_STORAGE` | Rows are deleted but an image object is not confirmed gone. Re-run `sim-cleanup`. |
| `FAIL_VERIFY` | An identity is still dirty or a row still references the run Convention. Nothing is readmitted. |
| `FAIL_ERROR` | An unexpected error. Anything not yet committed rolled back; rerun `sim-cleanup`. |
| `FAIL_LIMIT` | `retained` only: more than 100 runs to list. |
| `FAIL_RETAINED_LIMIT` | In a run: 5 or more runs are retained, so nothing is leased. |

### Cleaning runs from before #223

A run from before #223 recorded no identities, so `sim-cleanup` derives them from the
run's enrollments and cleans under the same rules; an identity that cannot be resolved
is `FAIL_ATTRIBUTION`. Such runs appear in `sim-retained` as `unfinished`. Their
outsider slot (the 7th identity of a `journeys` run) was never recorded and is not
readmitted by cleanup: readmit it with `make sim-pool-readmit POOL=<pool> INDEX=<i>`.

### Limitations

- **Orphan images:** some stored images cannot be attributed to a run, and are logged
  but never deleted: objects a domain service failed to delete after replacing or
  removing an image, and images stored by a `provision` whose commit outcome was
  unknown (`FAIL_BOOTSTRAP`).
- **Hard crash:** if the process dies before RETAIN, the run's slots keep their leases
  until they expire (1800 seconds). It then shows as `unfinished`, and the next
  `provision` still quarantines any dirty identity.

## Journeys

`journeys` proves the implemented V0 gameplay and image contract end to end through the
real Clerk authentication boundary and the public API only (#221,
[spec](../../docs/specs/2026-10-03-headless-acceptance-journeys.md)). It is host-only
and Staging-only, like `fixture-smoke`, and has nothing to configure.

```bash
make sim-journeys POOL=p1
```

- **Prerequisites:** the [pool](#identity-pool) and [fixture](#simulation-fixtures)
  prerequisites, plus 7 clean identities. The run leases 7 and provisions the first 6
  through the fixture channel (2 owners with 2 fursuits each, 4 catchers); the 7th is
  an onboarded outsider with no enrollment, passed to `provision` as an extra and
  checked clean. Identities left by a retained or pre-#223 run are dirty until
  `sim-cleanup` cleans them.
- **Journeys, in order:** `unauthenticated` (no token and a malformed bearer get 401),
  `catch` (session, credential, resolve, confirm, history), `retry` (a repeat confirm
  is `already_caught` with the same catch, also after the session stops),
  `stopped_session`, `stale_credential` (a rotated credential stops working),
  `deactivated`, `self_catch`, `convention_mismatch` (the catcher's active Convention is
  cleared, then restored even if the check fails), `ineligible_catcher`, `not_owner`
  (404), `avatar`, `fursuit_photo`, and `image_rejections` (GIF, non-image bytes, and a
  5001x5001 PNG are each rejected with 400). Each journey arms the state it needs through
  idempotent owner calls and stops at its first failed step; the rest still run.
- **Images:** valid images come from `services/api/simulation_fixtures/images/` in
  filename order, or two generated PNGs when that folder has none. Only leased
  identities' avatars and the fursuit that `fursuit_photo` creates are changed; #220
  fixture photos never are. No image URL is fetched.
- **Output:** fixed lines only, after the [fixture-smoke](#simulation-fixtures) target,
  `RUN` and `PASS setup identities=7 fursuits=4` lines:

  ```text
  PASS journey=<name>
  FAIL journey=<name> step=<step> expected=<status>/<code> observed=<status>/<code>
  PASS journeys passed=13        (or FAIL journeys failed=<n>)
  <reconciliation lines>         (see Reconciliation)
  PASS cleanup <counts>          (or RETAIN reason=<reason> quarantined=<n>; see Run lifecycle)
  PASS release
  ```

  `<code>` is a confirm outcome, a domain error code, an image rejection name, `-` when
  none is expected, or `other`. `observed` is `<status>/shape` when the status matched
  but the body did not, and `error` when there was no response (timeout, size cap,
  redirect). Setup and release failures print the `fixture-smoke` lines. Tokens,
  payloads, URLs, names, IDs, and body text are never printed. The exit code is 0 only
  if setup, every journey, reconciliation, cleanup, and release passed.
- **Cleanup consequence:** the run leaves catches, sessions, rotated credentials, one
  deactivated activation, the created fursuit and its photos, and stored-then-cleared
  avatars. A passing run [cleans](#run-lifecycle) all of it and its identities are
  clean again; a failing run is retained with them quarantined.
- **Covered only by API tests:** the 12 hour session expiry, the 10 MiB upload limit,
  and concurrent confirmation are not exercised over the network. They are covered by
  API pytest.

## Reconciliation

After the journeys, `journeys` proves that the simulator's expected state, the Catch
rows on Staging and each run identity's public catch history agree (#222,
[spec](../../docs/specs/2026-10-03-simulation-reconciliation.md)). It runs inside
`make sim-journeys` once SETUP has passed, whether the journeys passed or failed, and
always before the leases are released.

- **What is checked:** the journeys record every confirm they attempt, and the
  `catch` and `retry` journeys record what the API reported. One read-only `inspect`
  call, relayed over SSH to the pinned Staging instance (`make api-sim-inspect-ssh`),
  returns the run's Catch rows, fursuits and avatars from the database. Each of the 7
  identities also reads its own `GET /api/catches/` history. The comparison fails on:
  `contamination`, `duplicate`, `missing`, `unexpected`, `catch_id`, `caught_at`,
  `provenance`, `window`, `history`, `count`, `fixture_photo`, `created_fursuit`, and
  `avatar`. The world is closed: a catch no journey accounts for is a discrepancy.
- **Output:** fixed lines after the journey lines and before `PASS release`. IDs,
  pool indexes, timestamps, URLs and bodies are never printed:

  ```text
  PASS reconciliation checks=14
  FAIL reconciliation result=<FAIL_*>                       (inspect itself failed)
  FAIL reconciliation check=<check> journey=<name|-> role=<role|-> expected=<n> observed=<n>
  FAIL reconciliation discrepancies=<n>
  ```

  If the run Convention is unknown and catcher0 cannot read it, the run prints
  `FAIL reconciliation`. A failed reconciliation retains the run (reason
  `reconciliation`, or `journeys` if a journey failed and reconciliation still
  completed). The exit code is 0 only if setup, every journey, reconciliation, cleanup
  and release passed.
- **Prerequisites:** unchanged from [Journeys](#journeys), plus one more SSH call
  through the same Railway CLI access. `inspect` only reads, so nothing else needs to
  be provisioned or promoted by hand beyond the merged code.

## Later issues

Scenarios, seeds and run reports (#224), personas and traffic (#225, #226), guardrail
limits (#227), and the execution host (#228).
