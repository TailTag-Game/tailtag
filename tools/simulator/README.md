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

## External Staging host

The [external simulation host runbook](../../docs/operations/simulation-host.md)
describes the approved DigitalOcean NYC3 host, immutable `linux/amd64` image
archive delivery, foreground maintainer SSH bridge, finite profiles, supervision,
artifact retrieval and exact-run recovery. Gameplay remains direct public HTTPS;
privileged Railway relays stay on the maintainer machine. Profile examples are in
`host/normal-profile.json` and `host/stop-profile.json`, with separate
`host/safety.json`. Preparation/offline evidence and separately authorized paid-host
provisioning/live traffic are distinct gates. No automatic restart or CI load run
is provided. `make sim-host-prepare` and `make sim-host-run` wrap foreground
manifest/session commands; `sim-host-release-export` and `sim-host-release-load`
wrap verified archive handoff. Prefer absolute path parameters: these wrappers
evaluate relative CLI paths from `tools/simulator`. The runbook prepares an
owner-private profile copy with an absolute safety-file path and establishes the
matching release cwd/Python in each separate host control session. Automatic
remote commands select that cwd too. Offline source verification has finite
time/output bounds and cleanup of its exact named probe; failed or interrupted
preflight cannot launch the workload. Use
`make sim-image PLATFORM=linux/amd64` for the host. Canonical `make sim-check` includes secret-free bootstrap syntax validation;
CI builds amd64 without running traffic. Existing local simulator commands retain
their launcher behavior.

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
make sim-check                      # catalog/history, format, lint, Pyright, tests, Semgrep
make sim-smoke TARGET=local         # optional BASE_URL=http://localhost:8000
make sim-smoke TARGET=staging
make sim-image                      # clean-source build of tailtag-simulator:local
mkdir -p tools/simulator/reports
# Use your host UID/GID so mounted reports remain writable and readable.
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD/tools/simulator/reports:/reports" tailtag-simulator:local smoke --target local --base-url http://host.docker.internal:8000 --report-dir /reports
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
  The check uses counts only, so a large unfinished backlog never blocks runs;
  `sim-retained` still fails with `FAIL_LIMIT` above 100 listed runs.
