# Convention simulation operations

This guide covers routine use of the convention simulator against Staging:

- smoke after promotions;
- nightly and weekend profiles;
- evidence collection and evaluation;
- baselines;
- failure handling.

It implements [#230](https://github.com/TailTag-Game/tailtag/issues/230) and
its [implementation contract](../specs/2026-10-10-simulation-operations.md).
For host mechanics, see the [external host runbook](simulation-host.md):

- release installation;
- manifests;
- the foreground bridge;
- supervision;
- holds and exact-run recovery.

For simulator commands, see the
[simulator README](../../tools/simulator/README.md).

## Operating model: attended

Every run is attended. The maintainer starts it from their own machine, enters
the Clerk secret at the hidden prompt, and keeps the foreground bridge open
until the run ends:

- privileged Staging setup and reconciliation go through `railway ssh`, which
  uses the maintainer's personal Railway login;
- no Railway or Clerk credential is stored on the host;
- `--unattended` stays refused;
- no timer or scheduler starts runs.

The [unattended scheduling design](../specs/2026-10-10-unattended-simulation-scheduling-design.md)
explains why, compares the options, and proposes a follow-up. Until the
maintainer approves one, "the schedule" below is a target cadence the
maintainer follows. A missed night is recorded as skipped and never backfilled.

Live runs against Staging still need the maintainer's authorization for each
milestone, as they do today.

## Cadence

All times are UTC.

| When | What | Profile and safety |
| --- | --- | --- |
| After every controlled Staging promotion | Smoke | `smoke-profile.json` with `safety.json` |
| Every night, in the window | Smoke gate, then normal | `normal-profile.json` with `safety.json` |
| Monday–Thursday nights, after normal | That night's family | See [Nightly](#nightly) |
| Saturday night, after normal | Weekend | `weekend-profile.json` with `safety.json` |
| Wednesday and Sunday | Collect and evaluate | [Collection](#collection-and-evaluation) |

**Run window.** Nightly and weekend runs start between 08:00 and 10:00 UTC,
which is overnight across the continental US. Avoid these activities in that
window:

- controlled Staging promotions;
- #204 reset and reseed;
- the backup restore drill;
- manual Staging testing.

If any of them has to happen, do not start a simulation until it has finished.

### Smoke

Smoke runs the deterministic `journeys` v1 scenario through the host (seven
identities, seed 0). It covers the canonical public journeys and their
expected rejections, then reconciliation, cleanup and release.

```sh
make sim-host-prepare PROFILE="$TRANSFER/smoke-profile.json" \
  SAFETY_CONFIG="$SIM_REPO_ROOT/tools/simulator/host/safety.json" \
  RELEASE="$TRANSFER/release.json" MANIFEST="$TRANSFER/smoke-manifest.json"
make sim-host-run MANIFEST="$TRANSFER/smoke-manifest.json" HOST=tailtag-sim \
  HOST_ROOT=/srv/tailtag-simulator
```

Copy each committed profile into the owner-private transfer directory, set
its pool there, and keep it outside Git, as described in the
[host runbook](simulation-host.md#profile-preparation-and-foreground-execution).

Smoke is a gate. If it does not pass, run nothing else that cycle and follow
[After a failure](#after-a-failure). Smoke is correctness-only: it has no
performance evaluation and no baseline.

### Nightly

Every night, after smoke passes, run `normal-profile.json`. Its comparable key
already has the committed baseline, so every nightly run gives regression
evidence. Then run that night's family:

| Night | Family profile |
| --- | --- |
| Monday | `nightly-post-event-profile.json` |
| Tuesday | `nightly-hotspot-profile.json` |
| Wednesday | `nightly-retry-profile.json` |
| Thursday | `nightly-soak-profile.json` |

Each run uses a fresh `sim-host-prepare` and a new manifest. Never reuse a
manifest. A run must finish and have its hold resolved before the next run is
admitted; the host refuses overlapping runs.

### Weekend

`weekend-profile.json` is one baseline-family run that uses all 50 identities
and the full persona mix. It stays inside the standard host ceilings: 50
identities, ten actors and in-flight requests, 900 s setup and execution, and
600 s finalization. It needs pool `host228` expanded to 50 identities
(`make sim-pool-provision POOL=host228 SIZE=50`, separately authorized).

## Profile assumptions

All committed profiles live in `tools/simulator/host/`. They are closed
four-key wrappers, so their assumptions are recorded here. They describe
plausible early field-beta usage at small scale. None of them is a capacity
target.

| Profile | Seed | Identities | Assumption |
| --- | ---: | ---: | --- |
| `smoke-profile.json` | 0 | 7 | Canonical journeys only. Deterministic, with no randomness. |
| `normal-profile.json` | 22801 | 20 | Unchanged #228 normal run: ten active actors for 300 s. Its key carries the committed baseline. |
| `nightly-post-event-profile.json` | 23001 | 20 | Grouped collection after an event, as family-default bursts. |
| `nightly-hotspot-profile.json` | 23002 | 20 | Two popular owners attract concentrated catches and overlapping duplicates. |
| `nightly-retry-profile.json` | 23003 | 20 | Four retry-prone attendees revisit their catches. Every read, resolve and confirm attempt, from any actor, has a 10% injected pre-send failure and a 10% lost response. Five attempts per call keep a chance run failure near 1.6%; with three, about a third of runs would fail by chance. |
| `nightly-soak-profile.json` | 23004 | 20 | Three finite cycles that revisit the same catch pairs. |
| `weekend-profile.json` | 23010 | 50 | Every persona. Ten active actors for 300 s with 2 s think time. |
| `expiration-profile.json` | 23020 | 2 | One owner and one casual attendee. Exercises the natural 12-hour catch-session expiry. A one-time proof only. |

**Setup time.** Identity setup is paced at 4 s per identity. That is about
76 s for 20 identities and 196 s for 50, and it counts against safety
`seconds`. If a run reaches the 900 s deadline, it stops as a safety stop and
cannot pass.

**Attempt budget.** A traffic schedule that exhausts `limits.attempts` before
its window ends stops early and fails. The first live weekend run sent about
24 attempts per second and spent its 9,000 attempts 369 s into a 480 s window,
so the window is now 300 s, about 7,300 attempts. If a profile hits either
limit, shorten its traffic window in a reviewed change; never raise the
ceilings.

**Reproduction.** A run is reproduced by:

- the same scenario ID and version;
- the same seed and resolved configuration (the manifest's plan digest);
- the same simulator release (immutable image ID and simulator SHA).

Backend builds are expected to differ. See
[Scenario versions and reproduction](../../tools/simulator/README.md#scenario-versions-and-reproduction).

## Interpreting results

**Correctness is a hard gate.** A run whose `outcome` or correctness is not
`passed` is a failure, whatever its latency. Reconciliation discrepancies,
retained fixtures and journey failures are recorded in the report and the
stage log.

**Performance is evaluated offline.** It never changes the run outcome. The
verdicts, from [#229](../../tools/simulator/README.md#performance-evidence):

| Verdict | Meaning |
| --- | --- |
| `not_evaluated` | Correctness failed, the run did not pass, or the host companion records a stop |
| `inconclusive` | Too few samples, generator saturation, no comparable baseline, or a run that is not comparable |
| `breached` | An absolute threshold was exceeded |
| `regressed` | A baseline tolerance was exceeded |
| `acceptable` | The only passing performance result |

Thresholds are documented assumptions, not production SLOs.

**Aborts.** The existing automatic guardrails are the abort policy for every
profile:

- catastrophic error windows (genuine 5xx and transport errors only; expected
  domain rejections and injected faults never count);
- readiness collapse;
- a changed backend identity;
- request, time and concurrency budgets;
- supervision loss.

Generator saturation is not an abort. It makes the evaluation `inconclusive`.
Backend resource pressure is recorded through the optional operator context
file. An operator can still stop a run by hand, as the
[host runbook](simulation-host.md#observation-and-controlled-stop) describes.

**Deployment changes.** If Staging is redeployed during a run, the identity
check aborts it with `identity_mismatch`. Record that as a target change, not
a performance regression. Follow the exact-run recovery, then rerun in a later
window.

**Staging alerts.** Monitors M1–M7 in the
[field-beta dashboard](field-beta-operations.md) watch Staging and may fire
under weekend load, for example M3 latency or M7 authentication failures.
Never suppress or edit a monitor to accommodate a run. When one fires during a
run, record it with that run's evidence, then decide whether it shows a real
problem as the
[first-response guide](staging-first-response.md) describes.

**Correlating backend evidence.** Use the report's UTC window, the backend
`source_sha` and the Sentry release to find the #210, #212, #213 and #214
signals. The [backend context recipes](simulation-host.md#backend-context-for-performance-evaluation)
list the exact queries and the closed values for the context file.

## After a failure

Failures fail closed:

- a failed, interrupted or otherwise non-passing run keeps its host recovery
  hold;
- the hold refuses every later run until it is resolved;
- nothing resolves holds automatically.

1. Stop the cadence. Do not start the next profile.
2. Preserve the evidence: collect it (see below) or copy it with the runbook's
   hash-verified procedure.
3. Follow the [exact-run recovery](simulation-host.md#recovery-and-refusal-handling):
   - verify the target identity;
   - inspect `make sim-retained` and `make sim-pool-status`;
   - run `make sim-cleanup` for the exact run;
   - resolve the hold with a trusted receipt.
4. Record the cause before resuming. A failed smoke means the promoted build
   needs investigation before any nightly run.

For a `supervision_lost` stop, two non-authoritative diagnostics say where the
health path stalled: the Mac `<state>/<UUID>.bridge.json` fields `health` and
`revocation`, and the host's `runs/<UUID>/control/health.json`, read over ssh.
They never decide an outcome and are not collected.

Because every run is attended, the operator sees each result directly, and
there is no push notification today. If unattended scheduling is approved, the
notification mechanism will be Sentry Cron check-ins, which need only the DSN:

- `in_progress` at start, and `ok` or `error` at the end;
- a missed or failed check-in creates an issue routed to the existing
  `Staging field beta: email observability owner` alert.

The [design](../specs/2026-10-10-unattended-simulation-scheduling-design.md#mechanics-common-to-any-option)
specifies this. It is activated only by that follow-up.

## Collection and evaluation

Host retention:

- reports and `host.json` are kept for 30 days;
- stage logs are kept for only 7 days.

Collect at least every 6 days. The cadence above collects on Wednesday and
Sunday.

```sh
make sim-host-collect HOST=tailtag-sim HOST_ROOT=/srv/tailtag-simulator \
  RELEASE="$TRANSFER/release.json" ARCHIVE="$ARCHIVE"
```

For each run, collect prints one of:

- `COLLECT <run-id> collected evaluation=written|not_applicable|failed`
- `COLLECT <run-id> skipped|held|incomplete|failed`

The inventory lists every held and incomplete run first, then the newest
settled runs until the listing reaches 64 entries. Collect prints
`COLLECT omitted=<n>` for the older settled runs it left out. Collecting at
least every 6 days keeps every uncollected run inside that window. Runs whose
evidence the host has already pruned are not listed at all.

**Settled runs.** The report, stage log and host companion are copied into
`ARCHIVE/<run-id>/` over the verified SSH alias. Each file's size and SHA-256
are checked against the host's own inventory, and the report is validated.
`collected.json` records the hashes. Convention schema-5 reports are evaluated
into `<run-id>.evaluation.json`; journeys smoke is `not_applicable`.

**Held, incomplete or already-collected runs.** These are listed and left
untouched.

**What collect never does.** It never writes to the host or the baselines,
never prunes, and never resolves a hold.

A run that fails verification leaves nothing behind and makes the command exit
nonzero. Investigate before collecting again. Keep `ARCHIVE` owner-private and
outside Git.

Trend over the archive with `make sim-report-trend DIR="$ARCHIVE"`.

## Baselines

New profiles start without baselines, so they evaluate as `inconclusive`. To
promote the first reviewed passing run of each nightly family and the weekend
profile:

1. Review the collected report, its evaluation and any backend context.
2. Run `make sim-baseline-promote REPORT=… HOST_COMPANION=… RATIONALE="…"
   INITIAL_THRESHOLDS=1` on the maintainer machine. See
   [Promote a baseline](../../tools/simulator/README.md#promote-a-baseline).
3. Open a pull request with the baseline and thresholds files. Promotion takes
   effect only when it merges.

A passing run never replaces a baseline by itself. Smoke and the expiration
proof are correctness-only and never get baselines.

## Releases

Scheduled runs use the release currently selected on the host:

- after a simulator change merges, build and install it with the runbook's
  verified `install-runtime` flow;
- keep the previous release for rollback;
- a new simulator SHA is allowed against an existing baseline, but evaluations
  report it as a caveat.

## Natural-expiration proof (one-time)

**Status:** not run. Three attempts stopped before expiry, and on 2026-10-14
the maintainer replaced this run with deployed-source verification plus
backend tests ([#316](https://github.com/TailTag-Game/tailtag/issues/316)). See
the [Staging proof](../specs/2026-10-13-simulation-operations-staging-proof.md#natural-expiration-proof-ac25).
The profile stays available but needs fresh live authorization.

`expiration-profile.json` with `expiration-safety.json` proves that an
unrefreshed catch session expires at the server's real 12-hour lifetime, with
no clock or database manipulation. Host admission accepts its raised ceilings
only for this closed configuration shape:

- `convention-baseline` v2;
- `domain_case: expired`;
- at most 2 identities and 2 in-flight requests;
- up to 46,800 s of execution.

Every other profile is refused with this safety file.

Staging safety checks count toward the 10,000-request ceiling. Each check
sends three requests, and the run checks once per `poll_seconds` (30 s here)
plus once per 60 s lease heartbeat: about 7,000 requests over 46,800 s. At a
10 s poll the checks alone would exceed the ceiling after about 8 hours.

**This proof is not part of the cadence.** It needs separate authorization.
Plan for these constraints:

- **Attended for about 12.5 hours.** The maintainer's bridge and SSH session
  must stay connected the whole time, and a disconnect makes the run fail.
  Run it from a machine that will not sleep.
- **Truncated companion.** The host companion keeps only its first 301
  samples, about 25 minutes, so generator resource evidence covers only the
  start.
- **Correctness-only.** The proof is not performance-evaluated and has no
  baseline.
- **Hold.** Its run window spans the nightly window, so pause the cadence
  until it finishes and its hold is resolved.

## Readiness evidence

The required foundations have all been closed:

- operational and identity: #200, #201, #203, #204;
- diagnostics: #210, #212, #213, #214.

The #230 Staging proof, written with the first authorized live runs, records
their verified state with a date. Evidence from runs after that date counts as
backend-readiness evidence. Runs before it remain historical and
non-authoritative.

## Maintenance

- Patch the host and update pins only between runs, with no holds outstanding,
  as described in the
  [host runbook](simulation-host.md#artifacts-retrieval-and-maintenance).
- Revisit profile assumptions and thresholds after field-beta evidence exists.
  Change them only through reviewed pull requests.
- Stopping or pausing the cadence needs no tooling: stop starting runs. Before
  any unattended scheduling is enabled, its follow-up must define disable and
  recovery controls, as the design does.
