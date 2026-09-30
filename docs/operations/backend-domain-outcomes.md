# Backend domain outcomes

This guide explains the API's domain outcome signals: why catches, credential
lookups, catch sessions, and authentication succeed or are rejected. It covers
what each outcome and reason means, where to read it, what it cannot tell you,
and how to add a new one.

The contract is defined in the
[#213 spec](../specs/2026-09-30-domain-outcome-telemetry.md). Generic request,
latency, and server-error signals are in
[backend service signals](backend-service-signals.md). Log fields and request
lookup are in [backend logging](backend-logging.md).

## Signals and where they live

Each outcome is recorded twice, with the same values:

- a Sentry count of 1, named by the signal, with attributes `tailtag.outcome`
  and, when there is one, `tailtag.reason`;
- one INFO log line with `event` set to the signal, `tailtag_outcome`, and
  `tailtag_reason`, plus the usual `request_id`, `environment`, and `release`.

Use the Sentry metric for counts and rates. Use Railway service logs to follow
one request: search `@event:tailtag.catches.confirmation @tailtag_reason:credential_revoked`,
then take a line's `request_id` to the steps in
[backend logging](backend-logging.md#following-one-request).

Outcome lines and metrics carry no user, Clerk, fursuit, convention, catch, or
session ID, and never a credential or token.

| Signal | What it answers |
| --- | --- |
| `tailtag.catches.confirmation` | Did a catch attempt create a catch, find an existing one, or get rejected, and why? |
| `tailtag.conventions.credential_resolution` | Did a scanned credential resolve to a catchable fursuit, and if not, why? |
| `tailtag.conventions.catch_session` | Are fursuiters starting catch sessions, and how are sessions ending? |
| `tailtag.authentication.verification` | Why are presented tokens being rejected? |

## Outcomes and reasons

### Catch confirmation

| Outcome | Reason | Meaning |
| --- | --- | --- |
| `created` | | A new catch was recorded (HTTP 201). |
| `already_caught` | | The player had already caught this fursuit at this convention (HTTP 200). This is a normal result, not a failure. |
| `rejected` | `payload_invalid` | The body or credential payload was malformed. Usually a client bug. |
| `rejected` | `catcher_ineligible` | The catching player cannot play: profile ineligible or not enrolled. |
| `rejected` | `convention_mismatch` | The catching player's active convention is not the credential's convention. |
| `rejected` | `self_catch` | The player scanned their own fursuit. |
| `rejected` | a target reason | The fursuit cannot be caught right now. See [target reasons](#target-reasons). |

### Credential resolution

| Outcome | Reason | Meaning |
| --- | --- | --- |
| `resolved` | | The credential identifies a catchable fursuit. |
| `rejected` | `payload_invalid` | The body or credential payload was malformed. |
| `rejected` | `caller_ineligible` | The scanning player cannot play at this convention. |
| `rejected` | `convention_unknown` | The convention in the URL does not exist. Usually a client bug. |
| `rejected` | a target reason | See [target reasons](#target-reasons). |

### Target reasons

Both catch confirmation and credential resolution return one identical 404 for
every target reason, so players cannot learn why a target is unavailable.
Only the telemetry distinguishes them. For catch confirmation, when several
apply, the first in this table is recorded.

Credential resolution checks in its own order: `activation_inactive` comes
before `target_ineligible`, and a convention that is not playable is reported
as `target_ineligible`, not `convention_not_playable`.

| Reason | Meaning | What a rise usually means |
| --- | --- | --- |
| `credential_unknown` | No credential has this token, or it belongs to another convention. | Guessing, a wrong-convention scan, or a client bug. |
| `credential_revoked` | The credential was revoked or rotated. | Stale credentials: players are scanning an old code. |
| `convention_not_playable` | The convention is missing or not playable. | The convention was paused or ended. |
| `target_ineligible` | The fursuit or its owner cannot currently be caught. | Owner or fursuit disabled, or the owner left the convention. |
| `activation_inactive` | The fursuit is not activated at this convention. | The owner deactivated it. |
| `session_inactive` | The fursuit has no running catch session. | The owner stopped the session, or never started one. |
| `session_expired` | The fursuit's catch session ran past its expiry. | Owners are not restarting sessions. |

### Catch sessions

| Outcome | Reason | Meaning |
| --- | --- | --- |
| `started` | | A new catch session was created. Restarting a session that is still running records nothing. |
| `start_rejected` | `owner_ineligible` | The owner cannot play at this convention. |
| `start_rejected` | `not_enrolled` | The owner is not enrolled. |
| `start_rejected` | `activation_ineligible` | The fursuit's activation cannot host a session. |
| `ended` | `owner` | The owner stopped it. |
| `ended` | `operator` | An operator ended it. |
| `ended` | `eligibility_lost` | The fursuit, owner, enrollment, activation, or convention stopped being eligible. |
| `ended` | `expired` | It had reached its expiry when it was ended. |

Session outcomes are recorded only after the database transaction commits.

### Authentication

Every outcome is `rejected`. A request with no `Authorization` header records
nothing here; on a protected route it appears only as a 401 in the request
metric.

| Reason | Meaning | What a rise usually means |
| --- | --- | --- |
| `malformed_header` | The header is not `Bearer <token>`. | A client bug. |
| `token_expired` | The Clerk session token has expired. | The mobile app is not refreshing tokens. |
| `token_not_yet_valid` | The token's issue or start time is in the future. | Clock skew on a client or server. |
| `token_invalid` | Signature, key ID, audience, authorized party, or token type is wrong. | A key or configuration mismatch between Clerk and the API, or probing. |
| `claims_missing` | The token verified but has no usable session or subject claim. | A Clerk token template or configuration change. |
| `verifier_misconfigured` | The API could not verify any token: key missing or unusable. | An API configuration problem. Clients still receive 401. |
| `user_resolution_unavailable` | The token verified, but the TailTag user could not be resolved (HTTP 503). | A database problem. |
| `other` | Clerk gave no reason, or the SDK failed unexpectedly. | Investigate from the request's log lines. |

## Common questions

- **Is the API up but catches are failing?** Compare
  `tailtag.catches.confirmation` `rejected` counts by `tailtag.reason` with
  `created` and `already_caught`. A rise in one target reason names the cause.
- **Stale credentials or server errors?** Stale credentials show as
  `credential_revoked`. Server errors record no domain outcome; they appear as
  `5xx` in `tailtag.http.server.requests` and as Sentry issues.
- **Are duplicate scans a problem?** No. `already_caught` is a successful
  outcome and returns 200.

## Limits

- A session that expires while nobody touches it records no `ended` outcome.
  Expiry is visible when a catch or scan is rejected with `session_expired`, or
  when the session is later ended.
- After an expired session has been ended, rejections report
  `session_inactive`.
- Outcome counts do not add up to the request metric. Unauthenticated requests
  and unexpected server errors have no domain outcome.
- `verifier_misconfigured` still returns 401 to clients, so clients cannot tell
  it from a bad token.

## Adding an outcome or reason

Values are add-only, because dashboards and alerts depend on them. Renaming or
removing one needs a maintainer decision and a plan for the dashboards that use
it.

1. Check the new value against the
   [telemetry privacy policy](../architecture/backend/telemetry-privacy.md). A
   value names a class of result. It never contains an ID, token, or free text.
2. Add the value to `Signal`, `Outcome`, or `Reason` in
   `services/api/observability/outcomes.py`. The privacy allow-list is derived
   from these enumerations, so no second list needs editing.
3. Record it with `record_outcome(signal, outcome, reason)` at the point where
   existing code already decides the result: the view's exception mapping, or
   the service that makes the transition. Wrap transitions made inside a
   database transaction in `transaction.on_commit`. Do not add a query or check
   only to choose an outcome.
4. Do not call `sentry_sdk.metrics` from feature code. The
   `direct-sentry-metrics` Semgrep rule rejects it.
5. Add a row to the acceptance tests in
   `services/api/tests/test_domain_outcome_telemetry.py` and to the tables in
   this guide.
