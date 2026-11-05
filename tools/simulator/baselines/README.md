# Performance baselines and thresholds

This directory holds the reviewed known-good performance baselines and threshold
assumptions for convention simulation (#229). Each file is keyed by a comparable
key: the scenario ID and version, descriptor digest, traffic plan digest,
environment and execution context.

- `<slug>.baseline.json`: the single active baseline for a key. It records the
  promoted report's SHA-256, run ID, simulator and backend identity, aggregate
  per-operation metrics, a short rationale, and the hash of the baseline it
  supersedes. The full report and its evaluation stay in the maintainer archive.
- `<slug>.thresholds.json`: documented threshold assumptions for the same key.
  Every value carries its assumption text.

Thresholds and baselines are regression evidence, not production SLOs or capacity
claims.

## Changing a baseline

1. Run `RATIONALE='<text>' task sim-baseline-promote REPORT=<path>` on a reviewed,
   archived report (the rationale is taken from the environment so go-task does
   not alter it). The command
   refuses any run that did not pass, failed correctness, breached or regressed,
   saturated the generator, or cannot be compared. A refused run writes nothing.
2. Open a pull request with only the changed files from this directory. In the
   description, include:
   - the run ID;
   - the report SHA-256;
   - the evaluation summary;
   - for a first baseline, the proposed thresholds.
3. Reviewers check the rationale, the backend and simulator identity, and the
   assumption text on every threshold, and confirm that the archived report
   matches the recorded hash. A thresholds file needs latency limits for the
   workload operations that matter (`resolve`, `confirm`, `read`). Without
   them, `acceptable` rests only on the saturation checks.
4. Promotion takes effect only when the pull request merges. Git history shows
   who promoted what.

No run, evaluation or trend command writes here. A passing run never replaces a
baseline. To retire a baseline, delete its file in a reviewed pull request.

## Railway-era baselines

The three baselines here (`7b2ae8e2ce34`, `dac260032cf2`, and `154b7029c7da`)
came from Railway Staging runs, before the Render move. They stay as history
and as the evidence for #229 and #411. Railway is retired (#412), so no new run
can match them as a fresh Railway run. A Render baseline for the normal profile
comes from #411 AC14. Render weekend and soak baselines are deferred (#411 G10).
