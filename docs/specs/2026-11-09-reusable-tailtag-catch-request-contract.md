# Reusable TailTag and catch request contract

## Status

Frozen for #502 on 2026-11-09. Parent Feature: [#501](https://github.com/TailTag-Game/tailtag/issues/501).

Tasks #503 to #513 build against this contract. If a task needs a different rule, the task returns the conflict to the owner. The task does not change the rule on its own.

This contract changes no application code. The owner decisions come from the #502 refinement comment ([comment 6758140626](https://github.com/TailTag-Game/tailtag/issues/502#issuecomment-6758140626)).

## Terms

- A tag is the one current opaque code that an owner prints or displays for a suit.
- A token is the random 43-character part of a tag.
- A request is one catch attempt that the server records for an owner decision.
- A trio is one player, one suit, and one convention.
- The review deadline is the instant when the review window closes for a convention.
- The review window is open while the current database time is before the review deadline.
- A final state is a request state that no later action can change.
- The gate is one server setting that turns the new flow on or off.
- PITR (point-in-time recovery) restores a database to an earlier moment.
- A counted decline is a request with a `declined_at` value that undo or restore has not cleared. A later withdrawal, including self-leave, does not clear it.

## Policy and implementation choices

This document keeps two kinds of rules apart.

- Approved policy comes from #501 and its child tasks, or from an owner decision in #502. Each policy section names its source.
- Implementation choices are technical rules that the contract adds so the tasks agree. The section [Implementation choices](#implementation-choices) lists them. A task can propose a change to an implementation choice through review. A change to approved policy needs an owner decision.

## Sources

| Source | Policy it gives |
| --- | --- |
| #501 | Reusable tag, approval by default, review through the second following local day, outcome visibility, history deletion, preserved catches, no partial release |
| #503 | Local time zone, deadline rule, change rules before and after closure |
| #504 | One current tag per suit, preview-only scan, replacement, operator revocation, no v1 compatibility period |
| #505 | Per-suit approval preference, one pending request and one catch per trio, request time as catch time |
| #506 | Decisions, 10-second undo, restoration, withdrawal, cooldowns, blocks, broader limit |
| #507 | Operator controls, expiry, cleanup, audit |
| #508 | Aggregate metrics and simulation |
| #502 decisions G1 to G13 | Interface level, closure record, restore, eligibility matrix, precedence, cooldown counting, tag format, privacy owners, release gate, response boundaries, backfill, rate-limit shape, test traceability |

## Convention review deadline

Source: #501, #503, #502 G2 and G11.

### Fields

The convention gains these fields.

| Field | Type | Rule |
| --- | --- | --- |
| `time_zone` | IANA zone name or null | An authorized operator sets it. The server rejects a name that the IANA database does not know. Once set, it can change to another zone but never return to null. |
| `review_deadline_at` | UTC timestamp or null | The server computes and stores it. Null when `time_zone` is null. |

### Deadline rule

The review deadline is the start of the third calendar day after `end_date`, in the convention local time zone. The server converts that local midnight to a UTC instant and stores it.

| End date | Zone | Local deadline | Stored UTC value |
| --- | --- | --- | --- |
| Sunday 2027-01-17 | `America/New_York` | Wednesday 2027-01-20 00:00 EST | 2027-01-20T05:00:00Z |
| Friday 2027-03-12 | `America/New_York` | Monday 2027-03-15 00:00 EDT | 2027-03-15T04:00:00Z |

The second row crosses the change to daylight saving time on 2027-03-14. The server uses local calendar days, not a fixed 72 hours. The local deadline is midnight on Monday, so the UTC value uses the EDT offset.

If a local midnight does not exist or happens twice because of a zone rule, the server uses the first instant at or after local midnight.

### Changes before and after closure

| Situation | Result |
| --- | --- |
| The window is open and an operator changes `end_date` or `time_zone` | The server recomputes and stores `review_deadline_at`. |
| The recomputed value is at or before the current database time | The window closes at once. |
| The current database time is at or after the stored value, and an operator changes `end_date` or `time_zone` | The server saves the new date or zone. The stored `review_deadline_at` does not move. The window stays closed. |
| `time_zone` is null and an operator sets it | The server computes the deadline. If that value is already in the past, the window is closed at once. |
| Cleanup has not run yet | Closure still applies. Closure depends only on the stored deadline and the database time. |

Closure is permanent. No action reopens a closed window.

### Unknown time zone

If `time_zone` is null, `review_deadline_at` is null. The new flow is unavailable for that convention. Submission returns 409 `catch_requests_unavailable`. Owners and players see no request queue for that convention.

### Backfill

Existing conventions keep `time_zone` null after migration. No authoritative source exists for them. Simulation fixtures and seed data set an explicit zone for each convention that they create.

#503 must pin the `tzdata` package or prove that the server container has IANA zone data. The server uses Python `zoneinfo`.

### Read fields

Convention reads add these fields.

| Field | Type | Meaning |
| --- | --- | --- |
| `time_zone` | string or null | IANA zone name |
| `review_deadline_at` | string (UTC ISO 8601) or null | Stored deadline instant |
| `review_deadline_local_date` | string (`YYYY-MM-DD`) or null | The local calendar day that starts at the deadline |
| `review_open` | boolean | True while the window is open |

The client shows the deadline from these fields. The client needs no time-zone database. Request reads repeat `review_deadline_at` for the request's convention.

## Tags

Source: #501, #504, #502 G7.

### Tag record

Each suit has at most one current tag. Each suit has an integer `tag_version`, which starts at 0 before the first tag exists. The server raises `tag_version` by one on each creation, replacement, and revocation.

The tag record holds the token, the suit, the version that created it, and revocation fields. A token is 32 random bytes encoded as 43 URL-safe base64 characters, like v1.

### Printed format

The printed and displayed payload is:

```text
https://tailtag.app/t#<43-character token>
```

- The token is in the URL fragment. Browsers and HTTP clients do not send a fragment to a server, so the token stays out of edge logs.
- The V0 app scanner reads this format only. It sends the full payload string to the server.
- The server accepts only this exact format. Any other value, including a v1 `tailtag:catch:v1:` code, gets the neutral 404 `catch_target_unavailable`.
- In V0, a phone camera can open this link in a browser. TailTag serves no player flow at that path in V0. Regular-camera links stay a V1 decision.

This format is a one-way door. Badges carry it after printing. The owner approved it on 2026-11-09 (#502 G7).

### Creation

- An owner read creates the first tag only if the suit never had one. Two first reads return the same tag.
- After a replacement, a read returns the new current tag.
- After an operator revocation, a read returns state `revoked` and no payload. The owner must request a replacement. A read never creates a replacement.

The suit must be owned by the caller and enabled. A tag does not depend on any convention, activation, or session.

### Replacement

The owner sends the version they last saw. The server replaces the tag only if that version matches the current `tag_version`.

| Case | Result |
| --- | --- |
| `expected_version` matches | The old tag stops working. The server returns the new tag. |
| `expected_version` is stale | 409 `tag_version_conflict` with the current state and version, and no payload. The server makes no change. |
| The current state is `revoked` and the version matches | The server creates a new tag. |
| The suit never had a tag and `expected_version` is 0 | The server creates the first tag with version 1, the same result as a first read. |
| The suit never had a tag and `expected_version` is not 0 | 409 `tag_version_conflict` with state `none` and version 0. The server makes no change. |

Replacement does not change the fursuit identity, existing catches, pending requests, activations, or the active session.

### Lost response recovery

After a timeout, a lost response, or a 409, the client reads the current tag state. The client compares `tag_version` with the version it sent. The client never repeats a replacement on its own. The owner must choose to replace again.

### Operator revocation

An authorized operator revokes the current tag through the operator tools. The operator never sees the token or payload. Revocation creates no replacement. The audit action is `revoke_fursuit_tag`.

### Secrecy

Raw tokens and payloads never appear in logs, metrics, audit records, error responses, or admin views. Only the owner tag read and the replacement response return a payload.

## Catch requests

Source: #501, #505, #506, #507, #502 G3 to G6 and G10.

### Request record

Every valid submission creates one request row. The row stores the player, suit, convention, the activation and session that were current at submission, `requested_at`, the state, decision times, and whether the decline included a block.

When automatic approval applies, the server creates the request in state `approved` and the catch in the same transaction.

### States

| State | Meaning | Final |
| --- | --- | --- |
| `pending` | Waits for an owner decision | No |
| `approved` | A catch exists for this request | Yes |
| `declined` | The owner declined | No. Undo, restore, operator invalidation, or player self-leave changes it. |
| `withdrawn` | The player withdrew, or the player left the convention | Yes |
| `invalidated` | An operator action or convention cancellation ended it | Yes |
| `expired` | Derived: a `pending` request when the window closes | Yes |

The server does not store `expired`. At the deadline all request history becomes unavailable, so no read returns it. Cleanup counts pending rows as expired for metrics when it deletes them.

### Transitions

| From | Action | To |
| --- | --- | --- |
| none | Submit, approval required | `pending` |
| none | Submit, automatic approval | `approved` |
| `pending` | Owner approves | `approved` |
| `pending` | Owner declines, with or without block | `declined` |
| `pending` | Player withdraws | `withdrawn` |
| `pending` | Player leaves the convention | `withdrawn` |
| `pending` | Operator invalidation, operator enrollment removal, operator activation deactivation, convention cancelled | `invalidated` |
| `declined` | Owner undoes within 10 seconds | `pending` |
| `declined` | Owner restores before the deadline | `pending` |
| `declined` | Operator invalidation, operator enrollment removal, operator activation deactivation, convention cancelled | `invalidated` |
| `declined` | Player leaves the convention | `withdrawn` |

No other transition exists.

### Uniqueness

- One trio has at most one `pending` request.
- One trio has at most one catch. The existing `catches_catcher_fursuit_convention_unique` constraint stays.
- A database constraint enforces one `pending` request per trio.

### Submission checks

At submission, the server checks these items in one transaction:

1. The player is authenticated, has an enabled profile, and has a selected convention.
2. The convention has a time zone and an open window.
3. The convention is playable.
4. The player is enrolled in that convention.
5. The tag is current and its suit is enabled.
6. The suit owner has an enabled profile and an enrollment in that convention.
7. The suit has an active activation for the player's selected convention and an unended, unexpired session.
8. The player does not own the suit.
9. No catch exists for the trio. No pending request exists for the trio.
10. The player is not blocked for the suit and convention.
11. The cooldown and the per-player limit allow a submission.

The server resolves the tag against the player's selected convention. A scan from another convention finds no active activation there and gets the neutral unavailable response.

### Approval preference

Each suit has `catch_approval_mode` with values `manual` and `automatic`. The default is `manual`.

- A change applies only to new submissions.
- Existing pending requests stay pending after a change to `automatic`.
- Blocks, cooldowns, and the per-player limit apply in both modes.

### Times

- `requested_at` is the database time of the submission transaction.
- `approved_at` is the database time of the approval transaction. For automatic approval, it equals `requested_at`.
- The catch stores `caught_at` equal to the request's `requested_at`, and `approved_at`.

### Eligibility after submission

Source: #502 G4.

| Change after submission | Effect on a pending request |
| --- | --- |
| Session stopped or expired | Still approvable |
| Convention ended, or status set to completed, inside the window | Still approvable |
| Tag replaced or revoked | Still approvable |
| Owner deactivated the suit for the convention | Still approvable |
| Player profile disabled | Paused |
| Owner profile disabled | Paused |
| Suit disabled | Paused |
| Convention paused | Paused |
| Operator invalidation of the request | Invalidated |
| Operator removal of the player's enrollment | Invalidated, for the player's requests at that convention |
| Operator removal of the owner's enrollment | Invalidated, for requests on the owner's suits at that convention |
| Operator deactivation of the suit's activation | Invalidated, for requests on that suit at that convention |
| Convention cancelled | Invalidated, for all requests at that convention |
| Player leaves the convention | Withdrawn, for the player's pending and declined requests at that convention |
| Owner leaves the convention | Still approvable, like an owner deactivation |

Paused is a condition, not a stored state. While a request is paused:

- Approve fails with 409 `approval_paused`.
- Every other action follows its normal rules.
- The request stays pending until eligibility returns or the window closes.
- `OwnerRequest.approval_paused` is true. The flag does not say which party or record caused the pause (#512 disabled state).

A paused player cannot call the API, so the player cannot withdraw while paused. The existing disabled-profile rule handles that case.

## Competing actions

Source: #501, #502 G5.

### Transaction rule

Each request action runs in one database transaction:

1. Lock rows in this order, taking only the rows that the action needs: PlayerProfile, Convention, ConventionEnrollment, Fursuit, FursuitActivation, tag record, FursuitCatchSession, CatchRequest, block record, Catch.
2. Read one database time with `SELECT clock_timestamp()` after the locks. Do not use `now()`, which returns the transaction start time, or the application clock.
3. Check the state, eligibility, and window with that time.
4. Write the result.

This extends the existing lock order in [the catch credential spec](2026-09-01-v0-fursuit-catch-credentials.md#transactions-and-global-lock-order).

The action uses that one time value for `requested_at`, `approved_at`, `declined_at`, the window check, the undo check, and the cooldown and limit checks.

Submission always locks the submitting player's PlayerProfile row first. That lock serializes the per-player limit and the cooldown for that player.

### Deadline tie

Source: #502 G5. An action succeeds only if the database time is before `review_deadline_at`. An action at the deadline instant fails.

| Operation when the window is closed | Result |
| --- | --- |
| Submission or preview | 409 `catch_requests_unavailable` |
| Action on a request whose row still exists | 409 `review_window_closed` |
| Action on a request that cleanup deleted | 404 `request_not_found` |

The client treats `review_window_closed` and `request_not_found` the same way: the request is gone.

### Losing and repeated actions

- The losing action gets 409 `request_state_changed` with the current request state in the body.
- A repeat of an action that already happened returns 200 with the current request state. For example, a second approve of an approved request returns 200.
- A repeat after a different action won returns 409 `request_state_changed`.

### Outcome table

The first action committed wins. The table shows the result for the second action.

| First committed | Second action | Second result |
| --- | --- | --- |
| Approve | Withdraw | 409 `request_state_changed`, state `approved` |
| Withdraw | Approve | 409 `request_state_changed`, state `withdrawn` |
| Approve | Decline | 409 `request_state_changed`, state `approved` |
| Decline | Approve | 409 `request_state_changed`, state `declined` |
| Decline | Withdraw | 409 `request_state_changed`, state `declined` |
| Withdraw | Decline | 409 `request_state_changed`, state `withdrawn` |
| Decline | Undo or restore | 200, state `pending`, if the restore rules pass |
| Undo or restore | Second undo or restore | 200, state `pending` (repeat) |
| Restore | Player submits again | 200 with the existing pending request |
| Player submits again after a withdrawal | Restore of the older decline | 409 `request_superseded` |
| Any decision | Operator invalidation | Final states stay. A pending or declined request becomes `invalidated`. |
| Operator invalidation | Approve, decline, or withdraw | 409 `request_state_changed`, state `unavailable` |
| Operator invalidation | Undo or restore | 409 `request_superseded` |
| Enrollment removal | Approve | 409 `request_state_changed`, state `unavailable` |
| Approve | Enrollment removal | The catch stays. The removal does not change an approved request. |
| Deadline passes | Any action on an existing request | 409 `review_window_closed` |
| Ordinary decline | Decline with `block: true` | 200, state `declined`. The server adds the block. Undo is no longer available. |
| Decline with or without block | Decline with `block: false` | 200, state `declined` (repeat). An existing block stays. |
| Catch created for the trio by another path | Approve | 409 `request_superseded`. The request stays pending until the deadline. |
| Submit | Concurrent submit for the same trio | One pending request or one catch. The second gets 200 with that result. |
| Automatic approval | Concurrent submit for the same trio | One catch. The second gets 200 with outcome `already_caught`. |

### Restore and undo rules

Source: #506, #502 G3.

- Undo applies to an ordinary decline. It is available for 10 seconds after `declined_at`. Later calls fail with 409 `undo_expired`.
- A decline with a block has no undo. The owner can restore it.
- Restore applies to any declined request until the deadline.
- Undo and restore return the request to `pending` and remove the decline from the count.
- Both act only on the latest request for the trio.
- Both fail with 409 `request_superseded` if a newer request exists for the trio, a catch exists for the trio, or the request is invalidated.
- An active block does not stop undo, restore, or approval. A block prevents new attempts only. The owner can review a restored request while the block stays (#506).
- A paused request can be undone or restored. It stays pending and paused until eligibility returns.

## Cooldowns and limits

Source: #506, #502 G6 and G12.

### Cooldown rule

The cooldown key is the trio. Let n be the number of counted declines for the trio.

```text
submission_floor = last_requested_at + 10 seconds
decline_floor    = last_declined_at + (10 seconds if n == 1, else 10 minutes)   (only when n >= 1)
earliest_next    = the later of submission_floor and decline_floor
```

- `last_requested_at` is the latest `requested_at` for the trio.
- `last_declined_at` is the latest `declined_at` among counted declines.
- A decline counts at once. Undo and restore clear `declined_at` and remove it from the count.
- Self-leave turns a declined request into `withdrawn`, but its decline still counts. Leaving and rejoining does not reset the cooldown.
- Withdrawal does not count and does not reset the cooldown.
- Unblocking does not reset the cooldown.
- Counts end with the convention, because cleanup deletes request history.

### Worked examples

All times are seconds after the first submission at 0.

| Example | Events | n | Floors | Earliest next |
| --- | --- | --- | --- | --- |
| A. First decline | Submit 0, decline 30 | 1 | submission 10, decline 40 | 40 |
| B. Second decline | A, then submit 40, decline 50 | 2 | submission 50, decline 50 + 600 = 650 | 650 |
| C. Undo second decline | B, then undo at 55 | 1 | submission 50, decline 30 + 10 = 40 | 50. The request is pending again, so a new submission returns it. |
| D. Restore a decline | B, then restore the second request at 300 | 1 | submission 50, decline 40 | Pending again. After a later decline at 400, n is 2 and the earliest next is 1000. |
| E. Submission floor wins | Submit 0, decline 2, submit 12, withdraw 13 | 1 | submission 22, decline 12 | 22 |
| F. Withdrawal | Submit 0, withdraw 3 | 0 | submission 10 | 10 |

In example C, the earliest-next value matters only after the request leaves `pending` again.

### Per-player limit

- A player can create at most 30 requests in a rolling 10 minutes, across all suits and conventions.
- Requests created as automatic catches count.
- Refused submissions do not count.
- The limit is a server setting. #508 validates it against representative play and can tune it.
- The server reads the count from PostgreSQL. No shared cache exists.

### Refusal shape

Cooldown and limit refusals use HTTP 429:

```json
{"code": "cooldown_active", "detail": "Try again later.", "retry_after_seconds": 40}
```

- `code` is `cooldown_active` or `rate_limited`.
- `retry_after_seconds` is a positive integer, rounded up.
- The response also sets the `Retry-After` header to the same value.

### Blocks

Source: #506.

- The owner can decline and block a player for one suit and one convention.
- A block refuses later submissions from that player for that suit and convention, with the neutral 404 `catch_target_unavailable`.
- Blocks apply in manual and automatic mode.
- The owner can remove a block. Removal keeps the active cooldown.

## Response boundaries

Source: #511, #512, #502 G10.

### Player responses

| Server condition | Player result |
| --- | --- |
| Unknown, revoked, v1, or malformed tag | 404 `catch_target_unavailable` |
| Suit not active at the player's convention, no session, or suit disabled | 404 `catch_target_unavailable` |
| Convention not playable | 404 `catch_target_unavailable` |
| Suit owner disabled or not enrolled | 404 `catch_target_unavailable` |
| Player blocked for this suit and convention | 404 `catch_target_unavailable` |
| Player owns the suit | 409 `self_catch_not_allowed` |
| Player not enrolled, profile disabled, or no selected convention | 403 `catcher_ineligible` |
| Convention has no time zone or a closed window | 409 `catch_requests_unavailable` |
| Cooldown or per-player limit | 429 `cooldown_active` or `rate_limited` |
| Request created, approval required | 201, outcome `pending` |
| Catch created by automatic approval | 201, outcome `approved` |
| Pending request already exists | 200, outcome `already_pending` |
| Catch already exists | 200, outcome `already_caught` |
| Unexpected server failure | 500 with the existing sanitized shape |

A player whose request was declined with a block sees that request as `declined`. Later attempts get `catch_target_unavailable`. The player never sees a block code.

The player and owner request lists both map `invalidated` to the state `unavailable`. Neither party sees that an operator acted, or why.

### Owner request fields

The owner sees, for each request on their own suits:

- player display name and handle,
- suit, convention, and `requested_at`,
- state, and `undo_available_until` for an ordinary decline,
- prior decline count for the trio,
- whether the player is blocked for the suit and convention,
- whether approval is paused, without the cause,
- `review_deadline_at`.

The owner sees nothing about the player's other conventions, other suits, or catches.

### Visibility after the deadline

At the deadline, all request reads stop returning that convention's requests. Pending requests expire at the same instant. The product shows no individual expiry notice after closure. The server keeps no request history only to show a notice.

## Operations

Source: #502 G1. All paths sit under `/api/`. All bodies are JSON. Errors use `{"code","detail"}`, with `retry_after_seconds` added for 429. Every request read sets `Cache-Control: no-store`.

### Shared objects

`FursuitSummary`:

| Field | Type |
| --- | --- |
| `id` | integer |
| `tailtag_id` | string (UUID) |
| `name` | string |
| `photo_url` | string (URI) |

`PlayerRequest`:

| Field | Type |
| --- | --- |
| `id` | integer |
| `fursuit` | `FursuitSummary` |
| `convention_id` | integer |
| `state` | `pending`, `approved`, `declined`, `withdrawn`, or `unavailable` |
| `requested_at` | string (UTC ISO 8601) |
| `review_deadline_at` | string (UTC ISO 8601) |

`OwnerRequest`:

| Field | Type |
| --- | --- |
| `id` | integer |
| `fursuit` | `FursuitSummary` |
| `convention_id` | integer |
| `player` | object with `display_name` (string) and `handle` (string) |
| `state` | `pending`, `approved`, `declined`, `withdrawn`, or `unavailable` |
| `requested_at` | string (UTC ISO 8601) |
| `undo_available_until` | string (UTC ISO 8601) or null |
| `prior_decline_count` | integer |
| `player_blocked` | boolean |
| `approval_paused` | boolean |
| `review_deadline_at` | string (UTC ISO 8601) |

`Tag`:

| Field | Type |
| --- | --- |
| `fursuit_id` | integer |
| `state` | `current` or `revoked` |
| `tag_version` | integer |
| `payload` | string or null. Null when `state` is `revoked`. |

`Catch` keeps the existing confirmation shape: `id`, `caught_at`, `convention_id`, and `fursuit`. It adds `approved_at` (string, UTC ISO 8601).

### Owner tag operations

| Method and path | Request | Success | Errors |
| --- | --- | --- | --- |
| `GET fursuits/{fursuit_id}/tag/` | none | 200 `Tag` | 404 `fursuit_not_found`, 409 `fursuit_disabled` |
| `POST fursuits/{fursuit_id}/tag/replace/` | `{"expected_version": integer}` | 200 `Tag` | 404 `fursuit_not_found`, 409 `fursuit_disabled`, 409 `tag_version_conflict` |

A 409 `tag_version_conflict` body is `{"code","detail","current": {"fursuit_id", "state", "tag_version"}}`. In this body, `state` can also be `none`, which means the suit never had a tag. The error body never carries a payload. The client reads the tag again to get the payload. A caller who does not own the suit gets 404 `fursuit_not_found`. An owner without an enabled, completed profile gets the existing generic 403, as for other fursuit writes.

### Approval preference

| Method and path | Request | Success | Errors |
| --- | --- | --- | --- |
| `PATCH fursuits/{fursuit_id}/` | `{"catch_approval_mode": "manual" or "automatic"}` | 200 with the fursuit, including `catch_approval_mode` | Existing fursuit errors, plus 400 field validation for an unknown value |

The server stores `catch_approval_mode` whether the gate is on or off. The value has no effect while the gate is off.

### Player operations

| Method and path | Request | Success | Errors |
| --- | --- | --- | --- |
| `POST catches/preview/` | `{"payload": string}` | 200 `{"fursuit": FursuitSummary, "convention_id": integer}` | Player response table rows for tag, eligibility, and window |
| `POST catches/requests/` | `{"payload": string}` | 201 or 200 `{"outcome", "request": PlayerRequest or null, "catch": Catch or null}` | Player response table |
| `GET catches/requests/?convention_id=` | none | 200 `{"results": [PlayerRequest]}` for open windows only | 403 `catcher_ineligible` |
| `POST catches/requests/{id}/withdraw/` | none | 200 `PlayerRequest` | 404 `request_not_found`, 409 `request_state_changed`, 409 `review_window_closed` |

- Preview creates nothing.
- `outcome` is `pending`, `approved`, `already_pending`, or `already_caught`.
- `GET catches/requests/` without `convention_id` returns requests for every convention with an open window. Lists never include a request for a closed window. Actions on such a request follow the [closed-window table](#deadline-tie).
- A request that belongs to another player returns 404 `request_not_found`.

### Owner review operations

| Method and path | Request | Success | Extra errors |
| --- | --- | --- | --- |
| `GET catches/incoming-requests/?convention_id=&fursuit_id=` | none | 200 `{"results": [OwnerRequest]}` for open windows only | none |
| `GET catches/incoming-requests/summary/?convention_id=` | none | 200 `{"pending_count": integer, "fursuits": [{"fursuit_id", "pending_count"}]}` | none |
| `POST catches/incoming-requests/{id}/approve/` | none | 200 `{"request": OwnerRequest, "catch": Catch}` | `approval_paused`, `request_superseded` |
| `POST catches/incoming-requests/{id}/decline/` | `{"block": boolean}` | 200 `OwnerRequest` | none |
| `POST catches/incoming-requests/{id}/undo-decline/` | none | 200 `OwnerRequest` | `undo_expired`, `request_superseded` |
| `POST catches/incoming-requests/{id}/restore/` | none | 200 `OwnerRequest` | `request_superseded` |
| `DELETE catches/incoming-requests/{id}/block/` | none | 204 | none |

- Every action can also return 404 `request_not_found`, 409 `request_state_changed`, and 409 `review_window_closed`. All of these are HTTP 409 except `request_not_found`.
- A request on a suit that the caller does not own returns 404 `request_not_found`.
- Both list reads are ordered by `requested_at` descending, then `id` descending.
- `DELETE .../block/` with no block in place returns 204.

### Operator operations

Operators act through the existing operator tools, under the [operator authorization and audit contract](../operations/operator-authorization-audit.md).

| Action | Target | Effect |
| --- | --- | --- |
| `revoke_fursuit_tag` | tag record | Revokes the current tag. No replacement. |
| `invalidate_catch_request` | request | A pending or declined request becomes `invalidated`. |
| Set convention time zone | convention | Sets `time_zone` and applies the change rules. |

Operators can find and inspect requests. Operators cannot approve for an owner. Existing operator actions keep their effects and gain the invalidation effects in [Eligibility after submission](#eligibility-after-submission).

### Retired v1 operations

When the gate is on, these operations stop working:

| Operation | Result with the gate on |
| --- | --- |
| `POST conventions/{convention_id}/catch-credentials/resolve/` | 404 `catch_target_unavailable` |
| `POST catches/confirm/` | 404 `catch_target_unavailable` |
| `GET conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/` | 404 with the existing not-found shape |
| `POST conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-credential/rotate/` | 404 with the existing not-found shape |

The v1 player codes retire with no compatibility period (#504).

## Privacy and retention

Source: #501, #507, #508, #502 G8.

### Owners

| Duty | Owner | Rule |
| --- | --- | --- |
| Request deletion | #507 scheduled job | Deletes every request row and every block for a convention within 24 hours after its deadline. Retries daily. Failures are visible. Deletion never touches catches. |
| Operator audit | Operator audit contract, extended by #504 and #507 | #504 adds `revoke_fursuit_tag`. #507 adds `invalidate_catch_request`. Rows keep the existing no-expiry rule. |
| Backups | #507 recovery procedure | Documents PITR exposure and the cleanup rerun after a restore. |
| Aggregate metrics | #508 | Counts only, under [telemetry privacy](../architecture/backend/telemetry-privacy.md). No player, suit, request, or token identifiers. |

Scheduler provisioning needs a separate approval under ADR 0011.

### Recorded privacy conflicts

| Conflict | Decision |
| --- | --- |
| Deleted request rows stay recoverable from Render PITR for up to 7 days, and from any manual export. | Accepted. Any restore must rerun cleanup before the restored database serves traffic. |
| An audit row keeps `affected_record_id` after cleanup deletes the request. | Accepted. The ID holds no personal content. Audit evidence stays intact. |
| V0 has no account deletion. | Out of scope. A future account-deletion feature must delete that user's requests and blocks. |

## Migration and release

Source: #501, #504, #502 G9.

### Gate

- One server setting, `CATCH_REQUESTS_ENABLED`, controls the new flow. The default is off.
- When the gate is off, the new operations return 404 with the existing not-found shape, and the v1 operations work as today.
- When the gate is on, the new operations work, and the v1 operations are retired.
- The gate stays off on Staging until #506 and #507 have merged.
- Development can turn the gate on earlier.
- The simulator changes to the new flow in the same release that turns the gate on in Staging.

### Existing data

- Fursuit identities do not change.
- Existing catches keep `caught_at`. From this change on, `caught_at` means the server request time.
- `approved_at` is added with a database default of the current time, then backfilled from `caught_at` for existing rows. The database default keeps old application images able to insert catches.
- Every new column on an existing table must be nullable or have a database default (`db_default`). A Python-only default is not enough, because old images insert rows without the new columns. This covers `Convention.time_zone`, `Convention.review_deadline_at`, `Fursuit.tag_version` (database default 0), `Fursuit.catch_approval_mode` (database default `manual`), and `Catch.approved_at`.
- Catch provenance fields (`activation`, `catch_session`) do not change.
- `FursuitCatchCredential` stays in the database and becomes read-only when the gate is on.

### Safe state after each task

| After merge of | Schema change | Behavior with the gate off |
| --- | --- | --- |
| #503 | Convention `time_zone` and `review_deadline_at`, both nullable | No change for players. Operators can set zones. |
| #504 | Tag record and `Fursuit.tag_version` | v1 flow unchanged. New tag operations hidden. |
| #505 | CatchRequest, `Fursuit.catch_approval_mode` with database default `manual`, `Catch.approved_at` with database default and backfill | v1 flow unchanged. New v1 catches get `approved_at` close to `caught_at`. |
| #506 | Block record | No change |
| #507 | Audit actions, cleanup command | Cleanup runs on every schedule, whatever the gate state. With no requests, it deletes nothing. |
| #508 | None | Simulator gains the new flow behind the gate. |

No migration in this Feature drops or renames a table or column. #505 adds one data backfill for `approved_at`.

### Forward fix and rollback

- Forward fix is the default response to a defect.
- Application rollback follows the [rollback contract](2026-09-22-v0-migration-application-rollback.md).
- While the gate is off, rollback to an image from this Feature is a candidate for compatibility. It still needs the full review in the rollback contract, because constraints, defaults, and the backfill need proof.
- After the gate is on, rollback to an image older than #505 requires turning the gate off first. Pending requests stay in the database untouched. They become reviewable again after roll-forward if the window is still open.
- An image older than #507 has no cleanup. After roll-forward, the next cleanup run deletes every expired row. Reads hide those rows in the meantime, once the new image serves traffic.
- With the gate off, the v1 flow can create a catch for a trio that has a pending request. After the gate turns on again, approval of that request fails with 409 `request_superseded`.
- A later issue owns the contract migration that drops `FursuitCatchCredential` and the v1 code. Application rollback across that migration is not allowed.

## Failure modes

| Failure | Server behavior | Client recovery |
| --- | --- | --- |
| Lost response or timeout on submit | The first transaction either committed or did not. | Submit again with the same payload. The server returns the existing pending request or catch, or creates one. |
| Lost response on an owner or player action | The action either committed or did not. | Read the request list. Repeat the action only if the state did not change. |
| Lost response on tag replacement | Replacement either committed or did not. | Read the tag. Compare `tag_version`. Never replace again automatically. |
| 5xx response | Sanitized error. No partial state. | Retry reads. For writes, read state first. |
| Deadline passes during an action | The action uses the database time after locks. | 409 `review_window_closed`. Remove the convention's queue from view. |
| Competing action wins | 409 `request_state_changed` with the current state. | Show the current state. |
| Cleanup run fails | Rows stay. Reads already hide them. | Operators see the failure. The next daily run retries. |
| Restore from backup | Old request rows can come back. | Operators rerun cleanup before the database serves traffic. |
| Missing zone data in the container | Deadline computation fails. | #503 must prove zone data or pin `tzdata` before release. |

## Implementation choices

These rules are technical choices, not owner policy:

- Every submission creates a request row, including automatic approvals.
- `expired` is derived, not stored.
- The paths and field names in [Operations](#operations).
- The request ID is the default integer primary key, so audit rows can store it.
- Blocks are deleted with request history, because no submission is possible after closure.
- Undo and restore share one set of eligibility rules.
- New columns on existing tables use a database default or allow null, to keep old images compatible.
- The database time comes from `clock_timestamp()` after the locks.
- A decline with `block: true` on an already declined request adds the block.
- Submission runs the existing-result check after checks 1, 2, and 4 and a lookup of any known tag row, current or revoked. It runs before target checks 5 to 8. A retry gets its own pending request or catch back after its target changed (#505 G2).
- The PlayerProfile tier comes first in the lock order. Submission locks the catcher and the suit owner profiles in pk order, so two players who catch each other's suits cannot deadlock (#505 G4).
- Every request action locks the requesting player's PlayerProfile first. Approve locks both profiles in pk order. This serializes each action with that player's submissions (#506 G4).
- When a cooldown and the per-player limit both apply, the 429 carries the longer wait and its code. A tie returns `cooldown_active` (#506 G8).

## Test surfaces

Source: #502 G13. This table names the owning task and proof type for each clause. It sets no minimum test count. Proof types are unit, race, API, simulator, and physical device. Mobile widget tests and repository checks such as Semgrep count as unit proof.

| Clause | Owning task | Proof type |
| --- | --- | --- |
| Deadline rule, daylight saving, change rules, closure permanence | #503 | Unit, API |
| Unknown zone blocks the flow | #503, #505 | API |
| Tag creation, replacement, version conflict, revocation | #504 | API, race |
| Token secrecy, including error bodies | #504, #507 | Unit, API |
| Retired v1 operations behind the gate | #504 | API |
| One pending request and one catch per trio | #505 | Race |
| Request time as catch time, `approved_at` | #505 | API |
| Approval preference applies to new submissions only | #505 | API |
| Decisions, undo, restore, withdrawal | #506 | API, race |
| Cooldown examples A to F | #506 | Unit (table-driven) |
| Blocks and per-player limit | #506 | API, race |
| Response boundaries: neutral 404s, `unavailable` mapping, owner fields, 429 shape and header | #505, #506 | API |
| Eligibility matrix, including paused approval | #506, #507 | API |
| Operator invalidation, audit actions | #507 | API |
| Deadline visibility and cleanup | #507 | API, unit |
| Aggregate metrics without identifiers | #508 | Unit |
| Simulator pending and automatic paths | #508 | Simulator |
| Owner and player screens | #509 to #512 | Unit |
| Full journey, printed QR, poor connectivity, accessibility | #513 | Physical device |

## Physical-device evidence

#513 records evidence on one physical Android phone and one physical iPhone against Render Development. The evidence covers the items in #513. It names the build, environment, devices, and operating system versions. It contains no tokens, payloads, private URLs, or personal account data.

## Approvals

| Date | Decision | Source |
| --- | --- | --- |
| 2026-11-09 | Restore returns the latest request to pending, or fails with `request_superseded`. | #502 G3 |
| 2026-11-09 | The eligibility matrix, including cancellation and self-leave. | #502 G4 |
| 2026-11-09 | Printed payload `https://tailtag.app/t#<token>`. One-way door. | #502 G7 |
| 2026-11-09 | Accept 7-day PITR exposure, keep audit IDs after cleanup, account deletion out of scope. | #502 G8 |
| 2026-11-09 | Operator actions invalidate declined requests as well as pending ones. This amends refinement AC9. | #502 review R1 |
| 2026-11-09 | Player self-leave withdraws pending and declined requests. Owner self-leave keeps requests reviewable. | #502 review R2 |
| 2026-11-09 | Owners see `unavailable` instead of `invalidated`. | #502 review R3 |
| 2026-11-09 | A set convention time zone can change but cannot return to null. | #503 G1 |
| 2026-11-09 | #504 adds the `revoke_fursuit_tag` audit action. A replacement with version 0 on a never-tagged suit creates the first tag. | #504 G3, G8 |

The owner approved every #502 recommendation on 2026-11-09. The owner made the three review decisions on the same day, after independent review of this contract.
