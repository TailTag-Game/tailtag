# Headless V0 acceptance journeys

Issue: [#221](https://github.com/TailTag-Game/tailtag/issues/221) (SIM-4).
Parent: #199. Builds on the #218 harness
([spec](2026-10-02-headless-simulation-harness.md)), the #219 identity pool
([spec](2026-10-02-synthetic-identity-pool.md)), and #220 fixture provisioning
([spec](2026-10-02-simulation-fixture-provisioning.md)). Later consumers: #222
(reconciliation) and #223 (cleanup).

## Status and phase ledger

**APPROVED and frozen (2026-10-03).** The refinement decisions G1 to G12 were
approved on 2026-10-03 and are posted on
[#221](https://github.com/TailTag-Game/tailtag/issues/221#issuecomment-5972559017).
This spec turns them into a frozen acceptance contract (J-1 to J-13) and adds the
design details below.

Execution: STANDARD EXPANDED. Assurance: SECURITY (the public-API boundary of
SIMULATION, and no credentials, URLs, or bodies in output).

The maintainer approved this spec and the
[implementation plan](2026-10-03-headless-acceptance-journeys-implementation-plan.md)
on 2026-10-03.

Progress: tests, implementation, and review are complete, and `make sim-check`
passes. The maintainer Staging proof (J-13) is pending.

## Objective

Prove the implemented V0 gameplay and image contract end to end. A run must go
through the real Clerk authentication boundary and the public API only, on run-owned
records, and report one sanitized PASS or FAIL line per journey.

## Evidence

All paths are under `services/api/`.

- **No custom exception handler and no throttling** (`config/settings/base.py`).
  Unauthenticated requests get 401 with `WWW-Authenticate: Bearer`. This applies to
  both a missing header and an invalid bearer (`authentication/drf.py`,
  `authentication/clerk.py`).
- **Catch session.** `PUT /api/conventions/<c>/fursuit-activations/<f>/catch-session/`
  takes `{"is_active": bool}` and returns 200 with the session state. It needs an
  existing activation, which #220 provides. A non-owner gets 404 before the body is
  parsed (`conventions/views.py`).
- **Credential.**
  - `GET …/catch-credential/` returns `{"payload": "tailtag:catch:v1:<43>"}` with
    `Cache-Control: no-store`. The payload is stable until it is rotated.
  - `POST …/catch-credential/rotate/` takes an empty body and returns a new payload.
    It revokes the old one in the same transaction.
  - A non-owner gets 404.
- **Resolve.** `POST /api/conventions/<c>/catch-credentials/resolve/` takes
  `{"payload"}`.
  - It returns 200 with `{convention_id, fursuit: {tailtag_id, name, photo_url}}`.
  - An unknown, revoked, inactive, session-less, or expired credential gets an
    identical 404.
  - A caller who is not enrolled gets 403.
- **Confirm.** `POST /api/catches/confirm/` takes `{"payload"}`.
  - It returns 201 or 200 with
    `{outcome: "created"|"already_caught", catch: {id, …}}`.
  - Domain errors return `{"code", "detail"}`:
    - 403 `catcher_ineligible`
    - 409 `active_convention_mismatch`
    - 409 `self_catch_not_allowed`
    - 404 `catch_target_unavailable`
  - Already-caught is checked before every eligibility check
    (`catches/services.py`, `confirm_catch`).
  - A catcher with an inactive enrollment gets the mismatch error. A catcher with no
    enrollment gets the ineligible error.
  - Expired and stopped sessions give the same public outcome.
- **History.** `GET /api/catches/?convention_id=<c>` shows only the caller's own
  catches as catcher. It returns `{catch_count, next, previous, results: [{id,
  fursuit: {id, …}, …}]}`. No public endpoint shows owners the catches of their
  fursuits.
- **Deactivation.** `PUT …/fursuit-activations/<f>/` with `{"is_active": false}`
  revokes the credential and ends the session (`conventions/services.py`).
- **Active convention.** `DELETE /api/conventions/active/` returns 204 and
  deactivates the enrollment without removing it. `PUT` with `{"convention_id"}`
  restores it.
- **Fursuit images.**
  - `POST /api/fursuits/` takes multipart with exactly one text part `name` (1–50
    characters) and one file part `photo`. It returns 201 with `{id, tailtag_id,
    name, photo_url, is_enabled}`.
  - `PUT /api/fursuits/<id>/photo/` takes multipart `photo` only and returns 200.
- **Avatar.** `PUT /api/profile/avatar/` takes multipart `avatar` and returns 200
  with the profile, including `avatar_url`. `DELETE` returns 204, and
  `GET /api/profile/` then shows `avatar_url: null`.
- **Image rejections carry no code.** They return 400 `{"photo"|"avatar":
  ["<message>"]}` (`media/images.py`, `MEDIA_ERROR_MESSAGES`). The exact messages
  are:
  - `unsupported_format`: "Upload a JPEG, PNG, or static WebP image."
  - `invalid_image`: "Upload a valid image."
  - `too_many_pixels`: "The photo dimensions are too large."

  The pixel check reads the image header and runs before a full decode.
- **Image URLs are presigned S3 SigV4 URLs** of several hundred characters
  (`media/storage.py`). A history page of 20 is about 14 KB. The current 4096-byte
  response cap cannot hold one.
- **Expiry is covered in-process.** The 12 h session lifetime
  (`conventions/catch_sessions.py`) and the 10 MiB byte limit are already covered
  by API pytest (`tests/test_catch_confirmation.py`,
  `tests/test_fursuit_catch_credential_lifecycle.py`, and the media tests). So is
  concurrent confirmation (`tests/test_fursuit_catch_session_concurrency.py` and
  the catch confirmation concurrency tests).

## Design

### Command

`python -m tailtag_simulator journeys --pool <name>`, through
`make sim-journeys POOL=<name>`. It is host-only and Staging-only, like
`fixture-smoke`. It has no counts to configure. The shape is fixed:

- 2 owners with 2 fursuits each
- 4 catchers
- 1 outsider

That is 7 leased identities.

SETUP reuses the `fixture-smoke` sequence:

1. verify the target
2. lease and open the identities
3. call `provision` with the first 6 indexes (`owners=2`, `fursuits_per_owner=2`,
   `catchers=4`)

The seventh identity is leased and onboarded but never provisioned, so it holds no
enrollment. Release always runs. The shared SETUP and release sequence lives in
one place that both commands use. It is not copied.

### Roles

| Role | Identity | Fixture state |
| --- | --- | --- |
| O1, O2 | owners | 2 activated fursuits each: F1a, F1b (O1) and F2a, F2b (O2) |
| C1–C4 | catchers | enrolled, active convention set |
| U | outsider | onboarded, not enrolled |

### Journeys (ordered)

Each journey uses its own fursuit or identity. Where a later journey targets the
same fursuit, it first sets the state it needs through idempotent owner calls
(session `PUT true`, credential `GET`), so it does not depend on what an earlier
journey left behind. A journey stops at its first failed step and reports that
step. The remaining journeys still run.

| # | Name | Actors and target | Steps and expected outcomes |
| --- | --- | --- | --- |
| 1 | `unauthenticated` | no token; malformed token | `GET /api/me/` with no token → 401. `GET /api/me/` with the fixed non-JWT bearer `not-a-token` → 401. |
| 2 | `catch` | O1, C1, F1a | O1 session `PUT true` → 200 `is_active` true; O1 credential `GET` → 200 payload; C1 resolve → 200 with `convention_id` equal to the run Convention; C1 confirm → 201 `created`; C1 history for the run Convention → exactly one result whose `id` is the catch and whose `fursuit.id` is F1a. |
| 3 | `retry` | O1, C1, F1a | C1 confirm with the same payload → 200 `already_caught` with the same catch ID; O1 session `PUT false` → 200 `is_active` false; C1 confirm → 200 `already_caught` with the same ID; C1 history → still exactly one result for F1a. |
| 4 | `stopped_session` | O1, C2, F1b | O1 session `PUT true` and credential `GET`; O1 session `PUT false`; C2 confirm → 404 `catch_target_unavailable`. |
| 5 | `stale_credential` | O2, C2, F2a | O2 session `PUT true` and credential `GET` (old payload); O2 rotate → 200 with a different payload; C2 confirm the old payload → 404 `catch_target_unavailable`; C2 resolve the new payload → 200. |
| 6 | `deactivated` | O2, C3, F2b | O2 session `PUT true` and credential `GET`; O2 activation `PUT false` → 200 `is_active` false; C3 confirm → 404 `catch_target_unavailable`. |
| 7 | `self_catch` | O2, F2a | O2 session `PUT true` and credential `GET`; O2 confirm → 409 `self_catch_not_allowed`. |
| 8 | `convention_mismatch` | O2, C4, F2a | O2 session `PUT true` and credential `GET`; C4 `DELETE` active convention → 204; C4 confirm → 409 `active_convention_mismatch`; C4 `PUT` active convention → 200. The restore step runs even when the confirm step fails. |
| 9 | `ineligible_catcher` | O2, U, F2a | O2 session `PUT true` and credential `GET`; U confirm → 403 `catcher_ineligible`. |
| 10 | `not_owner` | O1 against O2's F2a | O1 credential `GET` → 404; O1 session `PUT true` → 404. |
| 11 | `avatar` | C3 | `PUT` avatar (image A) → 200 with an `https://` `avatar_url`; `PUT` avatar (image B) → 200 with an `https://` `avatar_url`; `DELETE` → 204; `GET /api/profile/` → `avatar_url` null. |
| 12 | `fursuit_photo` | O1 | `POST /api/fursuits/` (name `Sim journey`, photo A) → 201, `is_enabled` true, `https://` `photo_url`; `PUT` that fursuit's photo (image B) → 200 with an `https://` `photo_url`. |
| 13 | `image_rejections` | O1, fursuit from 12 | `PUT` photo with each of these → 400 `photo` with the exact message: GIF bytes (`unsupported_format`), non-image bytes with a JPEG content type (`invalid_image`), a 5001×5001 PNG (`too_many_pixels`). It runs only if journey 12 created the fursuit; otherwise it fails at step `precondition`. |

The run Convention ID comes from `GET /api/conventions/active/` (C1). The fursuit IDs
come from each owner's `GET /api/fursuits/`, sorted by ID.

### Images

- **Valid images.** Images A and B come from the committed #220 fixture folder
  `services/api/simulation_fixtures/images/`, in sorted filename order, cycling. The
  host CLI reads them as plain data. That is not an import. When the folder is empty
  or unreadable, the CLI falls back to two distinct deterministic PNGs that the
  simulator generates with the standard library.
- **Rejection files.** These are generated in the simulator package:
  - a minimal GIF
  - a short non-image byte string
  - a 5001×5001 1-bit PNG, which compresses to a few KB
- **Run-owned records only.** Journeys change images only on leased identities'
  avatars and on the fursuit that journey 12 creates. They never change #220 fixture
  photos, the #204 baseline, or another run's records.

### Public client

`ApiClient` gains these methods:

- `post(path, body | None)`. JSON, or an empty body when `None`.
- `delete(path)`.
- `put_multipart(path, data, files)` and `post_multipart(path, data, files)`.

`MAX_RESPONSE_BYTES` rises from 4096 to 65536. These are unchanged:

- origin pinning, checked before sending
- no redirects, with 3xx a failure
- the 10 s timeout
- no cookies
- the per-request token provider
- `trust_env=False`

`ApiClient` stays the only way simulator code reaches the API.

### Output

The fixed lines are:

```text
PASS target staging source_sha=<sha>
RUN run_id=<uuid>
PASS setup identities=7 fursuits=4
PASS journey=<name>                       (one per journey, in order)
FAIL journey=<name> step=<step> expected=<status>/<code> observed=<status>/<code>
PASS journeys passed=13                   or  FAIL journeys failed=<n>
PASS release
```

- `<step>` is a fixed step name from the journey's own definition.
- `<code>` is one of these:
  - a confirm outcome (`created`, `already_caught`)
  - a domain error code (`catcher_ineligible`, `active_convention_mismatch`,
    `self_catch_not_allowed`, `catch_target_unavailable`)
  - an image rejection name (`unsupported_format`, `invalid_image`,
    `too_many_pixels`), mapped from the exact message string
  - `-` when the step expects no code
  - `other` for anything else

  Nothing from a response body is printed except a code from that allowlist.
- A step that fails without an HTTP response prints `observed=error`. That covers
  timeouts, the size cap, and redirects.
- A step that got the expected status but the wrong shape prints `observed=<status>/shape`.
- SETUP and release failures print the existing `fixture-smoke` lines.
- The exit code is 0 only if setup, every journey, and release passed.

### Relationship to #204, #222, and #223

The run changes only its own fixtures and leased identities, so the #204 baseline is
untouched. The objects a journey run adds are outside the #220 ledger:

- catches and catch sessions
- rotated credentials
- one deactivated activation
- the journey-created fursuit and its stored photos
- stored-then-cleared avatars

All of them belong to the run's pool identities or the run Convention, so #222 and
#223 can find them through the ledger's identities and Convention. Every identity
the run used is dirty until #223 or a manual readmit.

## Acceptance contract (frozen)

- **J-1 Run shape** (AC1, G4). `journeys` leases 7 identities. It provisions the first
  6 through the #220 channel (2 owners × 2 fursuits, 4 catchers) and leaves the 7th
  unprovisioned. It runs the 13 journeys in the documented order. A journey stops at
  its first failed step, and the remaining journeys still run. Release always runs
  once leases may be held.
- **J-2 Canonical** (AC2). Journey `catch` passes only on these outcomes:
  - session start 200
  - credential 200
  - resolve 200 for the run Convention
  - confirm 201 `created`
  - exactly one history result matching the catch ID and F1a
- **J-3 Retry** (AC3, G8). Journey `retry` passes only on these outcomes:
  - 200 `already_caught` with the same catch ID before and after the session stops
  - exactly one history result for F1a
- **J-4 Negatives** (AC4, G1, G3). Each of these journeys passes only on its
  documented status and code:
  - `stopped_session`, `stale_credential`, and `deactivated` → 404
    `catch_target_unavailable`
  - `self_catch` → 409 `self_catch_not_allowed`
  - `convention_mismatch` → 409 `active_convention_mismatch`, followed by a restore
  - `ineligible_catcher` → 403 `catcher_ineligible`
  - `stale_credential` also passes only if the new payload resolves
- **J-5 Unauthorized** (AC5, G12). `unauthenticated` passes only on 401 for both no
  token and a malformed token. `not_owner` passes only on 404 for both the credential
  `GET` and the session `PUT`.
- **J-6 Images** (AC6, G7, G11). `avatar` and `fursuit_photo` pass only on their
  documented statuses. Every URL they read must be a non-empty `https://` string, and
  `avatar_url` must be null after `DELETE`. No image URL is ever fetched.
- **J-7 Rejections** (AC7, G6). `image_rejections` passes only on 400 with the exact
  `photo` message for each of the three generated files. Valid uploads use the #220
  fixture images, or the generated fallback when that folder is empty.
- **J-8 Run-owned images** (AC8). No request changes a #220 fixture fursuit's photo.
  The only photo writes target the fursuit that journey 12 created. The only avatar
  writes target leased identities.
- **J-9 Boundary** (AC9, G5). SIMULATION receives only `ApiClient` instances bound to
  the verified origin: one per identity, plus one with no token and one with the
  fixed malformed token. It never receives the lease channel, the fixture channel,
  the prompt, or the Clerk admin. `ApiClient` keeps every protection listed under
  Public client, now with a 65536-byte cap. The simulator Semgrep rules pass.
- **J-10 Output** (AC10, G9). Output is only the fixed lines above. No token,
  payload, response body, URL, object key, image bytes, database ID, Clerk ID,
  handle, or fursuit name appears. A test enforces this with sentinels across every
  journey failure path.
- **J-11 Offline proof** (AC11, G2). `make sim-check` covers J-1 to J-10 against
  in-memory fakes, with no secrets and no network. The live command is Staging-only.
- **J-12 Docs and no API change** (AC11, AC12). The simulator README documents:
  - the command and its prerequisites
  - the identity count
  - the output and failure lines
  - the quarantine consequence

  This spec records what is not covered over the network (expiry, the 10 MiB
  limit, concurrency). There is no change under `services/api/`.
- **J-13 Staging proof** (AC13, G10). One maintainer-run `make sim-journeys` on
  Staging passes, and its sanitized output is recorded below.

## Reversibility

TWO-WAY DOOR. The change is simulator-only, with no API, schema, or migration change.
Rolling back means reverting the commit. The data a Staging run leaves behind stays
until #223 or a manual readmit.

## Non-goals

- Load, ramps, scheduling, performance baselines, failure injection, and Flutter/UI
  (#224 to #228).
- Privileged reconciliation (#222) and cleanup (#223).
- New or changed public API. Changes to #219 leases or the #220 `provision`
  contract.
- A local or Development live mode.
- Network tests of session expiry, the 10 MiB limit, or concurrent confirms.
- Fetching presigned URLs.

## Staging proof record (J-13)

Pending.
