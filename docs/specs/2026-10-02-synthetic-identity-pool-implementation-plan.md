# Synthetic identity pool implementation plan

Spec: [synthetic simulation identity pool](2026-10-02-synthetic-identity-pool.md)
(#219, frozen acceptance contract P-1 to P-13). This plan sequences the work and
fixes interfaces; the spec stays authoritative for behavior.

## Phase ledger

Scope: STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY, RELIABILITY.
Completed: spec, D3 Staging proof, maintainer approval, reconnaissance; units A,
B, and C each with independent tests, implementation, and review; whole-change
review. Pending: maintainer Staging rollout in the README order (authorized-party
change with `--skip-deploys`, controlled promotion with the migration, readiness,
provision, live `pool-smoke` P-4 proof).

Review dispositions not implemented:

- Unit A F2 (LOW), declined: the remote entry does not re-check pinned Railway
  IDs; the launcher already pins project, environment, service, and instance.
- Whole-change F3 (MEDIUM), deferred: `scripts/api_staging_auth_smoke.py` still
  pins the single portal origin and the retired instance fingerprint. It is
  already unusable for the replacement Staging generation; fix both pins in one
  follow-up.
- Whole-change F5 (LOW), deferred: if a quarantine call itself fails, the setup
  line still lists that index and release returns it to the pool. Readmitting an
  available slot is harmless.

## Design refinements within the approved decisions

- **The lease store holds pool indexes, not Clerk user IDs.** Rows are keyed by
  `(pool, index)`. SETUP resolves an index to its Clerk user through the Backend
  API by `external_id` (`sim-pool-<pool>-<index>`), then checks markers (P-8a).
  Clerk user IDs never cross the lease channel or reach the database, so P-7
  holds there by construction.
- **Refresh is lazy.** Each identity's token provider returns its cached token
  while more than 15 seconds remain and otherwise requests a new one from its
  Clerk session. No background task is needed. The provider is created in SETUP
  and owns the Frontend API cookie jar (D5).
- **The Staging portal origin stays a literal.** Staging readiness compares
  literals today; there is no Staging SHA-256 pin. The pair is
  `("https://accounts.staging.tailtag.app",
  "https://simulator.staging.tailtag.app")` for the canonical phase only. The
  `staging-next` candidate phase is unchanged.
- **Handles use underscores.** Profile handles must match
  `^[a-z0-9][a-z0-9_]{1,31}$`, so the pool handle is `sp_<pool>_<index>`, with
  pool names limited to `[a-z0-9]{1,12}`. `external_id` keeps hyphens.
- **Pool runs are host-only for now.** The lease channel needs the Railway CLI
  and the owner manifest, so pool commands run from the maintainer's machine,
  not the simulator container. #228 owns other hosts.

## Review units

### Unit A — API: readiness pair and lease store

Files: `services/api/health/configuration.py`, a new `simulation_pool` app
(model, migration, service functions), settings and tooling registration
(`INSTALLED_APPS`, Pyright include, lint lists, `_PACKAGES` if the reset bundle
requires it), a launcher `scripts/api_sim_pool_ssh.py`, Make target, tests.

- `PoolSlot(pool, index, state, run_id, lease_expires_at, updated_at)`, unique
  on `(pool, index)`, `state` in `available | quarantined`. A slot is leased when
  `run_id` is set and `lease_expires_at` is in the future.
- Service functions, each one transaction:
  - `register(pool, size)` creates missing slots up to `size`; never deletes.
  - `allocate(pool, run_id, count, ttl_seconds)` selects `count` available,
    unleased or expired slots with `SELECT ... FOR UPDATE SKIP LOCKED`, leases
    all of them, or leases none and reports the shortfall.
  - `heartbeat(pool, run_id, ttl_seconds)` extends that run's leases.
  - `release(pool, run_id)` clears that run's leases.
  - `quarantine(pool, index, run_id)` marks a slot quarantined and clears its
    lease; `readmit(pool, index)` makes it available.
  - `status(pool)` returns counts only.
- Remote entry point: a function in deployed code that takes one validated
  JSON request, checks the runtime is Staging with the expected #203 identity,
  runs one operation, and returns one fixed JSON shape. Requests and responses
  carry only pool names, indexes, run IDs, counts, and TTLs.
- Launcher: reuses the pinned helpers from `scripts/api_staging_reset_ssh.py`
  (Railway identity, preflight, target IDs, active instance), sends the request
  on stdin to `railway ssh`, and prints the validated response JSON. Request on
  stdin, response on stdout, so the simulator can drive it as a subprocess.
- Readiness: canonical Staging requires exactly the ordered pair above (P-11).

Failure modes to protect (test value map):

| Failure | Contract | Cheapest level |
| --- | --- | --- |
| Two concurrent allocations lease the same slot | P-2 | Real PostgreSQL, two connections |
| Partial allocation when the pool is short | P-2 | Service test |
| Expired lease not reclaimable, or live lease stolen | P-3 | Service test with controlled time |
| Quarantined slot allocated | P-6 | Service test |
| Remote entry runs outside Staging or with a mismatched identity | P-12 | Entry-point test |
| Launcher sends private data in arguments, or skips account or preflight checks | P-12 | Launcher test at the subprocess seam |
| Readiness accepts a wrong, reordered, extra, or missing party | P-11 | Existing readiness tests, parameterized |

### Unit B — simulator: Clerk session and token provider

Files: `tools/simulator/tailtag_simulator/clerk.py`, client changes, tests.

- `ClerkAdmin` (SETUP only, holds the secret): instance and domain pin (P-8a),
  user lookup by `external_id`, user creation with markers, marker check,
  sign-in ticket create and revoke, active-session list and revoke. httpx only.
- `ClerkSession`: Frontend API at `https://clerk.staging.tailtag.app` with an
  in-memory cookie jar, `Origin: https://simulator.staging.tailtag.app`,
  `Clerk-API-Version: 2026-05-12`, no redirects, `trust_env=False`. Redeems a
  ticket, returns tokens lazily, ends its session.
- `ApiClient` accepts a token provider instead of a fixed token and gains a
  bounded `put` for profile onboarding.

Failure modes: ticket created for a wrong instance or unmarked user (P-8a);
secret, cookie, ticket, or token in output, `repr`, or exceptions (P-7); expired
token sent (P-4); cookies sent to the TailTag API (D5); redirect followed.
Clerk HTTP is substituted with `httpx.MockTransport` in tests only.

### Unit C — simulator: pool lifecycle and commands

Files: `tailtag_simulator/pool.py`, phases, CLI, Make targets, README, tests.

- `pool provision --pool P --size N`: secret prompt; create missing Clerk users
  with markers; register slots.
- `pool status --pool P` and `pool readmit --pool P --index I`.
- `pool-smoke --pool P --count N`: SETUP allocates through the lease channel,
  resolves and checks each identity, revokes leftover sessions, redeems a
  ticket, initializes or verifies the profile, discards the secret. SIMULATION
  gets one API client per identity, each with its token provider, and calls
  `GET /api/me/` before and after one token lifetime, heartbeating once.
  RECONCILIATION requires each identity to keep one id and all ids to differ.
  Release ends sessions through the Frontend API and releases leases, even after
  a failure.
- Any identity failing a check is quarantined, the rest are released, and the
  run fails with a fixed stage (P-6). Too few slots fails before allocation.
- The lease channel is a protocol in `SetupContext`; production runs the
  launcher as a subprocess, and tests use an in-memory fake.

Failure modes: SIMULATION reaching the secret, lease channel, or Backend API
(P-8); leases left after a failed run (P-3); profile invariant violated or
drift accepted (P-5); baseline touched (P-9, structural: pool runs only call
`/api/me/` and `/api/profile/`).

## Sequencing

A, then B, then C. Each unit gets an independent test author, an implementer,
and a reviewer. A final whole-change review covers all three. Live Staging
rollout is a maintainer step after merge readiness and is not automated here.
