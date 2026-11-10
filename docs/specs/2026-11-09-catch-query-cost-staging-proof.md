# Catch endpoint query count and authentication cost: proof

Issue: [#451](https://github.com/TailTag-Game/tailtag/issues/451). Spec: [refinement comment](https://github.com/TailTag-Game/tailtag/issues/451#issuecomment-6752734451) and the [AC4 amendment](https://github.com/TailTag-Game/tailtag/issues/451#issuecomment-6755623056). Code: [PR #498](https://github.com/TailTag-Game/tailtag/pull/498) (`9b3e550`). Before state: Render Staging run `2e17d592` and its Sentry spans.

Checkpoint: 2026-11-10 UTC. The first pull request added the statement lists, the code change, the `view.authenticate` record, and a local profile. The maintainer then promoted `9b3e550` to Render Staging and ran one `normal-profile` run. The [Staging run](#staging-run-ac20-to-ac24) section records it. The run returned `acceptable`. `resolve` server time fell by 38%, and the request rate rose by 31%.

## Before: Sentry spans of run `2e17d592` (AC1, AC18)

Run `2e17d592` is the current normal baseline (#411 AC14). It ran on Render Staging in Virginia, backend `2706490`, from 2026-11-04 21:25Z to 21:37Z. Sentry recorded a transaction for every catch request.

| Endpoint | Transactions | Server average | Server p95 | Statements per request |
| --- | --- | --- | --- | --- |
| `resolve` | 2,336 | 138.1 ms | 286.0 ms | 9.0 |
| `confirm` | 2,336 | 86.5 ms | 192.7 ms | 5.2 |
| `GET /api/catches/` | 1,198 | 72.9 ms | 171.1 ms | 4.0 |

The split below divides the server average into three parts. "Database" is the database span time outside `view.authenticate`. "Rest" is everything else, and most of it is in no span.

| Endpoint | Database | `view.authenticate` | Rest | Rest in no span |
| --- | --- | --- | --- | --- |
| `resolve` | 49.8 ms (36%) | 14.1 ms (10%) | 74.2 ms (54%) | 73.2 ms |
| `confirm` | 24.0 ms (28%) | 14.7 ms (17%) | 47.8 ms (55%) | 46.4 ms |
| `GET /api/catches/` | 16.8 ms (23%) | 13.1 ms (18%) | 43.0 ms (59%) | 41.6 ms |

A database statement took about 5 ms to 6 ms on average. The rest is more than half of each request. The statement cut addresses only the database part.

## Statement lists (AC1, AC2, AC9, AC10, AC12)

"Data statement" means a `SELECT`, `INSERT`, `UPDATE`, or `DELETE`. Savepoint statements do not count. The counts come from `services/api/tests/test_catch_query_counts.py`, which runs each request through the real authentication path.

### `resolve`

Before, 9 data statements:

| # | Statement | Reason |
| --- | --- | --- |
| 1 | User by Clerk subject | Authentication loads the TailTag user. |
| 2 | Convention by id | The path Convention must exist, or the response is 404. |
| 3 | Caller profile eligibility | An ineligible caller gets 403. |
| 4 | Caller enrollment | A caller who is not enrolled gets 403. |
| 5 | Credential by token and Convention, joined to activation, fursuit, owner, and Convention | The target lookup. |
| 6 | Owner profile eligibility | Part of the target eligibility. |
| 7 | Owner enrollment | Part of the target eligibility. |
| 8 | Unended catch session | The target needs a live, unexpired session. |
| 9 | Credential still current | Closes the rotation and revocation race. |

After, 4 data statements:

| # | Statement | Replaces |
| --- | --- | --- |
| 1 | User by Clerk subject | 1 |
| 2 | Caller gate: the Convention row with two `EXISTS` answers, caller profile eligibility and caller enrollment | 2, 3, 4 |
| 3 | Target read: the credential, activation, fursuit, and Convention, with two `EXISTS` answers, owner profile eligibility and owner enrollment | 5, 6, 7 |
| 4 | Final statement: the unended catch session, with one `EXISTS` answer, credential still current | 8, 9 |

### `confirm`

For an existing catch, the count goes from 5 to 4: the user lookup, the persisted-user check, the credential discovery, and the existing-catch read. The fifth statement loaded the fursuit for the response. The existing-catch read now joins the fursuit.

For a new catch, the count goes from 15 to 14:

| # | Statement | Change |
| --- | --- | --- |
| 1 | User by Clerk subject | |
| 2 | Persisted-user check | |
| 3 | Credential discovery | |
| 4 | Existing-catch read | Now joins the fursuit. |
| 5 to 12 | Locked reads: two profiles, Convention, enrollments, fursuit, activation, credential, session | None |
| 13 | Existing-catch read under the locks | Now joins the fursuit. |
| 14 | Catch insert | |
| 15 | Fursuit load for the response | Removed. The response uses the fursuit row that statement 9 locked. |

The locked reads keep their statements and their order (confirmation spec AC-09). The persisted-user check stays (confirmation spec AC-02).

Sentry counted 12,070 database spans for 2,336 `confirm` requests, or 5.17 per request. In production a new catch also sends one savepoint and one release, so it has about 17 spans. That count fits about 32 new catches (1.4%) and the rest as existing catches.

### `GET /api/catches/`

No change. With `convention_id`: the user lookup, the Convention existence check, the count, and the page, so 4. Without `convention_id`: 3.

## How `resolve` keeps its rules (AC5 to AC8)

- The response precedence stays: authentication, request validation, Convention existence (404), caller profile eligibility (403), caller enrollment (403), then target resolution (404). One caller gate row answers all three caller questions, so the order of the checks does not change.
- Each rejection records the same telemetry reason as before. In the final statement, the session checks come before the current-credential check, as before.
- The final current-credential check stays a separate statement after the target evaluation (AC6). The race tests 13, 14, and 15 pass with no change to an expected outcome. Two tests now hook the target evaluation step `_is_resolved_target_eligible` in place of `is_fursuit_activation_eligible` (AC7).
- `profiles.eligibility.eligible_player_profiles()` holds the profile eligibility rule. `is_participation_eligible`, the caller gate, and the target read use it (AC8). The other callers of the eligibility helpers do not change.

AC4 names the session in the target read. The session read is in the final statement instead. A target read that loads the session changes race test 15 from 404 to 200. In that design, a session stop after the target evaluation no longer fails the request. The count is still 4, and every outcome stays the same.

## `view.authenticate` (AC15, AC16, AC17)

`TailTagAuthentication` still loads the user row on every request. No cache keeps an identity across requests.

Local measurement, `resolve` after the change, average of 400 requests:

| Part | Time | Share |
| --- | --- | --- |
| Clerk token verification (offline RS256) | 0.24 ms | 18% |
| Connection health check (`SELECT 1`) | 0.42 ms | 32% |
| User query | 0.65 ms | 50% |
| Anything else | about 0.00 ms | 0% |
| Total `authenticate` | 1.31 ms | 100% |

Staging, run `2e17d592`: `view.authenticate` averaged 14.1 ms for `resolve`. The user query span inside it averaged 3.6 ms. The other 10.3 ms has no child span.

What this shows:

- Token verification is not the cost. It is one RSA signature check and about a fifth of the local time.
- The health check is about a third of the local time. Django sends `SELECT 1` on the first database use of each request because `CONN_HEALTH_CHECKS` is on. It uses a raw cursor, so Sentry records no span for it. On Staging it is one more round trip to a database at 100% CPU, so it is likely a large part of the 10.3 ms.
- The rest of the 10.3 ms is likely CPU time, but no measurement shows that. The Staging API has 0.5 CPU for 3 workers and the Sentry transport thread, so each part takes longer there.

`CONN_HEALTH_CHECKS` stays `True` (#448 AC1). Without it, the first request on each worker fails after a PostgreSQL restart.

## The rest of the server time (AC18)

The local profile ran 300 `resolve` requests under `cProfile`. Each function's own time is put in a group by its module. Built-in functions count toward the group that called them. `cProfile` adds time to code that makes many small calls, so the shares are a guide, not exact.

| Group | Sentry SDK on | Sentry SDK off |
| --- | --- | --- |
| ORM and database driver, with the local database wait | 7.98 ms (52%) | 8.49 ms (75%) |
| Sentry SDK | 3.06 ms (20%) | 0.06 ms (1%) |
| Other standard library (copies, context managers, HTTP client) | 1.84 ms (12%) | 0.91 ms (8%) |
| Framework and middleware | 0.96 ms (6%) | 0.94 ms (8%) |
| Logs and outcome telemetry | 0.62 ms (4%) | 0.19 ms (2%) |
| Application code | 0.51 ms (3%) | 0.20 ms (2%) |
| URL signing | 0.34 ms (2%) | 0.33 ms (3%) |
| Token verification | 0.19 ms (1%) | 0.26 ms (2%) |
| Total per request | 15.50 ms | 11.37 ms |

With the SDK on, the total is about 4.1 ms higher. The SDK's own code is 3.0 ms of that. The rest is more standard library and logging work that the SDK starts. Without the profiler, the SDK added about 0.5 ms to 1.4 ms of process CPU per request for `confirm` and `GET /api/catches/`. The `resolve` result was not clear. Laptop CPU scheduling makes differences below 1 ms noisy.

What this shows:

- Locally, the Sentry SDK at trace rate 1.0 is the largest CPU cost outside the database. It is about a fifth to a quarter of request CPU. Development and Staging use trace rate 1.0 ([backend delivery operations](../development/backend-delivery-operations.md)).
- URL signing, token verification, logs, and application code are each small.
- This is a lead, not a Staging measurement. The Staging run in part two shows how much rest is left after the statement cut. If the rest is still more than half of the `resolve` server time, a follow-up issue covers it (AC23).

## Local before and after

Same database and same seeded data, `main` (`e28f114`) against this change. Average of 400 requests per endpoint, Sentry SDK on.

| Endpoint | Statements | Database time | Process CPU | Wall time |
| --- | --- | --- | --- | --- |
| `resolve` | 9 to 4 | 4.16 to 2.71 ms | 6.00 to 5.27 ms | 9.42 to 7.60 ms |
| `confirm` (existing catch) | 5 to 4 | 1.93 to 1.62 ms | 3.92 to 3.48 ms | 5.44 to 4.73 ms |
| `GET /api/catches/` | 4 to 4 | 1.64 to 1.59 ms | 3.35 to 3.19 ms | 4.65 to 4.46 ms |

The local database is fast, about 0.4 ms to 0.7 ms per statement. On Staging a statement took about 5 ms to 6 ms, so the saving there is larger in time.

## Method

- The measurement called the real WSGI application with `config.settings.production`, one request at a time, in one process.
- Settings: `CONN_MAX_AGE` 60 with `CONN_HEALTH_CHECKS`, and real Clerk verification with a throwaway RSA key. S3 URL signing used dummy values. The Sentry SDK ran at trace rate 1.0 and sent its envelopes to a local sink process.
- Database: PostgreSQL 17 in Docker on the same machine, in a disposable database that was dropped after the run.
- Machine: Apple M2 Pro, macOS 26.6, Python 3.13.14, Django 6.0.8, Django REST Framework 3.17.2, `sentry-sdk` 2.71.0.
- Each endpoint had 60 warm-up requests before the 400 timed requests. Timers wrapped the token verification, the health check, the user lookup, and `authenticate`. A database execute wrapper summed the statement time.
- The measurement added no Sentry span, metric, or profiling setting to the application (AC19).

## Staging run (AC20 to AC24)

### Release and target

| Binding | Value |
| --- | --- |
| Backend source | `9b3e550e46fac4e1a6c348f404d30e2eb929a228` ([PR #498](https://github.com/TailTag-Game/tailtag/pull/498)) |
| Staging promotion | `dep-dbp6kis9v7es73aovi30`, deployed `2026-11-10T00:50:19Z`, every outcome `SUCCEEDED` ([receipt](../development/staging-deployments/dep-dbp6kis9v7es73aovi30.json)) |
| Staging plans | API `0.5c-512mb`, PostgreSQL `0.1c-256mb`, both in Virginia |
| API runtime | 1 instance, 3 sync workers, `CONN_MAX_AGE` 60 with health checks, Sentry trace rate 1.0 |
| Simulator release | `f275b7bb6e298c242164a475832a907e6e9e5764`, image `sha256:bde88f9aac935c21c944c2419476f681dba3d8491866e8f09cd4669b2af881bf`, the same as run `2e17d592` |
| Profile | `tools/simulator/host/normal-profile.json`, unchanged |
| Comparable key | `convention-baseline` v2, plan `dac260032cf2…`, `staging`, `external_host:linux/amd64` |

### Session

The maintainer ran a host operator session on 2026-11-10. The session key was registered on Render only for the session and removed at the end. The maintainer confirmed the session end. The results of the two negative controls at session start were not kept.

| Run | Window (UTC) | Result |
| --- | --- | --- |
| `309b4e46-0f7a-4e3f-b6da-3b0597739f8a`, smoke | `01:02:22Z` to `01:04:57Z` | `passed`. All 13 journeys passed, among them `stale_credential`, `stopped_session`, `self_catch`, `convention_mismatch`, and `ineligible_catcher`. |
| `027338ba-776c-4373-9af9-a88b9b70a225`, normal | `01:05:09Z` to `01:14:42Z` | `passed`. Target `9b3e550` confirmed. Reconciliation passed 14 checks. Cleanup removed every fixture. |

`task sim-host-collect` copied both runs into the owner-private archive with size and SHA-256 checks, and evaluated the normal run.

### Verdict (AC20)

The verdict is `acceptable` against the baseline from run `2e17d592`. All 27 checks passed: 16 absolute, 8 regression, and 3 saturation.

| | Run `2e17d592` (baseline) | Run `027338ba` |
| --- | --- | --- |
| Backend | `2706490` | `9b3e550` |
| Outcome / correctness | `passed` / `passed` | `passed` / `passed` |
| Rate, total | 19.62 per second | 25.67 per second (+31%) |
| p95, total | 596.3 ms | 384.5 ms (−36%) |
| p99, total | 827.1 ms | 493.5 ms (−40%) |
| p95, `resolve` | 623.7 ms | 393.4 ms |
| p95, `confirm` | 585.4 ms | 373.9 ms |
| p95, read | 561.6 ms | 324.1 ms |
| Errors and timeouts | 0 | 0 |
| Generator peak CPU | | 58.9% |

The rate is now above the retired Railway baseline of 24.39 per second. This issue promotes no baseline (AC24). A promotion is a separate owner decision.

### Sentry statements per request (AC21)

| Endpoint | Transactions | Before | After |
| --- | --- | --- | --- |
| `resolve` | 3,071 | 9.0 | 4.0 |
| `confirm` | 3,070 | 5.17 | 4.13 |
| `GET /api/catches/` | 1,562 | 4.0 | 4.0 |

`confirm` fell by about one statement, as expected for a run of mostly existing catches.

### Server time (AC22)

| Endpoint | Server average | Server p95 |
| --- | --- | --- |
| `resolve` | 138.1 to 86.0 ms (−38%) | 286.0 to 193.1 ms (−32%) |
| `confirm` | 86.5 to 59.4 ms (−31%) | 192.7 to 113.8 ms (−41%) |
| `GET /api/catches/` | 72.9 to 54.3 ms (−26%) | 171.1 to 102.3 ms (−40%) |

The split uses the same three parts as the before section.

| Endpoint | Database | `view.authenticate` | Rest |
| --- | --- | --- | --- |
| `resolve` | 49.8 to 18.5 ms (22%) | 14.1 to 12.2 ms (14%) | 74.2 to 55.3 ms (64%) |
| `confirm` | 24.0 to 17.3 ms (29%) | 14.7 to 11.3 ms (19%) | 47.8 to 30.8 ms (52%) |
| `GET /api/catches/` | 16.8 to 13.5 ms (25%) | 13.1 to 12.9 ms (24%) | 43.0 to 27.9 ms (51%) |

What this shows:

- The statement cut worked. The database part of `resolve` fell from 49.8 ms to 18.5 ms.
- `GET /api/catches/` has no code change, but it is 26% faster. The database and the API CPU are less busy, so every request waits less.
- A statement still takes about 4 ms to 5.5 ms. In `view.authenticate`, the user query span is about 3 ms, and the part with no child span is about 9 ms.
- The rest is now 64% of the `resolve` server time.

### Resource use

From the Render Dashboard, read by the maintainer for the run window. Times are UTC.

| Service | CPU | Memory |
| --- | --- | --- |
| `tailtag-api-stg` (limit 0.5 CPU, 512 MB) | 85% to 100% from about 01:08Z to 01:14Z, at 100% twice. The smoke run reached about 30%. | About 66% steady (about 340 MB). One short spike to about 80% (about 410 MB) near 01:12Z. |
| `tailtag-postgres-stg` (limit 0.1 CPU, 0.25 GB) | 45% to 65% in the same window, peak about 75% near 01:13Z. Under 20% before the run. | About 38%, flat. |

The API reached its CPU limit, and the database did not. Before #448, the database was the resource at 100%. After this change, the API CPU limits the request rate. A larger database plan does not address that.

### Follow-up (AC23)

The rest is more than half of the `resolve` server time, so AC23 applies. [#499](https://github.com/TailTag-Game/tailtag/issues/499) covers the API CPU outside the database. The local profile points first at the Sentry SDK at trace rate 1.0.
