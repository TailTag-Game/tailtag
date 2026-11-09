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

## Render and Railway-era baselines

The normal profile baseline (`dac260032cf2`) comes from Render Staging run
`2e17d592` in Virginia, backend `2706490` (#411 AC14). Its thresholds are the
proposed defaults from that run.

No Render run passed the Railway thresholds, and Railway is retired (#412).
So #411 retired the Railway `dac260032cf2` files and promoted the Render run as
a first baseline. Git history keeps the Railway files:

- baseline SHA-256 `bdbbaaa065da5967513e74389fcf50466515848cca2b7aa2de2fdb28dad6a03e`
- thresholds SHA-256 `e229cfb3bc95db44c3b8d7dac06d04d5eb0dd2ec8a1273291f0af76d54855b33`

The weekend (`7b2ae8e2ce34`) and soak (`154b7029c7da`) baselines still come
from Railway Staging runs. They stay as history and as the evidence for #229.
No new run can match them as a fresh Railway run. Render weekend and soak
baselines are deferred (#411).
