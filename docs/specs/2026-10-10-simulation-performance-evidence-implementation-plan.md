# Convention-simulation performance evidence — implementation plan

This plan implements the
[frozen contract](2026-10-10-simulation-performance-evidence.md) for #229.
Branch: `feat/229-performance-evidence`. The baseline before any change was
`make sim-check` PASS (1378 passed, 2 skipped).

## Global constraints

- Simulator-only. No backend, dependency, scenario-descriptor or
  traffic-behavior change apart from labeling and classification hooks.
- Reports, evaluations and baselines contain no credentials, identifiers
  beyond the approved public identities, URLs, bodies or free text. The single
  exception is the bounded baseline rationale.
- Every refusal prints one fixed line and exits non-zero.
- Follow the existing strict-validation helpers in `reports.py`: `_object`,
  `_require`, `_count`, `_number`, `_hex`, `_measurement`.
- Follow the existing atomic-write patterns.
- Run `uv run ruff check --no-cache` before handing back a new module.
- `make api-semgrep-check` skips untracked files, so run
  `git add -N tools/simulator/tailtag_simulator/<new>.py` before
  `make sim-check`.

## Unit order

Each unit goes through:

1. Independent test author (red).
2. Parent approves the test set.
3. Independent implementer (green).
4. `make sim-check`.
5. Fresh reviewer.

### U1 — Measurement and schema 5

1. `traffic_metrics.py`: an `OperationMetrics` recorder (per-operation class
   counts and `array('d')` samples), `nearest_rank`, and `summary(window)`
   returning the schema-5 `attempts`/`throughput`/`latency_percentiles`
   values.
2. `traffic.py`: `request(send, *, operation, injection)` with timing and
   classification; `expected_rejection(operation)`; `performance()`.
3. `traffic_effects.py`: pass `operation` and the pre-drawn `injection`.
   `traffic_behavior.py`: bootstrap clients pass `"auxiliary"`; replace the
   two expected-rejection records.
4. `provenance.execution_mode`, `RunReport.record_execution_mode`, and
   `RunReport.record_traffic(snapshot, performance)`. `reports_v5.py` and the
   dispatch in `_validate_report`. `convention.py` and `__main__.py` wiring.
5. Update existing tests that assumed schema 4 for convention v2.

### U2 — Thresholds and evaluation

1. `evaluation.py`:
   - the comparable key;
   - strict threshold, context and host-companion parsers;
   - checks, verdict and reasons;
   - the artifact writer;
   - `evaluate(...)`, which returns the artifact for reuse by promotion.
2. The `report evaluate` CLI and the `sim-report-evaluate` Make target.

### U3 — Baselines, promotion, trend and documentation

1. `baselines.py`:
   - the strict baseline record;
   - the slug;
   - `promote(...)` with refusals and initial thresholds;
   - `trend(...)`.
2. The `baseline promote` and `report trend` CLI commands and their Make
   targets.
3. `tools/simulator/baselines/README.md`, the README section, the
   simulation-host recipes, and the telemetry-preservation correction.

### Integration

- One whole-change review.
- `make sim-check`, `./scripts/doctor.sh` and `git diff --check`.
- Offline end-to-end: a real fake-transport convention run produces a schema-5
  report. Evaluate it, promote it into a temporary baselines directory, then
  trend it.

### U4 — Live proof

After merge, with separate authorization, follow the contract's U4 steps.
