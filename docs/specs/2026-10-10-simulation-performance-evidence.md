# Convention-simulation performance and regression evidence — implementation contract

Approved outcome: issue #229, AC1–AC21 in the
[approved refinement](https://github.com/TailTag-Game/tailtag/issues/229). The
maintainer approved every gap recommendation (G1–G11c) on 2026-10-10 and asked
for implementation through ADW.

## Phase ledger and scope guard

DEVELOPMENT / STANDARD EXPANDED. Assurance: TEST ADEQUACY and DATA INTEGRITY.
Reports, evaluations and baselines are evidence, so they must stay immutable,
honest about missing data, and privacy-bounded. No architect or security
challenger trigger applies: there is no new service, persistence store,
authorization boundary or distributed design.

**Outcome.** Client-side per-operation measurement goes into report schema 5.
Offline commands evaluate, promote and trend runs:

- `report evaluate`
- `baseline promote`
- `report trend`

Committed threshold and baseline records under `tools/simulator/baselines/`
make the evidence comparable and reviewable. Correctness remains the hard gate.
No SLO is claimed.

**Non-goals.**

- Backend changes.
- Automated Sentry or Railway retrieval.
- Provider tokens on the host.
- Per-route metric keys and warm-up exclusion.
- Changing the run `outcome` because of performance.
- A committed per-run history.
- Migrating v1–v4 reports.
- Scheduling (#230).
- Changes to traffic shape, guardrails or host provisioning.
- New dependencies.

**Expected change surface.**

- Simulator code:
  - `traffic.py`
  - `traffic_effects.py`
  - `traffic_behavior.py`
  - `convention.py`
  - `reports.py`
  - `provenance.py`
  - `__main__.py`
- New simulator modules:
  - `traffic_metrics.py`
  - `reports_v5.py`
  - `evaluation.py`
  - `baselines.py`
- Tests under `tools/simulator/tests/`.
- `tools/simulator/baselines/README.md`.
- Root `Makefile`.
- Documentation:
  - `tools/simulator/README.md`
  - `docs/operations/simulation-host.md`
  - `docs/operations/telemetry-evidence-preservation.md`
- This spec and its plan.

**Proof.**

- Behavioral red/green evidence for each unit.
- `make sim-check`, `./scripts/doctor.sh` and `git diff --check`.
- One review per unit plus a whole-change review.
- The AC20 live proof, under separate authorization, after merge.

**Reversibility.** TWO-WAY DOOR. Schema 5 is additive and versioned. Existing
reports keep their contract. Baseline and threshold files are ordinary
reviewed repository files. Nothing writes outside the operator-chosen local
paths.

## Architecture and alternatives

Measurement lives in the simulator process, at the existing
`TrafficRuntime.request` boundary (G1). Every SIMULATION workload attempt
already passes through it, under the traffic semaphore and modeled timeout.

The run report records facts only (G4). Judgment is offline and repeatable:
evaluation reads an immutable report plus versioned configuration, and writes
a separate artifact. Re-evaluating an old run against a newer baseline
therefore never rewrites evidence.

Rejected alternatives:

- Sentry percentiles as the primary source: sampled, manual, and server-only.
- An embedded verdict: it makes reports mutable judgments.
- A histogram approximation: exact samples fit the existing 1,000,000-request
  safety ceiling as 8 MB `array('d')` storage.

## U1 — Measurement and report schema 5

### Operation vocabulary (G3, AC9)

`OPERATIONS = ("auxiliary", "resolve", "confirm", "read")`, plus a derived
`total`.

| Operation | Source | Backend route template (`http.route`) |
| --- | --- | --- |
| `resolve` | `TrafficEffects.call("resolve", …)` | `api/conventions/<int:pk>/catch-credentials/resolve/` |
| `confirm` | `TrafficEffects.call("confirm", …)` | `api/catches/confirm/` |
| `read` | `TrafficEffects.call("read", …)`: history reads | `api/catches/` |
| `auxiliary` | Bootstrap `_CountedClient` sends without effects | Several routes, listed below |

The `read` name matches the existing `failure.operations` vocabulary.
`auxiliary` covers population preparation, fursuit activation, session arming,
and domain-transition rotate/stop. Its routes are
`api/conventions/<int:pk>/fursuit-activations/<int:fursuit_pk>/`, its
`catch-credential/rotate/` and `catch-session/` children, and the preparation
routes used by `behavior.prepare_population`.

`TrafficRuntime.request(send, *, operation, injection="none")` requires an
`operation` in `OPERATIONS`. Callers pass their true label. The
`_CountedClient` default of effects operation `"read"` stays, because it *is*
the history read. Bootstrap clients without effects pass `"auxiliary"`.

### Measured attempt and classification (G9, AC8, AC10)

A measured attempt is an invocation of the `send` callable inside
`TrafficRuntime.request` (inside `invoke()`), after the traffic semaphore is
acquired.

Timing uses `self.clock.monotonic()`:

- Start: when the HTTP request is actually issued. The traffic runtime sets a
  context-local callback that `ApiClient._send` invokes immediately before
  `self._client.stream(...)`. By then the bearer token has been resolved and
  the safety request slot acquired.
- Fallback start: a `send` that never reaches `ApiClient` (test doubles) is
  timed from `send()` invocation.
- End: when `send()` returns or raises.

The client reads the whole body inside `send`, so the end point is the last
body byte. Excluded from latency:

- traffic semaphore queue wait, which stays visible through scheduling lag;
- Clerk token refresh (AC8);
- waits for the shared safety request slot.

Documentation states that latency includes host-to-ingress network time. This
start point replaces the original "immediately before `send()`", following U1
review finding F1.

`injection` is supplied by `TrafficEffects` from its pre-drawn values. It is
`"pre_send"` when the operation is selected and `pre < pre_send_failure_rate`.
Otherwise it is `"lost_response"` when the operation is selected and
`outcome < lost_response_rate + timeout_rate`. Otherwise it is `"none"`.

Each measured attempt is classified exactly once:

| Observation | Class | Latency sample? |
| --- | --- | --- |
| `send` raised and `injection == "pre_send"` | `injected` | no |
| reply received and `injection == "lost_response"` | `injected` | no |
| reply 200–299 | `success` | yes |
| reply 500–599 | `server_error` | yes |
| any other reply status | `client_error` | yes |
| `TransportFailed(timed_out=True)`, or the modeled `httpx.TimeoutException` raised by `request` | `timeout` | no |
| `TransportFailed(timed_out=False)` or `RequestFailed` | `transport_error` | no |
| any other exception (`TrafficStopped`, `CancelledError`, `SafetyAborted`, …) | not recorded | — |

Not-recorded attempts were cut off by a stop. A stopped run is inconclusive
anyway (U2).

`TrafficRuntime.expected_rejection(operation)` replaces the two
`runtime.record("expected_rejections")` call sites in `traffic_behavior.py`
(the confirm negative path and the resolve expiry path). It increments the
existing counter and moves one `client_error` count for that operation to
`expected_rejection`. It raises `ValueError` if no `client_error` exists for
that operation.

Derived values:

- Responses = `success + expected_rejection + client_error + server_error`.
- Rate denominator = attempts − `injected`.
- Error rate = (`client_error + server_error + transport_error`) ÷ denominator.
- Timeout rate = `timeout` ÷ denominator.
- Throughput = responses ÷ `window_seconds`, where `window_seconds` =
  traffic `generation_seconds + drain_seconds`.
  - `auxiliary` includes population preparation that happens before the
    schedule window, so `auxiliary` and `total` throughput are not
    window-bounded workload rates. This was accepted and documented after U1
    review finding F2.
  - Per-operation `resolve`/`confirm`/`read` throughput is the comparable
    measure. No threshold or trend column uses throughput.
- Percentiles use the nearest rank on sorted millisecond samples: rank
  `ceil(q·n)`, with p50, p95, p99 and max. Values are rounded to 3 decimal
  places.

Each operation stores its samples in an `array('d')`. Raw samples, statuses,
URLs and bodies never leave the process.

Existing traffic counters, attempt accounting, plan digests, scheduling and
effects behavior are unchanged. Scenario descriptors are unchanged.

### Report schema 5 (AC11, G11c)

`RunReport` writes `schema_version: 5` only for `convention-*` scenario
version 2. Every other scenario keeps writing schema 4. The only difference
from schema 4 is the `performance` object:

```json
"performance": {
  "duration_seconds": {"value": 412.3, "reason": null},
  "window_seconds": {"value": 301.2, "reason": null},
  "execution_mode": {"value": "container", "reason": null},
  "attempts": {"value": {"<op|total>": {
      "success": 0, "expected_rejection": 0, "client_error": 0,
      "server_error": 0, "timeout": 0, "transport_error": 0, "injected": 0}},
    "reason": null},
  "throughput": {"value": {"<op|total>": 12.5}, "reason": null},
  "latency_percentiles": {"value": {"<op|total>": {
      "samples": 0,
      "p50": {"value": null, "reason": "not_observed"},
      "p95": {"value": null, "reason": "not_observed"},
      "p99": {"value": null, "reason": "not_observed"},
      "max": {"value": null, "reason": "not_observed"}}},
    "reason": null},
  "resource_context": {"value": null, "reason": "not_observed"}
}
```

Field rules:

- **`execution_mode`** is `"container"` when the packaged `source.json`
  provenance path is used, and `"checkout"` for a Git checkout. A new
  `provenance.execution_mode(root)` uses the same detection as `load_source`.
  It is recorded by `RunReport.record_execution_mode(mode)` next to
  `record_source`, and is otherwise `unavailable()`. The report cannot attest
  host identity: the container has no Docker socket, and environment
  relabeling is forbidden. Evaluation therefore adds host identity from the
  host companion (U2).
  - This narrows AC11's wording, which asked the report itself to record
    external host, platform and image ID. That is impossible from inside the
    container, so the report records the observable mode and evaluation
    attests the host.
- **`attempts`, `throughput`, `latency_percentiles`, `window_seconds`.** These
  four are written by `RunReport.record_traffic(snapshot, performance)` at the
  same points the traffic snapshot is written today. They are observed exactly
  when `results.traffic` is observed. Otherwise they are
  `unavailable("not_observed")`. Throughput is unavailable `not_observed` when
  the window is 0.

`reports_v5.validate` checks the following, then projects to schema 4 (with
the schema-4 constant `performance`) and delegates to `reports_v4.validate`:

- The keys are exactly the ones above. Operation keys are exactly
  `OPERATIONS ∪ {"total"}`, and each counts dict has exactly the seven classes.
- `total` is the per-class sum of the operations.
- `total.injected == traffic.injected`.
- `total.expected_rejection == traffic.expected_rejections`.
- The sum of all `total` classes ≤ `traffic.attempts`.
- Non-injected `total` ≤ `traffic.sent`.
- `samples` == responses for each operation.
- Each percentile is null exactly when samples == 0.
- `p50 ≤ p95 ≤ p99 ≤ max`, all finite and ≥ 0.
- Throughput equals responses ÷ window (relative tolerance 1e-9).
- `window_seconds` == traffic `generation_seconds + drain_seconds`
  (relative tolerance 1e-9).
- `resource_context == unavailable("not_observed")`.

Strictness is unchanged: unknown keys, duplicate keys and malformed values fail
with only `FAIL report`. `load_report`, `report validate` and host completion
accept schema 5.

## U2 — Thresholds and offline evaluation

### Comparable key (G6, AC14)

```json
{"scenario_id": "convention-baseline", "scenario_version": 2,
 "descriptor_digest": "<64 hex>", "plan_digest": "<64 hex>",
 "environment": "staging", "execution_context": "external_host:linux/amd64"}
```

- `plan_digest` is `results.traffic.value.plan_digest`. It hashes the resolved
  traffic configuration (including the pool name, seed and limits).
- `environment` is `target.starting.value.environment` for Staging, and
  `"local"` for a local target.
- `execution_context` is `"external_host:<platform>"` when a valid host
  companion for the same `run_id` is supplied and `execution_mode` is
  `container`. Otherwise it is the report's `execution_mode` value, or
  `"unknown"`.

The key is `null` when traffic was not observed.

A run is comparable to a baseline only on an exact key match. These
differences are caveats, not incomparability:

- `simulator_sha_differs`
- `dependency_lock_differs`
- `image_differs`

A different backend build is expected and is not flagged.

### Threshold file (G7, AC15)

Threshold files are `tools/simulator/baselines/<slug>.thresholds.json`, with
`"kind": "thresholds"` and `schema_version` 1. Validation is strict: closed
keys, no duplicates, and at most 64 KiB. Every value object is
`{"value": number, "assumption": "<1–500 printable chars>"}`:

```json
{"schema_version": 1, "kind": "thresholds", "key": {…},
 "minimum_samples": {"p95": {…}, "p99": {…}},
 "operations": {"<op|total>": {"p95_ms": {…}, "p99_ms": {…},
                               "error_rate": {…}, "timeout_rate": {…}}},
 "regression": {"p95_percent": {…}, "p99_percent": {…}, "minimum_delta_ms": {…}},
 "saturation": {"peak_cpu_percent": {…}, "lag_seconds": {…}, "steal_ticks_delta": {…}}}
```

Every limit inside an operation is optional. `regression` and `saturation` are
required.

The proposed defaults, written by `baseline promote --initial-thresholds`, are:

- **Latency limits:** 2× the baseline value, rounded up to 1 ms.
  - `p95_ms` only for operations with at least as many baseline samples as
    the p95 minimum (200).
  - `p99_ms` only for operations with at least as many as the p99 minimum
    (1,000).
- **Rate limits:** error and timeout rate at max(2× baseline, 0.01), for
  operations with at least 200 baseline samples.
- These rules mean a run like its own baseline evaluates `acceptable` rather
  than `inconclusive`.
- **Minimum samples:** 200 for p95 and 1,000 for p99.
- **Regression:** p95 +25%, p99 +50%, ignored unless the change is at least
  20 ms.
- **Saturation:**
  - peak CPU 160: Docker `CPUPerc` units, 80% of 2 vCPUs;
  - lag 1.0 s;
  - steal 1,500 USER_HZ ticks.
- Each value gets assumption text. The maintainer reviews these numbers in the
  promotion PR. The 0.01 rate floor and the saturation values are proposals,
  not observed facts.

### Optional inputs

- **Host companion:** the `host.json` written by `host_artifacts`. Accepted
  only if `run_id` matches and the closed evidence keys validate. Generator
  summary:
  - `samples`;
  - peak `cpu_percent`;
  - peak `memory_percent`;
  - steal delta = last − first non-null `cpu_steal_ticks`.

  Null samples are ignored, and a field with no values is null. Platform and
  `image_id` come from the companion.
- **Operator context** (G8, AC16): `schema_version` 1 and `run_id`, plus
  `signals` with exactly these keys:
  - `http_5xx`
  - `server_latency`
  - `db_connections`
  - `worker_timeouts`
  - `restarts_or_oom`
  - `runtime_resources`
  - `domain_outcomes`

  Each value is one of `observed_normal`, `observed_pressure` or
  `not_observed`. No other keys and no free text are allowed. The context is
  copied verbatim and never changes the verdict.

### Evaluation (G4, G5, AC12, AC13)

```
report evaluate REPORT [--host-companion PATH] [--context PATH]
                       [--baselines-dir DIR] [--out PATH]
```

The command:

- Validates the report with `load_report`. It refuses with `FAIL evaluation`
  if the report is invalid or its schema is not 4/5.
- Discovers, in `--baselines-dir` (default `tools/simulator/baselines/` under
  the repository root; there is no container default), the
  threshold and baseline files whose key equals the run key. More than one of
  either kind refuses.
- Writes the artifact with O_EXCL and mode 0600. The default path is
  `<report dir>/<run_id>.evaluation-<UTC YYYYmmddTHHMMSSZ>.json`. It refuses
  to overwrite and never modifies its inputs.
- Prints `PASS evaluation <verdict>` followed by a short fixed-format summary.
- Makes no network request.

Artifact (`schema_version` 1, `kind` `"evaluation"`) keys:

- **`evaluated_at`.**
- **`report`:** `run_id`, `sha256` of the exact file bytes, `schema_version`,
  `scenario_id`, `scenario_version`, `outcome`, `correctness`,
  `simulator_sha`, `dependency_lock_sha256`.
- **`key`.**
- **`observation`:** `started_at` and `ended_at` from the report timing,
  `window_seconds`, and `backend` (`deployment_id`, `source_sha`,
  `environment`, or null).
- **`thresholds`:** `{path, sha256}` or null.
- **`baseline`:** `{path, report_sha256}` or null.
- **`generator`:** `{status: "observed"|"not_observed", samples,
  peak_cpu_percent, peak_memory_percent, steal_ticks_delta, lag_seconds,
  image_id, platform}`.
- **`backend_context`:** the signals or null.
- **`checks`:** a list of
  `{check, operation, metric, observed, limit, baseline, result}`.
  - `check` is one of `absolute`, `regression`, `saturation`.
  - `result` is one of `passed`, `breached`, `regressed`, `inconclusive`.
- **`caveats`:** a sorted closed list.
- **`verdict`.**
- **`reasons`:** a sorted closed list.
- **`statement`:** this fixed text: "Thresholds and baselines are documented
  assumptions for regression evidence; they are not production SLOs or
  capacity claims."

Check rules:

- Absolute checks run for each configured limit:
  - A percentile check is `inconclusive` when samples are below the minimum.
  - A rate check is `inconclusive` when the denominator is 0.
  - Otherwise the result is `breached` if observed > limit, else `passed`.
- Regression checks run only for an operation and metric whose limit
  (`p95_ms` or `p99_ms`) is configured in the thresholds file, and only when
  both the run and the baseline have that percentile. They use the thresholds'
  regression settings. Operations without a configured limit, such as a
  low-volume `auxiliary`, are not regression-checked. This rule was added
  after U3 implementation showed that the original "every operation" rule
  made realistic runs permanently inconclusive.
  - The result is `inconclusive` if either side is below the minimum samples.
  - It is `regressed` when observed > baseline·(1 + pct/100) **and**
    observed − baseline ≥ `minimum_delta_ms`.
- Saturation checks run when observed; CPU and steal require a companion.
  Exceeding a limit sets the reason `generator_saturated`.

The verdict is the first that applies:

1. **`not_evaluated`**: outcome ≠ `passed` (reason `run_not_passed`),
   correctness ≠ `passed` (`correctness_not_passed`), schema 4
   (`performance_not_measured`), or a supplied host companion records a host
   run that did not pass (`host_run_not_passed`). The last case means a
   companion `stop_reason` that is not null, `hard_stop` true, a non-zero
   `container_exit_code`, or `report_attribution` other than `matched`. This
   rule was added after U2 review finding M1.
2. **`inconclusive`**, with reasons from:
   - `traffic_stopped` (`stop_reason` not null)
   - `generator_saturated`
   - `insufficient_samples`
   - `no_thresholds`
   - `no_baseline`
   - `not_comparable` (no key)
3. **`breached`**: any absolute check breached.
4. **`regressed`**: any regression check regressed.
5. **`acceptable`**.

All applicable reasons are listed. Breached and regressed checks are listed
even under `inconclusive`. Performance never alters the report or its
`outcome`.

## U3 — Baselines, promotion and trend

### Baseline record (G2, AC17)

Baseline records are `tools/simulator/baselines/<slug>.baseline.json`, with
`schema_version` 1 and `kind` `"baseline"`. Validation is strict and the file
is at most 64 KiB. Keys:

- `key`
- `report`:
  - `run_id`
  - `sha256`
  - `started_at`
  - `simulator_sha`
  - `dependency_lock_sha256`
  - `backend` (`deployment_id`, `source_sha`, `environment`)
  - `execution` (`image_id`, `platform`, or null)
- `metrics` (for each `<op|total>`):
  - `samples`
  - `p50`
  - `p95`
  - `p99`
  - `max`
  - `error_rate`
  - `timeout_rate`
  - `throughput`
- `rationale`
- `supersedes` (the previous `report.sha256`, or null)

Values in `metrics` are nullable. `rationale` is 1–1000 printable characters
with no newlines. The slug is
`<scenario_id>-v<version>-<plan_digest[:12]>-<context with "/" and ":" → "-">`.
There are no personal fields; git and PR history is the promoter trail. Full
reports and evaluations stay outside git in the maintainer archive, recorded by
hash.

### Promotion (G10, AC18)

```
baseline promote REPORT --rationale TEXT [--host-companion PATH]
                        [--context PATH] [--baselines-dir DIR] [--initial-thresholds]
```

The command evaluates internally, never trusting a supplied evaluation file.
It refuses with `FAIL promotion`, and writes nothing, unless all of these hold:

- The report is schema 5 and valid.
- Outcome and correctness are both `passed`.
- `environment == "staging"`.
- The verdict is `acceptable`, or `inconclusive` with reasons ⊆
  {`no_baseline`, `no_thresholds`}.
- No `absolute` or `regression` check is `breached` or `regressed`. This
  closes the case where a threshold breach on a run without a baseline would
  otherwise read as promotable `inconclusive`.

On success it writes or replaces the single baseline file for the key, with
`supersedes` set to the prior record's report hash. With
`--initial-thresholds` it also writes a thresholds file, but only when none
exists for the key; otherwise it refuses. It also refuses when the proposal
would configure no operation limits, because no operation has 200 or more
baseline latency samples. This rule was added after whole-change review
finding M1: it stops an `acceptable` verdict from resting only on saturation
checks. Writes are atomic: a temp file in
the same directory, then replace.

Promotion takes effect only when the PR that changes these committed files
merges. Only `__main__.py` imports `baselines.py`. No run, evaluate or trend
path calls the writer or writes under the baselines directory. Promotion also
refuses when `<slug>.baseline.json` already exists but is not the baseline that
evaluation matched for this key; this guards against slug collisions (U3 review
finding M1). Trend skips non-regular files, such as FIFOs, without reading
them.

### Trend (G11b, AC19)

```
report trend DIR [--baselines-dir DIR]
```

The command scans `DIR` recursively. The bounds are 2,000 files, 1 MiB per
file, and depth 4. It classifies each JSON file as one of: a valid
schema-4/5 report, an evaluation, or a host companion. It pairs companions and
evaluations to reports by `run_id` and report hash, using the newest
evaluation.

Files beyond the count or depth bounds are not read and are counted as
skipped. Evaluations and companions that match no report are ignored and not
counted. A missing verdict prints `-`.

It groups reports by comparable key. For each key it prints a time-ordered
table with these columns:

- `started_at`
- `run_id`
- backend `source_sha[:12]`
- correctness
- verdict, or `-`
- p95 and p99 for each operation that has samples
- error and timeout rates

The active baseline row is marked `*`. The command ends with
`skipped <n>` for invalid or unrelated files. It never writes anything.

### CLI and Make

The new commands print only fixed `PASS …`/`FAIL …` lines, plus the bounded
tables and summaries described above. The Make targets are:

- `sim-report-evaluate REPORT= [HOST_COMPANION= CONTEXT= OUT=]`
- `sim-report-trend DIR=`
- `sim-baseline-promote REPORT= RATIONALE= [HOST_COMPANION= CONTEXT= INITIAL_THRESHOLDS=1]`

### Documentation (G2, G8, AC16, AC17)

- README: a section on performance evidence covering measurement semantics,
  the operation and route map, classification, schema 5, evaluation verdicts,
  comparability, promotion and trend.
- `docs/operations/simulation-host.md`: how to collect `host.json` and run
  `evaluate`/`promote`, plus fixed backend query recipes for #212–#214:
  - `tailtag.http.server.requests` by `http.route`/status class;
  - Sentry p95 by transaction;
  - `tailtag.db.connection.attempts`/`.duration`;
  - gunicorn `WORKER TIMEOUT` in Railway logs;
  - Railway CPU/memory/restart events;
  - #213 domain outcome counts.

  Each recipe maps to an operator-context signal, filtered by `sentry.release`
  or the deployment and the evaluation's UTC window.
- `docs/operations/telemetry-evidence-preservation.md`: correct the claim that
  reports are kept in the repository. Reports and evaluations live in the
  maintainer archive. Only reviewed baselines and thresholds are committed.
- `tools/simulator/baselines/README.md`: what lives there and how a promotion
  PR is reviewed.

## U4 — Live proof (AC20)

This runs after U1–U3 merge, under separate explicit authorization.

1. Build and install the merged simulator image through the #228 release
   flow.
2. Run the `host/normal-profile.json` workload twice.
3. Evaluate run 1 with its companion and promote it with
   `--initial-thresholds` in a PR.
4. After that PR merges, evaluate run 2 against the baseline.
5. Record a sanitized proof document,
   `docs/specs/<date>-simulation-performance-evidence-staging-proof.md`.

Preserve failed or aborted attempts. Make no capacity or SLO claim. If the
observed run-to-run variation contradicts the AC15 defaults, return for a
revised threshold decision.

Completed 2026-10-10. See the
[Staging proof](2026-10-10-simulation-performance-evidence-staging-proof.md):
run 2 was `acceptable` against the run-1 baseline, and the variation was within
the AC15 defaults.

## Frozen test surface and failure/value map

Tests use real simulator modules. Fakes are allowed only at existing seams:

- the injected traffic `Clock`;
- `httpx.MockTransport` and the existing support helpers for the network;
- temporary directories.

Do not mock internal collaborators.

| Failure mode | Consequence | Cheapest protection |
| --- | --- | --- |
| Wrong label (all requests reported as one operation) | Misleading per-operation evidence | Traffic convention test: real schedule with mock transport; assert per-operation counts |
| Injected attempts counted as errors or latency | Retry family always "regresses" | Effects test with seeded pre-send and lost-response injection; assert `injected` class and sample exclusion |
| Expected rejection counted as `client_error` | Domain-case scenarios report false errors | Domain-case traffic test asserts reclassification and the counter invariant |
| Timeout or transport error misclassified | Wrong timeout rate | Parameterized `request` classification test using the fake clock |
| Queue wait included in latency | Inflated latency | Fake-clock test with a saturated semaphore |
| Percentile off-by-one | Wrong p95/p99 | Small table test of nearest-rank values |
| Schema 5 accepts inconsistent totals or extra keys; v1–v4 broken | Untrustworthy evidence or lost compatibility | `test_reports_v5.py` mutation table plus existing v1–v4 fixtures |
| Correctness failure evaluated as passing | AC2 violated | Evaluation table test |
| Stop, saturation, missing samples or no key not inconclusive | False confidence | Same evaluation table |
| Breach or regression not detected, or noise flagged | False result | Same table, including the minimum-delta case |
| Promotion of an ineligible run, or a write on refusal | Silent baseline corruption | Promotion refusal table asserting the directory is unchanged |
| Evaluate, trend or run writes a baseline | AC5 violated | Behavioral directory-unchanged assertions plus an import-boundary test |
| Context or companion accepts free text or a mismatched run | Privacy or attribution leak | Strict-input table |

The test author reuses `traffic_support`, `report_support` and
`convention_support` and minimizes overlapping cases. Expected new test files:

- `test_traffic_metrics.py`
- `test_reports_v5.py`
- `test_evaluation.py`
- `test_baselines.py`

Existing tests that assert schema 4 for convention v2 reports are updated to
expect 5.
