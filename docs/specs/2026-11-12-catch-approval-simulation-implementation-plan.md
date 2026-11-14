# Catch approval simulation implementation plan (#508 PR 1b)

## Status

Draft. This plan covers PR 1b of [#508](https://github.com/TailTag-Game/tailtag/issues/508), the simulator half. PR 1a ([#528](https://github.com/TailTag-Game/tailtag/pull/528)) added the API half: decision metrics, the fixture review deadline offset, and `inspect-population-v2`. The owner approved the split on 2026-11-12.

The refinement in `.refinement/508.md` is the source of truth for the criteria. The frozen contract is [the reusable TailTag and catch request contract](2026-11-09-reusable-tailtag-catch-request-contract.md).

## Goal

The simulator runs the new catch request flow instead of the retired v1 confirm path. It covers pending and automatic paths, owner decisions, retries, duplicate convergence, session end, tag replacement, request expiry, and the per-player limit. Reconciliation tells pending requests apart from durable catches and finds duplicate or missing credit.

## Terms

- The v1 path is credential GET, resolve, confirm, and rotate. The gate retires it.
- The new flow is tag read, preview, request submission, owner review, and withdrawal.
- A trio is one player, one suit, and one convention.
- An archived report is a report file that a past run wrote. It must still validate.

## Constraint: archived reports

The report validator re-resolves the scenario descriptor and configuration of every report. It checks the plan digest, the operation names, the behavior counters, and the reconciliation check names. Schema 4 and schema 5 reports from Staging runs live in the maintainer archive and in `tools/simulator/baselines`.

So the plan follows these rules:

- Every new shape gets a new version: convention scenarios v3, journeys v2, report schema 6.
- The existing scenario files, config resolvers, operation names, counter sets, and check names stay as they are. They exist only to validate archived reports.
- The runner refuses old scenario versions with `FAIL configuration`, because the API no longer serves the v1 path once the gate is on.
- New sets live next to the old ones, for example `V6_OPERATIONS` next to `OPERATIONS`. New code never edits an old set.

## Design

### Scenario catalog (AC29)

| Scenario | Version | Use |
| --- | --- | --- |
| `convention-baseline`, `-hotspot`, `-post-event`, `-retry`, `-soak` | 3 | Load profiles on the new flow |
| `journeys` | 2 | Smoke: each request journey once |
| `request-limit` | 1 | The per-player limit and request expiry |

- `scenarios.py` accepts these versions and the new id. Old versions stay loadable for validation.
- v3 convention descriptors use the operation `request_traffic_schedule` and the assumption `request_flow`.
- Every host profile points at a new version. `normal`, `weekend`, `stop`, and `expiration` use baseline v3. The nightly profiles use their family's v3. `smoke` uses journeys v2. A new `request-limit-profile.json` runs the limit scenario.

### Configuration (AC14)

A new resolver, `resolve_request_traffic_config`, serves v3. It starts from the v2 traffic shape and changes three things:

- `failure.operations` takes `preview`, `submit`, and `read`.
- `failure.domain_case` takes `none`, `replaced`, `stopped`, or `expired`. `replaced` replaces the tag, where v2 `stale` rotated the credential.
- A new closed `review` section holds the decision mix:

| Key | Default | Meaning |
| --- | --- | --- |
| `automatic_share` | 0.25 | Share of suits set to automatic approval, chosen from the seed |
| `delay_min_seconds` | 5 | Shortest owner review delay |
| `delay_max_seconds` | 30 | Longest owner review delay |
| `approve_rate` | 0.85 | Share of manual requests that the owner approves. The rest are declined. |
| `poll_seconds` | 2 | How often each owner reads the incoming list |

### Operations and report schema 6 (AC27, AC28)

- `traffic_metrics.V6_OPERATIONS` is `auxiliary`, `preview`, `submit`, `review`, and `decide`, plus `read`. `review` is the owner list and summary. `decide` is approve, decline, undo, restore, withdraw, and block.
- `OperationMeter` takes its operation set as an argument. v2 runs keep `OPERATIONS`.
- `reports_v6.py` layers over schema 5, like schema 5 layers over schema 4. It uses `V6_OPERATIONS`, the v6 behavior counters, and the v6 checks.
- v6 behavior counters: `actors`, `actions`, `completed`, `pending`, `automatic`, `already_pending`, `already_caught`, `approved`, `declined`, `expected_rejections`, `retries`, `history_reads`, `exhausted`, `unused_budget`, and `cycles`.
- `evaluation.py` and `baselines.py` accept schema 6 with v6 operation names. Thresholds for v6 need limits for `preview`, `submit`, and `read`.

### Request traffic behavior (AC11, AC12, AC14, AC16 to AC19)

A new module, `request_behavior.py`, replaces `traffic_behavior.py`. It reuses the arrival schedule, effects, retries, and safety runtime.

Owner setup, once per suit:

1. Activate the suit for the run convention.
2. Start the catch session.
3. Read `GET /api/fursuits/<id>/tag/` and keep the payload.
4. Set `catch_approval_mode` with `PATCH /api/fursuits/<id>/`. The seed picks the automatic suits.

Catcher visit, for each planned suit:

1. `POST /api/catches/preview/`. Expect 200 for the suit and the run convention.
2. `POST /api/catches/requests/`. Expect 201 `pending` for a manual suit, 201 `approved` for an automatic suit, or 200 `already_pending` or `already_caught` after a lost response.
3. Repeats submit again and expect `already_pending` or `already_caught`.
4. With `duplicate_overlap`, two concurrent submissions must name the same request or catch.

Owner review:

- One task per owner reads `GET /api/catches/incoming-requests/?convention_id=` every `poll_seconds`.
- Each pending request waits a delay from the seed and its request id. The owner then approves or declines it. The seed and the request id also choose the decision.
- After the last arrival, owners decide every pending request before `owner_stop`.

Domain cases:

- `replaced`: the owner replaces the tag. The old payload gets 404 `catch_target_unavailable`. An existing pending request stays approvable.
- `stopped`: the owner stops the session. A new submission gets 404. An existing pending request stays approvable.
- `expired`: unchanged from v2. It needs the long expiration profile.

429 handling:

- A planned 429 counts as `expected_rejection`.
- Any other 429 is a correctness failure.
- The simulator never resubmits before `Retry-After`.

### Expectations and reconciliation (AC22 to AC26)

- `PopulationExpectations` gains a request map: trio to the request id and the last observed state.
- Reconciliation calls `inspect-population-v2`.
- Three new v6 checks: `request_state`, `request_duplicate`, and `request_credit`.

Reconciliation fails when:

- an approved request has no catch, or more than one
- a catch's `caught_at` differs from its request's `requested_at`
- a catch has no approved request
- a pending, declined, withdrawn, invalidated, or expired request has a catch
- one trio has more than one pending request
- a trio's stored state differs from the expected state.

An unplanned pending request at run end gives `INSPECT`.

### Journeys v2 (AC15, AC18)

Journeys v2 keeps the account and image journeys. It replaces the catch journeys:

| Journey | Proof |
| --- | --- |
| `pending_approve` | Submit, owner approves, catch in history with `caught_at` equal to the request time |
| `automatic` | Automatic suit, submit returns `approved` |
| `decline` | Owner declines, player sees `declined` |
| `decline_block` | Decline with block, later submit gets 404 |
| `undo` | Decline, undo inside 10 seconds, request pending again |
| `restore` | Decline, wait past the undo window, restore |
| `withdraw` | Player withdraws a pending request |
| `cooldown` | Decline, resubmit, 429 `cooldown_active` with `Retry-After` |
| `retry` | Lost response, resubmit returns the same request |
| `duplicate` | Two concurrent submissions name one request |
| `stopped_session` | Stop the session, new submit gets 404, pending stays approvable |
| `replaced_tag` | Replace the tag, old payload gets 404, pending stays approvable |
| `deactivated`, `self_catch`, `convention_mismatch`, `ineligible_catcher`, `not_owner` | Same proof as v1, on preview and submit |

### Limit and expiry scenario (AC20, AC21, AC30 to AC32)

`request-limit` v1 is deterministic, like journeys:

- 8 owners with 5 suits each give 40 suits. Two players take part.
- Provisioning sets `review_deadline_offset_seconds` to 1200.
- Owners never decide, so every request stays pending.
- `normal_play`: the first player creates one new request every 30 seconds for 10 minutes, 20 in all. Any 429 fails the journey.
- `abuse_limit`: the second player submits to a new suit every 2 seconds. Creates 1 to 30 succeed. The 31st gets 429 `rate_limited` with `Retry-After`. After that wait, the next submission succeeds.
- `expiry`: after the deadline, both players' lists and the owner lists are empty, and approval returns 409 `review_window_closed`.
- Reconciliation expects every request to be pending, with no catch.

The run takes about 21 minutes. It uses the journeys report shape, with its own journey names.

### Host and launcher

- `host_bridge.py` and the inspection channel allow `inspect-population-v2`.
- `__main__.py`, `host_operator.py`, and `host_runner.py` accept convention v3, journeys v2, and `request-limit` v1. They refuse the old versions for new runs.
- The fixture channel sends `review_deadline_offset_seconds` only for `request-limit`.

### Removed code (G2)

- `traffic_behavior.py`, `behavior.simulate_population`, and the v1 journey functions go away. `prepare_population` moves to a shared module.
- `gameplay.arm_session` reads the tag instead of the credential.
- Tests that only cover the removed code go away. Tests for shared parts move to the new flow.

## Delivery order

1. v3 resolver, `V6_OPERATIONS`, the meter change, report schema 6, evaluation, and baselines. Unit tests only.
2. Request traffic behavior and owner review, with fake-transport tests.
3. Request-aware reconciliation.
4. Journeys v2 and `request-limit`.
5. Scenario files, host profiles, host gates, removal of the v1 path, and documents.
6. Full simulator suite, `task doctor`, and an independent review.

The PR stays a draft until step 6 passes.

## Verification

- `task sim-check`, which runs the simulator lint, types, and tests.
- `task sim-report-validate` against one archived v5 report fixture, to prove archived reports still validate.
- `task doctor` and `git diff --check`.

## Implementation notes

These choices came up during the build. They do not change the criteria.

- A new `RequestCheck` enum holds the three request checks. The journeys keep the `Check` enum and its count.
- The limit scenario sends `review_deadline_offset_seconds` through `run_provisioned`, including the lease-renewal path. The host bridge treats the offset as part of the fixed partition, so any other value vetoes the session.
- The limit scenario has its own host safety tier, `host/request-limit-safety.json`, with 1800 seconds. The standard tier allows 900 seconds.
- `client.Reply` now carries `Retry-After` as whole seconds, for planned 429 checks.
- The host runner builds container commands with the newest scenario versions: convention 3, journeys 2, and `request-limit` 1.
- `task sim-request-limit` runs the limit scenario outside a host session.

## Out of scope

- The gate change. PR 2 owns it.
- The Staging run, the proof document, and the first v6 baseline. PR 3 owns them.
- Sentry widgets (G11).