- **Report:** each execution creates a durable JSON report using the same run UUID
  as the lease and fixture ledger. Capture fixed stdout alongside it; the ledger
  keeps backend status, retention reason, counts and times. See [Run reports](#run-reports).

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

## Convention populations

Convention scenarios execute finite, stateful public API behavior on Staging.
Owners remain separate from casual, active, heavy and retry-prone attendees.
Normal and popular owners contribute configurable target weights. The families
are `baseline` (round-robin visits), `post-event` (grouped collection), `hotspot`
(one popular target), `retry` (first confirmations followed by duplicates), and
`soak` (finite repeated cycles over the same catch pairs).

```bash
make sim-convention POOL=p1 FAMILY=baseline SEED=42
make sim-convention POOL=p1 FAMILY=soak CONFIG=/path/to/population.json REPORT_DIR=/path/to/reports
# From tools/simulator:
uv run --locked --no-sync python -m tailtag_simulator convention --pool p1 --family retry --config /path/to/population.json --seed 42
```

The optional JSON object accepts behavioral parameters only. Example:

```json
{"casual":2,"active":1,"heavy":1,"retry_prone":2,"normal_owners":1,"popular_owners":1,"fursuits":2,"cycles":1}
```

Defaults are one of each persona, four fursuits per owner, budgets 1/3/8/3,
extra confirmations 0/0/0/2, history cadences 0/3/1/1 and target weights 1/4.
Cadence zero means completion history only. Default soak has three cycles;
other families have one. `activation_break` optionally deactivates between cycles.
The resolved configuration is recorded, and per-actor seeded choices use stable
logical ordinals. Backend IDs and run UUIDs do not affect target selection.

Synthetic limits are 1–50 owners, 1–200 attendees, 1–5 fursuits per owner,
1–200 target budgets, 0–10 extra confirmations, 0–200 history cadence,
1–100 target weights and 1–100 finite cycles. At most 200 distinct catches can
be requested. Zero-count personas are allowed when aggregate populations and
family requirements remain valid. Hotspot requires a popular owner; retry requires
a retry-prone attendee. Exhausted target budgets are reported without looping.
Unknown/duplicate keys, oversized JSON, boolean counts and routing overrides
(`pool`, `family`, `target`, `base_url`) fail before external work.

Orchestration renews every allocated lease independently every 60 seconds with a
30-minute TTL, starting during identity setup. Loss or count mismatch cancels and
awaits work before finalization. Provisioned failures retain fixtures; successful
runs clean up; release and session closure run last. Public behavior receives only
public clients. Read-only population inspection compares all actors' authoritative
state and complete histories before cleanup.

Historical version-1 convention reports use schema version 2, with six persona summaries and bounded
actor discrepancies. `completed` counts successful target visits, `created` first
catches, `already_caught` revisits and duplicates, `retries` extra confirmations,
`cycles` completed actor-cycles, and `unused_budget` unmet distinct-target budget
once per run. Owner completion counts armed fursuit sessions per cycle. Trace,
credentials, runtime IDs and raw responses are not persisted. The [literal v2
example](tests/data/report-v2-convention.json) and [approved design](../../docs/specs/2026-10-06-convention-virtual-users.md)
provide the exact historical contract. All supported report versions validate offline.

Version 1 records concurrency, arrival timing, traffic ramps, network failure
injection and elapsed-time soak as unavailable (`not_implemented`). Performance
measurements remain deferred for all versions. These
families establish behavioral evidence; they do not establish load capacity.
Live acceptance requires five small family proofs after separately approved
publication and Staging promotion; local boundary tests do not complete that gate.

### Opt-in convention traffic (version 2)

Use `VERSION=2` or `--scenario-version 2` to select concurrent, stateful traffic
with the historical schema-3 traffic fields. Omitting it preserves version-1
execution semantics. Guarded execution now writes schema 4 for both versions,
wrapping their existing results with the shared safety evidence.
The five new recipes are additive: distributed arrivals (`baseline`), a
concentrated release (`post-event`), overlapping confirmations on one target
(`hotspot`), selected client effects (`retry`), and elapsed-time repeated journeys
(`soak`). All population and timing defaults are synthetic assumptions.

```bash
make sim-convention POOL=p1 FAMILY=baseline VERSION=2 CONFIG=/path/to/traffic.json SEED=42
```

A bounded JSON configuration can combine configurable persona counts, target
budgets, extra-confirmation repeats and target weights with `traffic`, `failure`,
`retry`, and `limits`. Version 2 uses elapsed traffic to control actor reentry
and reads completion history after every entry. Its `cycles`, `activation_break`,
and `*_history` fields are fixed compatibility metadata: `cycles` is 3 for soak
and 1 for other families, `activation_break` is false, and `casual_history`,
`active_history`, `heavy_history`, and `retry_history` are 0, 3, 1, and 1,
respectively. Nondefault values are rejected before external work. Version 1
retains its configurable cycles, activation breaks and history cadence.
For example:

```json
{
  "traffic": {
    "mode": "arrivals",
    "segments": [{"duration_seconds": 2, "start": 0, "end": 4}],
    "bursts": [{"at_seconds": 1, "count": 2}],
    "think_seconds": 0.05
  },
  "failure": {"operations": ["confirm"], "lost_response_rate": 0.1},
  "retry": {"attempts": 3, "base_seconds": 0.25, "cap_seconds": 2},
  "limits": {"attempts": 5000, "active": 10, "in_flight": 10,
             "generation_seconds": 300, "drain_seconds": 15}
}
```

Active mode uses integral segment targets bounded by attendees and the active
ceiling. Arrivals that cannot be admitted are counted and skipped without a
backlog. Actors preserve state between entries; ordinary journeys for one actor
never overlap. The explicit hotspot duplicate experiment sends bounded overlapping
real confirmations. Soak revisits bounded pairs; all historical fixture and
200-distinct-catch inspection bounds still apply.

Effects cover selected reads, resolution and confirmation: pre-send delay/failure,
real response delay, and concealed lost/timeout-like responses. They never fabricate
backend replies or affect setup, authentication refresh, inspection or cleanup.
Retries reuse confirmation payloads; exhausted retries fail the workload even when
persisted correctness passes. `domain_case` selects `none`, `stale`, `stopped` or
`expired`; `recover_existing` separates canonical recovery from forbidden creation.
Natural expiration requires explicit duration/limits sufficient for the real
12-hour lifetime. Its long live proof is deferred to #230; no server clock changes
or database writes are used.

Historical schema 3 records resolved profiles, configured ceilings, an intended-plan digest,
bounded offered/admitted/skipped/completed timing buckets, peaks, lag, actual
generation/drain duration, and failure/retry/rejection/uncertainty counts.
Correctness and workload completion are separate: a safety stop or unresolved
submission cannot produce a passed run. Failed/interrupted runs retain fixtures
and release leases after task-owned work ends. Reports omit raw credentials,
identities, payloads, response bodies and unbounded traces. The seed and recorded
configuration reproduce intended choices/timing/effects with the same source and
runtime; actual network timing and completion ordering may differ.

These commands execute Staging work and require separate live-execution
authorization. Small Staging family/failure proof remains an explicit gate;
convention-scale readiness, latency/SLO analysis and the long expiration proof
are deferred. The [implementation contract](../../docs/specs/2026-10-07-convention-traffic.md)
defines the complete closed parameter and evidence shapes.

## Run reports

All five execution commands (`smoke`, `pool-smoke`, `fixture-smoke`, `journeys`, `convention`)
create one UUID-named UTF-8 JSON file. Pool administration, retained listing and
standalone cleanup do not create simulation reports. Host output defaults to
`tools/simulator/reports/` (Git ignored); containers default to `/reports`. Mount
that directory to keep reports after `docker run --rm`. A custom output directory
must be writable and should be outside version control. Reports are never
implicitly deleted or uploaded; operators control retention and export.

```bash
make sim-journeys POOL=demo VERSION=1 SEED=0 REPORT_DIR=/tmp/tailtag-reports
make sim-report-validate REPORT=/tmp/tailtag-reports/<run-uuid>.json
# Equivalent offline validation from the simulator project:
uv run --locked --no-sync python -m tailtag_simulator report validate /path/to/report.json
```

CLI options are `--scenario-version`, `--seed`, and `--report-dir`. Version 1 is
supported for each current command. Convention workloads consume the recorded integer
seed; the four legacy workloads record it without making random choices. There are
no scenario-specific traffic ramps or traffic budgets in version 1. Shared safety
ceilings apply to every command and supported version. Version 2 adds the bounded
traffic evidence described above; performance percentiles and SLOs remain deferred. Existing request,
response, launcher, lease and retention limits are recorded with their units and
actual enforcement scopes.

Report schema changes require a new `schema_version`, independently of scenario
versions. Supported older reports retain their original contract and meaning;
unsupported versions are rejected offline without conversion or reinterpretation.

Schema versions 1, 2 and 3 are strict: unknown fields, duplicate keys, invalid measurements,
unsupported versions, unsafe configuration and malformed files fail offline with
only `FAIL report`; valid files print only `PASS report`. Validation performs no
backend or provider requests. The [frozen design](../../docs/specs/2026-10-05-simulation-scenarios-run-reports.md)
and [literal schema-v1 example](tests/data/report-v1-smoke.json) describe the exact
nested fields. Reports contain scenario descriptor/digest, resolved configuration,
simulator/dependency identity, starting/final backend identity, population, operation
profile, scoped limits, UTC timestamps and monotonic durations, lifecycle phases,
correctness, sanitized result summaries and outcome/fixed failure code. Journey
items carry only approved names and pass/fail. Reconciliation `checks.count` means
checks performed; `checks.items` contains discrepancies only, so a successful
journeys report records 14 checks and an empty list. An inspection failure records
only the one inspection check reached. Cleanup records the eight
object-kind counts and the readmitted count.

Every unavailable measurement has a null value and a bounded reason:
`not_observed`, `not_applicable` or `not_implemented`. Throughput, latency percentiles,
resource context and load ramp are unavailable, rather than guessed. Reports never
contain credentials, provider/user/session IDs, fixture/database IDs, pool indexes,
handles, cookies, image/media URLs, raw payloads, exception text or launcher/Git
stderr. Synthetic pool names, logical roles, bounded counts and validated public
source/deployment identity are permitted. Review exported reports as operational
run evidence and store them under the team's retention policy.

The initial running file is reserved before source verification and any external
work. Dirty, unknown or missing simulator source prevents execution and leaves a
sanitized failed artifact when storage works. `make sim-image` uses the provenance
builder to validate clean source and copy approved inputs into a temporary context
with build-time metadata. Runtime SHA environment variables cannot relabel an image.
An initial report write failure prevents provenance and network calls. Recorder
updates validate against an isolated copy of the scenario admitted at run start.
Snapshot persistence and offline validation still check the versioned catalog.
Later snapshot failures, including missing or invalid catalog descriptors, preserve
the last complete file, set a sticky failure flag and prevent a passing exit.
Report-persistence failures prevent passing and permit bounded retention/release
only after fresh readiness and the pinned deployment are verified. Final identity
uncertainty prohibits further TailTag operations and records unfinished state for
manual recovery. Independently verified Clerk closure remains bounded by the
finalization reserve. The last durable snapshot may precede a persistence failure;
fixed operator output and the nonzero exit remain evidence of that failure.

Correctness is independent of attribution, cleanup, retention and release. A workload
can be correct while its overall run fails. After successful workload/reconciliation,
all five reported commands observe the backend identity again; changed or unverifiable
identity prevents passing attribution, and fixture cleanup is gated by it. Interrupts
finalize after resource obligations. A hard process crash or machine failure may leave
a valid running snapshot with unreached/incomplete phases; no handler can guarantee a
final report or release in that case. Use the existing retained/cleanup commands for
backend recovery. An unavailable output disk or damaged catalog can also leave only
the last snapshot. Validate retained reports from their recorded simulator revision
with its intact versioned catalog; repairing storage or the catalog does not erase a
report failure already observed during the run.

### Scenario versions and reproduction

Descriptors live in `tailtag_simulator/scenarios/<id>-v<version>.json` and are embedded
with a canonical SHA-256 digest. Committed versions cannot be changed or removed;
`make sim-catalog-check` checks structure, digests and available Git history, and
fails on shallow history. CI fetches full history. Review semantic workload changes
and create a new version when role/operation order, assumptions, waits, population
meaning, configuration meaning or backend contract interpretation changes. Changing
allowed count values, a seed that remains unused, or behavior-preserving source code
does not alone change scenario version. Source identity preserves executable history.

To reproduce an equivalent workload, retain the report and:

1. Check out its full `source.simulator_sha.value` in a clean checkout with full
   history, then run `make sim-setup` for that revision's locked Python environment.
   Compare the reported runtime and dependency-lock identity.
2. Read the embedded descriptor and digest, scenario ID/version, seed and resolved
   configuration. Use those same effective inputs with the corresponding command;
   do not substitute newer defaults.
3. Prepare fresh synthetic credentials and a clean compatible fixture/pool state
   using the existing maintainer procedures. Secrets are supplied only at hidden
   prompts. Old credentials or fixture IDs cannot be recovered from a report.
4. Provide a backend implementing the declared `tailtag-public-v0` API contract.
   Backend revisions can differ if their behavior remains compatible; review that
   compatibility and keep both identity observations as attribution evidence.
   Reports do not pin, redeploy or automatically launch a backend.
5. Run manually, validate the new artifact offline and compare workload inputs and
   correctness. Time, UUID, fresh credentials, deployment identity and durations
   will differ. This is workload equivalence, not a promise of identical timings,
   database rows or every runtime detail.

No command automatically checks out a revision or launches a reproduction.

## Later issues

Personas and traffic (#225, #226), guardrail
limits (#227), and the execution host (#228).

## Runtime safety and operator stop

Every execution command (`smoke`, `pool-smoke`, `fixture-smoke`, `journeys`, and
both convention versions) uses the shared safety runtime, even without a report.
Staging checks identity, readiness, and identity before phases and privileged
operations, pins the deployment for the run, and polls every 10 seconds. Local
smoke remains available only through explicit `--target local` and its allow-list.
One unavailable periodic probe pauses new traffic; a second aborts. HTTP 408/429
identity responses are unavailable, and non-200 readiness responses other than
redirects are unavailable. Redirects from either health endpoint abort immediately
without being followed. A healthy next probe resumes traffic. A changed or
malformed identity aborts immediately.

Use `--safety-config path.json` or `SAFETY_CONFIG=path.json` with the corresponding
Make target. The bounded JSON object accepts only the following fields; omitted
fields keep their defaults. Duplicate/unknown keys, nonfinite values, and values
outside allowed bounds fail before credentials or external work.

| Field | Default | Maximum |
| --- | ---: | ---: |
| `requests` | 10000 | 1000000 |
| `seconds` | 900 | 86400 |
| `in_flight` | 10 | 250 |
| `population` | 250 | 250 |
| `final_requests` | 1000 | 5000 |
| `final_seconds` | 600 | 1800 |
| `poll_seconds` | 10 | 30 (minimum 5) |
| `error_window_seconds` | 10 | finite positive |
| `error_min_samples` | 20 | positive integer |
| `error_percent` | 50 | 100 |
| `error_windows` | 2 | positive integer |

Public HTTP attempts include setup, probes, actual retries, and normal
reconciliation. Injected never-sent attempts remain in the separate traffic
budget. Probes have one reserved request slot, so the combined concurrency bound
is `in_flight + 1`. Finalization has one shared time/request reserve for the entire
recovery, without resetting it between operations. Clerk and launcher operations
consume elapsed time and retain their individual bounds. Genuine workload 5xx
and transport failures trigger catastrophic abort after two qualifying,
non-overlapping windows; expected rejections and injected failures do not count
as catastrophic errors. These settings are initial safety policy, not SLOs.

Convention execution requires supervision. `--unattended` (or `UNATTENDED=1` with
`make sim-convention`) refuses execution. Automated resource monitoring is
reported as unavailable. The operator observes Railway/Sentry evidence and can
request `resource_saturation` by sending **SIGUSR1 to the Python run process**:

```sh
kill -USR1 <python-run-pid>
```

Identify the specific `python -m tailtag_simulator ...` process in the supervised
terminal/process listing. Do not signal the Make parent or another run. The CLI
registers the handler with the running event loop, waking idle execution, and
removes it and restores the previous process handler on exit. The signal latches a
sanitized abort reason, cancels and awaits owned traffic, and writes schema-4
report evidence. Record the relevant Railway/Sentry observation separately;
the signal itself does not measure saturation. Ctrl-C retains interruption
semantics. Every safety abort exits nonzero.

Request admission, release, and outcome counts update validated in-memory
safety evidence without disk writes. Phase transitions, target checks, monitor
ticks, aborts, and finalization records persist the latest evidence; report
finalization flushes the latest cache. Abort evidence is persisted immediately.
A process crash between checkpoints can leave recent request counts absent from
the last durable snapshot. Cache validation or persistence failure stops further
workload and leaves a nonzero report. The prior Staging exercise remains
historical evidence at source `578ebc0a377549289a92efc59a37dacf0b9ca00e`; these
follow-up changes have deterministic regression proof and were not rerun live.

Correctness/ceiling aborts permit bounded read-only diagnostics and
retention/release after readiness and the same deployment are verified.
Readiness/error/saturation aborts skip reconciliation and allow recovery only
when the pinned target recovers. Identity mismatch prohibits further TailTag
HTTP or privileged operations: owned local resources and independently verified
Clerk sessions are closed within the reserve; leases/state may require manual
recovery. Skipped, failed, or uncertain finalization is reported explicitly.
Failed setup can leave bad or unverified identities pending quarantine. Release
requires acknowledged quarantine; uncertain quarantine holds leases for manual
recovery. Cancellation does not prove a previously sent mutation rolled back. Historical
report schemas 1–3 remain valid; guarded execution writes schema 4.
