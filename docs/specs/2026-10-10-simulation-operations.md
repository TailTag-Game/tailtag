# V0 convention simulation operations — implementation contract

Approved outcome: issue #230, AC1–AC27 in the
[approved refinement](https://github.com/TailTag-Game/tailtag/issues/230). The
maintainer approved every gap recommendation (G1–G12) on 2026-10-10. During
design they also approved three clarifications:

- The weekend profile is one baseline-family run with the full persona mix.
- Evidence collection runs at least every 6 days.
- The 12-hour expiration proof is correctness-only.

## Phase ledger and scope guard

DEVELOPMENT / STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY and
RELIABILITY.

- **SECURITY.** U1 and U2 widen the privileged host admission and bridge
  allow-lists. They must widen them by exact closed shapes, never by relaxing
  checks.
- **DATA INTEGRITY.** U3 copies evidence off the host. Copies must be
  hash-verified and must never mutate the host.
- **RELIABILITY.** The expiration tier keeps a run alive for about 12.5 hours
  without weakening the shorter tiers.

No architect trigger applies: there is no new service, store or distributed
design. A security challenger is held in reserve. It is used only if review
finds the bridge or admission widening ambiguous.

**Outcome.**

- The external host can run `journeys` v1 smoke.
- Committed nightly, weekend and expiration profiles are admitted by the
  existing host contract. The expiration profile is admitted only through a
  narrowly bound tier.
- `sim-host-collect` retrieves settled evidence with hash verification and
  evaluates it.
- An operator guide and an unattended-scheduling design document the attended
  cadence and the deferred automation.

**Non-goals.**

- Unattended execution of any kind:
  - timers;
  - host-resident Railway or Clerk credentials;
  - removing the `--unattended` refusal;
  - Sentry Cron activation.
- Raising the standard host ceilings.
- New scenario semantics or a multi-family run.
- Changes to report schema v5 or to evaluation, promotion or trend semantics.
- Automatic hold resolution, pruning changes or new automatic aborts.
- Changes to the host companion's sample cap.
- New dependencies, new paid services, backend changes, and any change to
  `post-deploy-smoke.yml`.

**Expected change surface.**

- Simulator code (`tools/simulator/tailtag_simulator/`):
  - `host_protocol.py`
  - `host_operator.py`
  - `host_runner.py`
  - `host_bridge.py`
  - `__main__.py`
  - `host_artifacts.py`, for read-only inventory helpers only
- New host files under `tools/simulator/host/`:
  - `smoke-profile.json`
  - `nightly-post-event-profile.json`
  - `nightly-hotspot-profile.json`
  - `nightly-retry-profile.json`
  - `nightly-soak-profile.json`
  - `weekend-profile.json`
  - `expiration-profile.json`
  - `expiration-safety.json`
- Root `Makefile`: `sim-host-collect`.
- Tests under `tools/simulator/tests/`, extending `test_host_protocol.py`,
  `test_host_bridge.py`, `test_host_cli.py`, `test_host_runtime.py` and
  `test_host_ssh.py`.
- Documentation:
  - new `docs/operations/simulation-operations.md`;
  - new `docs/specs/2026-10-10-unattended-simulation-scheduling-design.md`;
  - `tools/simulator/README.md`;
  - `docs/operations/simulation-host.md`, for links and the journeys,
    expiration and collect notes;
  - this spec and its implementation plan.

**Deferred external actions.** Each needs its own authorization:

- AC26 live runs;
- the 50-identity pool expansion;
- the AC25 run;
- the AC20 baseline-promotion PRs;
- the AC23/AC26 proof document;
- opening the AC14 follow-up issue.

**Reversibility.** Every code change is a TWO-WAY DOOR, because each one adds
closed shapes that a later release can remove. Old manifests stay valid.
Persisted held runs keep their original release and validator. The unattended
design is the ONE-WAY DOOR, and it is not crossed here.

## U1 — Host admission and committed profiles (AC12, AC15, AC16, AC25)

### Manifest shapes (`host_protocol.validate_manifest`)

The manifest schema stays at 1. Admission accepts exactly three scenario
shapes. Every other combination is refused before any external work, as it is
today.

1. **Convention, standard tier.** This is unchanged:
   - `scenario_id` is `convention-<family>`;
   - `scenario_version` is 2;
   - the configuration round-trips through `resolve_traffic_config`;
   - the ceilings are the persona sum ≤ 50, safety `seconds` ≤ 900,
     `final_seconds` ≤ 600, `population` ≤ 50, `in_flight` ≤ 10, and
     `limits.active` and `limits.in_flight` ≤ 10.

   A configuration whose `failure.domain_case` is `expired` is never admitted
   under the standard tier.
2. **Convention, expiration tier.** This is admitted only when every one of
   these conditions holds:
   - `scenario_id` is `convention-baseline` and `scenario_version` is 2;
   - the resolved `failure.domain_case` is `expired`;
   - the persona sum is ≤ 2;
   - resolved `limits.active` ≤ 1 and `limits.in_flight` ≤ 2;
   - resolved `limits.generation_seconds` ≤ 45000;
   - safety `seconds` ≤ 46800, `final_seconds` ≤ 600, `population` ≤ 2,
     `in_flight` ≤ 2 and `requests` ≤ 10000.

   Any other field or ceiling is the same as the standard tier. The tier
   follows from the closed configuration shape alone: no flag, filename or
   profile name selects it.
3. **Journeys smoke.** This is admitted only when every one of these
   conditions holds:
   - `scenario_id` is `journeys` and `scenario_version` is 1;
   - `seed` is exactly 0, because journeys consume no randomness;
   - `configuration` is exactly `{"pool": <valid pool name>}`, with no other
     key;
   - safety `population` ≥ 7, plus the standard safety ceilings.

   The identity count is the fixed seven
   (`journeys.py`: 2 owners, 4 catchers and 1 outsider).

The operator `prepare` wrapper still requires exactly the four keys
`scenario_id`, `scenario_version`, `seed` and `configuration`. It dispatches
journeys configuration validation and does not call `resolve_traffic_config`.
`validate_manifest` remains the single source of truth: `prepare`, the host
runner and the bridge all call it.

### Committed profiles

Every profile uses pool placeholder `host228`, as today. Operators keep
private copies when they change the pool.

| File | Shape | Purpose |
| --- | --- | --- |
| `smoke-profile.json` | `journeys` v1, seed 0 | AC12/AC13 smoke |
| `normal-profile.json` | unchanged | Nightly; committed baseline key |
| `nightly-post-event-profile.json` | `convention-post-event` v2 | Nightly rotation |
| `nightly-hotspot-profile.json` | `convention-hotspot` v2, at least one popular owner | Nightly rotation |
| `nightly-retry-profile.json` | `convention-retry` v2, at least one retry-prone attendee | Nightly rotation |
| `nightly-soak-profile.json` | `convention-soak` v2 | Nightly rotation |
| `weekend-profile.json` | `convention-baseline` v2 with every persona, persona sum 50, ten active actors for about 480 s | Weekend |
| `expiration-profile.json` | `convention-baseline` v2, expiration tier | AC25 one-time proof |
| `expiration-safety.json` | Expiration-tier safety | Used only with `expiration-profile.json` |

**Rules.**

- Each nightly profile has ≤ 20 identities and ≤ 10 in-flight requests, and
  stays inside the standard tier with `host/safety.json`.
- Seeds are fixed and distinct: 23001–23004 for the nightly profiles, 23010
  for the weekend profile and 23020 for the expiration profile.
- The weekend profile's identity-setup pacing (50 × 4 s, about 196 s) and its
  traffic window must fit inside `generation_seconds` ≤ 900 and safety
  `seconds` 900.
- The expiration profile:
  - uses 1 normal owner, 1 casual attendee and 1 fursuit;
  - has one segment longer than 43,200 s, with `generation_seconds` in the
    range (43200, 45000];
  - uses `bucket_seconds` 60, keeping the bucket count ≤ 1000;
  - sets `failure.domain_case` to `expired`.
- Every documented assumption lives in the operator guide, not in the JSON,
  because the wrappers are closed four-key objects.

## U2 — Journeys host execution and expiration-tier bridge budget (AC12, AC25)

### CLI and container

The `journeys` parser gains the host flags that `convention` has today:
`--host-manifest`, `--host-socket-dir` and `--stage-log`. The existing host
branch in `__main__.py` handles both `convention` and `journeys`, with the same
checks in each case:

- release and provenance attribution;
- manifest identity;
- an exclusive stage log;
- `RunReport.run_id` taken from the manifest.

With a bound host, journeys wraps its pool, fixture and inspection channels in
`host_channel`, exactly as convention does. Without a bound host, local
`make sim-journeys` is byte-for-byte unchanged. `--unattended` stays a
convention-only refusal flag; journeys has no workload that needs it.

`host_runner` builds the container command from the manifest:

- **journeys:**
  `journeys --pool <pool> --scenario-version 1 --seed 0 --host-manifest /manifest.json --host-socket-dir /bridge --stage-log ... --report-dir ...`
- **convention:** the command is unchanged.

The fixture images that journeys loads must be present in the immutable image.
If any are not, implementation stops and replans rather than adding a new
build input.

### Bridge authority (`host_bridge.BridgeSession`)

The session derives one closed partition from the validated manifest.

- **Convention:** today's partition, unchanged.
- **Journeys:**
  - `count` is 7;
  - `provision` arguments are exactly `owners`, the first 2 leased indexes,
    `catchers`, the next 4, `extras`, the last 1, and `fursuits_per_owner`
    of 2;
  - the provision acknowledgement is exactly
    `{"convention": 1, "enrollment": 6, "fursuit": 4, "activation": 4}`.
    Extras receive no fixture state (`services/api/simulation_fixtures/services.py:167`).
  - Reconciliation uses operation `inspect` on the inspection channel. Its
    arguments are exactly `pool`, `run_id` and `identities`, where
    `identities` maps the seven closed role names (`owner0`, `owner1`,
    `catcher0` to `catcher3`, `outsider`) in lease order.
  - A new closed validator checks the `inspect` response. It mirrors the
    relay contract (`services/api/simulation_fixtures/inspection_remote.py`)
    and the simulator parser (`reconciliation.py`). Any deviation is
    `FAIL_LAUNCHER`, and failure details never cross the boundary.
  - `inspect-population-v1` is refused for journeys, and `inspect` is refused
    for convention.

Every existing rule holds for both scenarios:

- an authority mismatch vetoes the session;
- terminal ordering is preserved;
- deadlines come from manifest safety;
- uncertain outcomes are retained;
- receipts are derived only from acknowledgements.

**Expiration-tier budget.** The 256-operation cap stays for every
non-heartbeat operation. Heartbeats get their own budget of
`ceil((seconds + final_seconds) / 60) + 16`, from manifest safety, and they
still require leased indexes and a non-terminal session. For standard and
journeys manifests this is ≤ 41 heartbeats on top of the 256 non-heartbeat
operations. The extra heartbeats only extend lease TTL; they never extend
deadlines or grant other authority. Lease renewal stays at 60 s and the TTL at
1800 s.

## U3 — Evidence collection (AC21, AC22)

### Host inventory (`host_runner inventory --root ABSOLUTE_PATH`)

This is a new read-only subcommand. It takes no host lock and never waits on
an active run, so a run in progress is simply `incomplete`. If a file vanishes
or changes type mid-read, that run is reported as `incomplete`; the command
does not fail. It reads `runs/*/` and prints exactly one JSON line of at most
65,536 bytes:

`{"schema_version": 1, "runs": [{"run_id", "state", "files"}...], "omitted": <int>}`

Each run's `state` is one of:

- `settled`: `host.json` and `control/recovery.json` are present, and there is
  no `recovery-hold.json`;
- `held`: a hold is present;
- `incomplete`: neither of the above.

For a `settled` run, `files` maps `report`, `stages` and `host` to
`{"sha256", "bytes"}`. `stages` is `null` once it has been pruned. For every
other state, `files` is `null`.

**Bounds and refusals.**

- **Pruned runs are omitted.** A run whose `control/recovery.json` exists but
  whose `host.json` has been pruned, and that has no hold, has nothing left to
  collect. It is not listed and not counted. The host keeps these directories
  as UUID markers indefinitely (`_prune`).
- **Listing order and bound.** Every held and incomplete run is listed first.
  Settled runs follow, newest first by `host.json` `completed_at`, until the
  listing reaches 64 entries. `omitted` counts the older settled runs left
  out. If held and incomplete runs alone exceed 64, the command fails with
  exit 1. A settled run whose `completed_at` cannot be read is `incomplete`.
  With collection at least every 6 days, the newest 64 settled runs always
  include every run not yet collected.
- Only canonical UUID directory names are considered.
- A file is refused if it is a symlink, a non-regular file, or not owned by
  the host owner.
- The command never writes, prunes, resolves or locks out admission.

### Operator collect (`host_operator collect`)

**Command.**
`collect --host ALIAS --host-root ABSOLUTE_PATH --release release.json --archive DIR [--baselines-dir DIR]`

**Make wrapper.**
`make sim-host-collect HOST=… HOST_ROOT=… RELEASE=… ARCHIVE=… [BASELINES=…]`

**Steps.**

1. Run the remote inventory through the same fixed
   `cd -- RELEASE && exec PYTHON …` SSH grammar and `SSH_OPTIONS`, using a new
   bounded helper. It waits at most 30 s, captures at most 65,536 bytes of
   stdout and discards stderr. Treat the inventory as untrusted input and
   validate it strictly: canonical UUIDs, 64-hex digests, `bytes` within
   [1, 33,554,432], and closed keys and states.
2. Print `COLLECT <run_id> held` or `COLLECT <run_id> incomplete` for those
   runs, and do not touch them.
3. For each `settled` run:
   - If `ARCHIVE/<run_id>/collected.json` already exists, print `skipped`.
   - Otherwise, create an owner-only (0700) `ARCHIVE/.<run_id>.partial/`
     directory and copy each listed file into it with `scp`, using the
     validated fixed remote paths and the same SSH options.
   - Check each file's size and SHA-256 against the inventory.
   - Validate the report with `reports.validate`.
   - Write `collected.json`, a closed record of `run_id`, the inventory hashes
     and the collection UTC time.
   - Atomically rename the directory to `ARCHIVE/<run_id>/`.
4. Evaluate collected convention schema-5 reports with
   `evaluation.evaluate(report, host_companion=host.json, context=None, baselines_dir)`
   and write `<run_id>.evaluation.json` beside them. Journeys and older schema
   versions record `evaluation: not_applicable`. Evaluation failure is recorded,
   and it does not undo collection.
5. Print one fixed line per run: `COLLECT <run_id> collected|skipped|held|incomplete|failed`, with the `evaluation=` suffix on `collected` lines.
   The command exits 0 only if no run failed.

**Failure handling.** A hash or size mismatch, a validation failure or a
transfer failure deletes the run's partial directory and prints
`COLLECT <id> failed`. The archive is never left half-written under the final
name.

**Resolved details (fixed after the unit B tests were written).**

- **Inventory refusals.** A symlinked, non-regular or foreign-owned file makes
  only that run `incomplete`; the inventory still succeeds. The one exception
  is a symlinked or non-regular stages file on an otherwise settled run: the
  run stays `settled` with `stages: null`.
- **Malformed inventory.** Collect refuses the whole command with exit 1,
  before any transfer, and prints no run identifiers from the untrusted input.
- **Archive layout.** `ARCHIVE/<run_id>/` holds `<run_id>.json`, `stages.log`
  (when listed), `host.json`, `collected.json`, and
  `<run_id>.evaluation.json` when evaluated. This matches the host runbook.
- **`collected.json`.** A closed record of `schema_version` (1), `run_id`,
  `files` (the inventory hashes and sizes) and `collected_at` (UTC).
- **Evaluation outcome.** It goes on the collected line rather than in
  `collected.json`, as
  `COLLECT <run_id> collected evaluation=written|not_applicable|failed`.
- **Baselines directory.** `--baselines-dir` defaults to
  `tools/simulator/baselines`, the same default as `report evaluate`.
- **scp options.** `scp` gets an explicit option list: the `-o` options from
  `SSH_OPTIONS` plus `-q`. It never gets `-a`, `-T` or recursive copy.
- **Omitted runs.** Collect validates `omitted` as a non-negative integer. When
  it is positive, collect prints `COLLECT omitted=<n>` once and still exits 0.
- **Existing final directory.** An existing `ARCHIVE/<run_id>/` without a
  regular `collected.json` is `failed`. Collect transfers nothing for that run
  and never replaces the directory, even when it is empty.
- **Host root for collect.** It must match `^/[A-Za-z0-9_./-]+$`, because
  `scp` remote paths are not shell-quoted. `run` validation is unchanged.
- **Platform.** `inventory` does not apply the Linux host admission policy.
  It is read-only and runs on any platform.

**What collect never does.** It never writes to the host, the baselines
directory or an existing `ARCHIVE/<run_id>/`. It never follows symlinks in
`ARCHIVE`, and it never runs workload.

## U4 — Documentation (AC10, AC13, AC14, AC17–AC19, AC23, AC24)

### `docs/operations/simulation-operations.md`

The operator guide covers these subjects, linking to `simulation-host.md` for
host mechanics:

- **Cadence:**
  - smoke after every controlled promotion;
  - smoke as the gate before each nightly run;
  - nightly: the normal profile plus one rotating family per night, covering
    every family weekly;
  - the weekend profile.
- **Fixed UTC run window and Staging coordination (AC18):**
  - a deployment change during a run is classified as a target change;
  - M1–M7 alerts are never suppressed, and any firing is recorded with the
    run's evidence.
- **Profile assumptions** for each committed profile.
- **Reproduction** by scenario, version, seed and release.
- **Failure interpretation:**
  - correctness, which is a hard gate;
  - performance verdicts;
  - abort semantics for each profile under AC19's existing guardrails.
- **Observability correlation**, using the #229 recipes.
- **Holds:** exact-run recovery after any failure, fail-closed, with no
  automatic resolution (AC17).
- **Collection** at least every 6 days, then evaluation.
- **Baseline promotion** of each new profile's first reviewed passing run
  (AC20).
- **Release updates** through `install-runtime`, and rollback.
- **The expiration proof:**
  - attended for about 12.5 hours;
  - correctness-only;
  - the host companion keeps only its first 301 samples.
- **Disabling the schedule**, which points to the design document.

The guide contains no private endpoints, inventory or credentials.

### `docs/specs/2026-10-10-unattended-simulation-scheduling-design.md` (AC14)

The design is decision input. It states:

- **Trust facts:**
  - the relays require the personal Railway login through `railway ssh`
    (`scripts/api_staging_reset_ssh.py:188`);
  - Railway project tokens do not support `railway ssh`;
  - the Clerk instance secret key cannot be scoped.
- **Options and threat model**, including the Production blast radius:
  - host-resident workspace credentials;
  - a maintainer-armed bridge, kept on the maintainer machine with Keychain;
  - a backend-side privileged path.
- **Mechanics:**
  - systemd timer and oneshot overlap semantics;
  - schedule disable and recovery;
  - hold interaction;
  - Sentry Cron check-ins on DSN, with `in_progress`, `ok` and `error` sent
    to the existing owner email alert. The free plan includes one monitor.
- **A recommended follow-up issue scope.**

Nothing in this design is implemented.

### Other updates

- **README:** the "Later issues" section, journeys on the host, collection,
  and a link to the guide.
- **`simulation-host.md`:**
  - journeys and expiration manifests;
  - inventory and collect;
  - a correction: stage logs last 7 days, so collection must run at least
    every 6 days.

## Frozen test surface and failure/value map

Tests extend the existing host suites. They use real `validate_manifest`, real
`BridgeSession` with a fake relay dispatch, real temporary host directories
and fake `ssh`/`scp` executables at the process boundary, as existing
`test_host_ssh.py` does. Each test below protects a distinct failure mode.

| Failure mode | Consequence | Test |
| --- | --- | --- |
| Admission widened beyond the closed shapes: journeys with extra configuration, a non-zero seed, version ≠ 1; expiration tier with population 3, `domain_case` ≠ expired, seconds > 46800, a non-baseline family; standard tier with `expired` | Unsafe or unbounded host workload | `test_host_protocol`, parameterized refusal table |
| Committed profiles rejected, or admitted under the wrong tier | Operators cannot run the cadence, or a ceiling is bypassed | `test_host_protocol`: every committed profile and safety pairing prepares offline; expiration profile with `safety.json` and normal profile with `expiration-safety.json` are refused |
| Bridge accepts a journeys provision, inspect or acknowledgement outside the fixed partition, or accepts cross-scenario operations | A compromised container gains privileged authority | `test_host_bridge`, parameterized |
| Journeys host run takes unwrapped launchers or the wrong container command | Bypasses the bridge, or the run fails | `test_host_cli` / `test_host_runtime` |
| Heartbeat budget: a long run starves, or standard runs gain extra operations | Lease loss at 12 h, or a looser bound | `test_host_bridge` |
| Inventory misclassifies held or incomplete runs, follows symlinks, or writes | Held evidence collected, or host mutation | `test_host_artifacts` / `test_host_runtime` |
| Collect accepts mismatched bytes or hash, half-writes the archive, re-collects, writes baselines, or trusts unvalidated inventory paths | Corrupted durable evidence or path traversal | `test_host_ssh`, focused cases |
| `--unattended` refusal regresses | Unattended convention execution | Existing test, unchanged |

Local `make sim-journeys` stays unchanged and is covered by the existing
journeys tests. Required verification: `make sim-check`,
`./scripts/doctor.sh` and `git diff --check`.
