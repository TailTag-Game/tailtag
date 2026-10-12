# Deterministic simulation scenarios and run reports

Issue: #224; approved refinement:
https://github.com/TailTag-Game/tailtag/issues/224#issuecomment-5997094427

## Phase ledger

- Scope: ADW STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY, RELIABILITY,
  TEST ADEQUACY. Parent: GPT-6 Sol family, high engineering judgment.
- Reversibility: TWO-WAY DOOR; additive simulator artifacts, no backend migration.
- Completed: approved AC1–AC14, independent reconnaissance/test design/authorship,
  all three implementations and fresh unit reviews, authoritative `make sim-check`
  (607 tests; Ruff/strict Pyright/catalog/Semgrep pass, zero findings), doctor,
  actual Docker build/runtime/persistence proof, offline CLI negative proof.
- Current: PR #295 includes the CodeRabbit corrections; final simulator validation
  passed 617 tests. Independent correction-unit and whole-change reviews passed.
  The maintainer live Staging acceptance and reproduction proof below passed.
- PR #295 merged as `a025878`; issue #224 is Closed/Done. A post-merge recorder
  validation failure can bypass resource finalization; the focused follow-up below
  addresses refined AC8 and original AC5's remaining reliability gap.
- Environment: full access restored after the temporary identity/network stop.
  Root verified `FinnThePanther` before resuming and before doctor. Docker is reachable.
  Image assurance uses a disposable clean Git snapshot with verified Finn identity;
  publication is authorized through a pull request. Deployment is outside this handoff.
  Task-created containers and proof image have been removed; base images retained.

## Acceptance contract and scope guard

The fourteen approved criteria in `.refinement/224.md` are the contract. The
published approved comment is the durable copy. This design chooses implementation
interfaces without changing those criteria. Report all four existing execution
commands and preserve their workloads, integer return values and fixed stdout.
Library calls used by existing tests may omit the optional recorder; all real CLI
execution commands create a recorder before external work. Administration and
standalone cleanup/listing do not create simulation reports.

Files: new focused modules under `tools/simulator/tailtag_simulator/` for scenarios,
reports, provenance; immutable scenario JSON descriptors; optional hooks in
`smoke.py`, `pool.py`, `fixtures.py`, `journeys.py`, `targets.py`, `__main__.py`;
existing simulator tests plus focused report/provenance tests; Dockerfile,
Makefile, `.gitignore`, simulator README, CI only where needed and this spec.

Non-goals: backend changes/migrations, new workloads/randomness, traffic/guardrail/
performance implementations, network validation of an old report, automatic
reproduction launch, deployment, automatic report deletion or GitHub publication.

Ruling: final identity drift and report-persistence failure before fixture cleanup
use the existing `interrupted` retention reason, with the precise `attribution` or
`report` failure recorded in the report. This truthfully records an interrupted
run without changing the backend's closed retention-reason enum. Cost if wrong:
operators consult the report for more precise diagnosis.

Ruling: the approved G5 recommendation asks for a final identity observation after
workload/reconciliation without restricting it to fixture-backed commands. Apply
it to all four reported execution paths; only fixture-backed paths have cleanup
to gate. Additional unauthenticated identity requests are attribution checks,
not changes to the simulated workload. Cost if wrong: a failed end probe makes an
otherwise correct smoke result ineligible as attributable evidence.

## Design

### Scenario contract

`scenarios.py` owns immutable versioned descriptors for `smoke`, `pool-smoke`,
`fixture-smoke`, and `journeys`, version 1. Each descriptor declares its API
contract, logical roles, ordered operation/journey names, fixed assumptions and
intentional waits, supported configuration keys/defaults and no random choices.
Embed the complete descriptor and SHA-256 digest of deterministic UTF-8 JSON in
every report. Changing configuration values within the same declared meaning does
not bump the version. Changes to semantic interpretation do.

Catalog validation checks structure, declared digests and historical immutability
against available Git history: a committed descriptor for an existing ID/version
cannot change or disappear. The check participates in `make sim-check`. Containers
validate the packaged catalog/digests without Git. Semantic executable changes
still require review; source identity preserves historical executable behavior.
History enforcement fails clearly in a shallow checkout rather than silently
claiming old descriptors were checked. Simulator CI fetches full Git history.

Public functions:

```python
resolve_scenario(command: str, version: int, config: Mapping[str, object]) -> dict[str, object]
validate_catalog(root: Path | None = None) -> None
```

Required pool/count descriptor defaults are null markers; resolved configuration
must supply these values, preserving existing CLI requirements. Other defaults
remain the current effective CLI defaults.

Resolution rejects unsupported versions/contracts, unknown configuration keys,
invalid types (including booleans used as counts/seeds), invalid count ranges and
unsafe targets before execution. Seed is an integer; fixed scenarios declare it
unused. Known local origins are safe bounded configuration values, not arbitrary
URLs. Negative/unsafe population values are never sent to privileged launchers.

### Report contract and recorder

`reports.py` owns the strict JSON document, validator and real filesystem store.
The public construction surface is:

```python
RunReport(
    output_dir: Path,
    scenario_id: str,
    *,
    scenario_version: int = 1,
    seed: int = 0,
    config: Mapping[str, object],
    run_id: str | None = None,
    wall_clock: Callable[[], datetime] = utc_now,
    monotonic: Callable[[], float] = time.monotonic,
)
validate_report(value: object) -> dict[str, object]
load_report(path: Path) -> dict[str, object]
```

Constructor resolves the scenario and reserves/persists `<UUID>.json` before
network work. `path` and `run_id` are public read-only attributes. Add explicit
recorder methods for source, target observations, stage begin/end, correctness,
sanitized journey/reconciliation summaries and finalization. Use `begin(stage)`,
`end(stage, status, code=None)` and `finish(exit_code) -> int` as the lifecycle
surface; methods must not serialize arbitrary values or exception objects.

Later snapshot errors set `write_failed`; they do not throw past resource release.
`finish` preserves nonzero/interruption status and cannot return zero after a write
failure. Initial reservation/write failure raises a detail-free report failure
before any network work. Save snapshots by writing a temporary sibling and atomic
replacement, preserving the last complete snapshot on replacement failure. Refuse
file collisions/symlinks; remove task-owned temporary snapshot files on failure.

The external document contains:

| Field | Contract |
| --- | --- |
| `schema_version` | Independent integer report version, initially 1. |
| `run_id` | Canonical lowercase UUID shared with leases/fixture ledger. |
| `scenario` | ID/version, complete descriptor/digest, integer seed, randomness usage, resolved configuration. |
| `source` | Full simulator SHA, provenance status/reason, runtime/dependency identity needed for reproduction. |
| `target` | Safe target name/origin; starting/final validated source SHA, deployment ID and environment; attribution status/reason. |
| `timing` | UTC start/end and finite nonnegative monotonic elapsed durations. |
| `population` | Logical roles/effective counts/fixture assumptions. |
| `profile` | Ordered execution assumptions and intentional waits; explicit unavailable load/ramp fields. |
| `limits` | Existing applicable values with units/enforcement scope; explicit unavailable new ceilings. |
| `phases` | Fixed stage names with status, timestamps/duration and fixed failure code where applicable. |
| `correctness` | Passed/failed/not_observed; separate from cleanup/release/attribution/report outcome. |
| `results` | Approved journey/check/role labels and bounded counts; no internal identities/payloads. |
| `performance` | Available durations; explicit unavailable throughput/percentiles/resource-context fields. |
| `outcome` | Running/passed/failed/interrupted, consistent with phases/correctness/attribution. |
| `failure` | Fixed stage/code or explicit absence. |

Before provenance is observed, source SHA is null with `not_observed` reason.
Missing/dirty/invalid source can finalize a failed report with a fixed provenance
status/reason and any validated available SHA; only clean provenance permits
external execution or a passed report. Backend observations follow the same
initial unavailable rule, with valid local nulls distinguished as not applicable.

Freeze exact nested field spellings in the independent tests/representative JSON
fixture before implementation; the table defines their semantics. Unknown fields
at every level are rejected. Optional measurements always distinguish value from
bounded `not_applicable`, `not_implemented`, `not_observed` reasons. Only bounded
synthetic configuration is accepted. Reader is size-bounded, rejects duplicate
keys/nonfinite numbers/deep or malformed input, and emits no raw input details.
Reconciliation summary count records checks performed; items contain only
discrepancies. Successful journeys require all declared journey results and all
14 reconciliation checks; successful fixture runs require observed cleanup.
Partial failure evidence remains valid, with consistent performed-check counts. Journey summaries need names/pass-fail counts; storing arbitrary step/body strings
is unnecessary. Reconciliation details may keep the existing Check/Role enums and
bounded expected/observed counts, not internal rows/IDs.

### Provenance and container build

`provenance.py` validates real Git host source or immutable packaged metadata.
Expose `load_source(root: Path | None = None) -> dict[str, object]` and a
repository-owned build command taking source root/tag. Source is full SHA plus
clean tracked production package/data/dependency files, relevant Makefile wiring
and committed fixture inputs. Reject changed staged/unstaged relevant files,
deleted inputs and untracked runtime/workload inputs (including ignored source
files that would be executed/loaded). Caches and output artifacts are not inputs.
Host launcher input closure also includes the three `api_sim_*_ssh`, shared
`api_staging_reset_ssh` and `api_staging_preflight` scripts, the API dependency
manifest/lock, and `scripts/__init__.py` if present. These host-only inputs do not
enter container smoke metadata. Tests are not execution inputs. Inspect real file bytes, handle symlinks safely,
and sanitize all Git failures; do not expose Git stderr or arbitrary filenames.

The build command first validates provenance, copies approved inputs into a
temporary build context, writes SHA plus a content manifest/lock identity, and
launches Docker without a shell. Runtime verifies that packaged bytes agree with
metadata. Place metadata in an image path not writable by the app user. Runtime
environment variables cannot replace it. Build checks run through the repository
command invoked by `make sim-image`; test its subprocess boundary without Docker.
Container-supported smoke must resolve package/root paths correctly. Host-only
fixture/pool commands keep their existing host boundary.

### CLI and lifecycle

Four run commands gain `--scenario-version`, `--seed`, `--report-dir` (default
`tools/simulator/reports` on the host; writable persisted location in containers).
Add `report validate PATH` as a credential-free offline command, with safe
fixed success/failure output. It invokes the same actual reader/validator as
execution. Existing Make targets pass optional VERSION/SEED/REPORT_DIR values;
add a focused offline validation target. Container docs show a volume mount.

CLI creates the recorder, validates provenance before external work and passes its
UUID/optional recorder into the existing command functions. Extend VerifiedTarget
to retain deployment ID/environment. Stage calls record actual boundaries rather
than parsing stdout. Journey/reconciliation results are attached through explicit
safe result adapters; raw observations/expectations are never passed to the store.

After workload/reconciliation, make a credential-free final identity observation
before passing fixture cleanup; on uncertainty preserve starting evidence, prevent
pass and use existing failure retention/release. Simple smokes record the final
identity too. Partial failures need not fabricate an end observation. Report
finalization wraps all resource obligations in a finally path. Both session close
and lease release are attempted even if one is interrupted; propagate interruption
after both attempts. Handle KeyboardInterrupt/CancelledError safely. A hard kill
may leave the last `running` snapshot, which cannot validate as completed success.

## Frozen Test Surface Contract

Parent approved the independent schema/API fixture contract in
`.refinement/224-test-contract.md`, including the literal
`tools/simulator/tests/data/report-v1-smoke.json`. Existing HTTP request timeout
is also required in `limits.request_timeout` (10 seconds, per request). This
contract supplies exact nested spellings for the external schema table above.

- Test Author is independent of all Implementers and Reviewers.
- Approved: real temp files; literal hand-derived JSON fixtures and deterministic
  digest calculation; actual report validator/offline CLI; real temp Git repos;
  existing HTTP/lease/fixture/inspection seams; injected UTC/monotonic clocks;
  filesystem write/replace faults; external subprocess build launcher boundary.
- Prohibited: mocking report/schema/provenance implementations or internal domain
  collaborators, private-function assertions, real providers or credentials, new
  test-only production APIs, source-text/Dockerfile matching as container proof.
- Existing tests remain workload/lifecycle protection. Add report assertions to
  representative existing cases, with one parameterized fixture-backed lifecycle
  rig; do not duplicate journey, cleanup, identity-pool or auth test coverage.

Approved Test Value Map: strict validator/config/descriptor mutation partitions;
filesystem reservation/atomicity; four successful report paths; representative
target/setup/correctness/cleanup/retain/release/interruption results and privacy;
initial/later snapshot failure ordering; final identity drift before cleanup;
real Git/build provenance and runtime override rejection; interrupted release.

## Review units and implementation plan

### U1: Scenario/report contracts

Own new `scenarios.py`, immutable catalog JSON, `reports.py` and report tests.

- [x] Independent Test Author freezes exact representative JSON and minimum tests.
- [x] Run focused tests; missing production surfaces must fail, not silently skip.
- [x] Implement named public contracts, strict safe validation and atomic store.
- [x] Run focused pytest, Ruff/Pyright; perform plausible-mutant analysis for
  permissive unknown fields, false successful lifecycle outcomes and overwrites.
- [x] Fresh reviewer returns SPEC/QUALITY/TEST/SCOPE/assurance verdicts.

### U2: Source/build provenance

Own new `provenance.py`, Dockerfile/build wiring and provenance tests; coordinate
Makefile changes with U3 rather than competing edits.

- [x] Independent Test Author supplies real-temp-Git/build-boundary tests.
- [x] Implement clean source identity, temp-context build and immutable runtime
  metadata with byte/lock verification; no environment fallback.
- [x] Run focused pytest/static checks; prove dirty inputs cannot launch work and
  changed packaged bytes/runtime labels cannot claim clean provenance.
- [x] Fresh reviewer returns all independent verdicts.

### U3: Lifecycle/CLI/documentation integration

Own existing runner/target/CLI files, Makefile integration, README, `.gitignore`
and lifecycle tests. Consume U1/U2 public contracts, preserve fixed stdout.

- [x] Test Author extends existing rigs for artifact/ordering/failure proof.
- [x] Implement initial recorder/provenance gate, stage/result hooks, final target
  check, safe failure retention/release and terminal snapshot; add offline CLI.
- [x] Document schema versioning/privacy, unavailable fields, exact reproduction
  recipe, fresh credentials/fixtures, retention/export and hard-crash limitations.
- [x] Run `make sim-check`, `./scripts/doctor.sh`, `git diff --check`; attempt image
  proof only when Docker access and clean source are available. Record unavailable
  checks explicitly without bypassing provenance.
- [x] Fresh unit review.
- [x] Fresh whole-change reviewer at Sol/xhigh: all specification, quality, test,
  scope and selected assurance verdicts PASS; all material findings resolved.
- [x] Parent verified contract coverage, diff and cleanup. Maintainer subsequently
  requested commit, push and a pull request using the repository template.

## Evidence

Baseline `make sim-check`: 422 tests passed, Ruff/Pyright passed, three Semgrep
rule fixtures passed, 15 rules scanned 13 production files with zero findings.
Full transcript: `.refinement/224-baseline.log`.

## Initial automated verification and acceptance evidence

- `make sim-check`: 607 tests passed; catalog/history, Ruff format/lint, strict
  project Pyright (zero errors), three Semgrep fixtures and 15 rules on 16
  production modules passed with zero findings. Logs: `.refinement/224-final-sim-check.log`.
- `./scripts/doctor.sh`: required checks passed after immediate FinnThePanther
  verification; optional Dev Container CLI absent. Log: `.refinement/224-doctor.log`.
- Actual container proof: clean source snapshot built by the repository provenance
  command, source/environment relabel rejection, nonroot runtime, root-owned
  read-only application/metadata, writable mounted output and offline validation.
  Public local smoke ran with `--network none`, intentionally failed target, and
  persisted a valid terminal failure report after container removal. It proves
  packaged execution/lifecycle; it is not live backend acceptance.
  Log: `.refinement/224-image-proof.log`; clean source bundle and report retained.
- Actual host CLI: dirty current source refused before target work with a valid
  failed report. Valid/secret-bearing invalid documents produced only fixed
  success/failure output with empty stderr. Log: `.refinement/224-cli-proof.log`.
- Verification used no live Staging run, credentials, backend migration or deployment.
  Existing HTTP/provider/SSH boundary rigs prove workloads; publication is a separate
  authorized pull-request handoff.

| Acceptance coverage | Evidence |
| --- | --- |
| AC1–2, AC7–8, AC12 | Four command report tests, shared lifecycle/failure matrix, literal report fixtures and clock/storage faults |
| AC3–4 | Closed descriptors/digests, real Git historical mutation/removal/shallow tests; semantic review found no workload changes requiring a second version |
| AC5–6 | Reproduction/schema compatibility documentation, offline actual CLI, fixed scenario/seed/config tests and fresh UUID proof |
| AC9 | Starting/final deployment evidence and drift/unverified negative lifecycle tests before fixture cleanup |
| AC10–11 | Real atomic reservation/replacement faults, strict closed JSON mutation/reader tests, actual container persistence/offline validation |
| AC13–14 | Allowlist/privacy tests, Semgrep, independent review; real Git launcher/namespace/byte integrity and actual immutable-image proof |

## Task retrospective

- Mechanical: run typing from the repository's canonical target/project configuration;
  root-level narrow Pyright calls missed strict settings. Final evidence uses the
  canonical command, not those superseded narrow claims.
- Project context: host launcher/preflight/namespace inputs are part of simulator
  source identity. The bounded input set and regression partitions encode this.
- Mechanical: the cleanup-start snapshot is itself a possible persistence failure.
  The deletion gate now checks that boundary, with a regression in the shared rig.
- One-off: the access/identity interruption is recorded as execution evidence;
  no new global workflow guidance or unrelated environment repair was added.

Final whole-change review resolved the additional AC11 contradiction: whenever
correctness claims success, core phases and applicable complete journey/check
evidence must support it, even if attribution, cleanup or release makes the overall
run fail. Two new mutation partitions protect this boundary. All final reviews
report PASS with no remaining findings; successful authenticated live-backend
execution remains outside this verification run.


## Maintainer live Staging acceptance — 2026-10-05

**PASS.** The maintainer ran all four commands and reproduced `journeys` from clean
simulator revision `1e56a29a379f1ec3a0ecc22645005dfa3bd4d586`. This supplements the
initial automated/container evidence above and closes its live-backend gap.
No promotion was needed: the existing backend included all required pool, fixture,
reconciliation and cleanup operations.

- Staging source: `b20355cb2459a7ad6ea118511c1429aa94d53547`.
- Deployment: `5dd8353e-b28d-4336-90d1-6b46bb6a1e7d`.
- Fresh canonical preflight passed. Each saved report contains that same source,
  deployment and Staging environment in both starting and final observations;
  attribution is `verified`. These observations do not prove continuous stability.
- Runtime: Python `3.13.14`, httpx `0.28.1`; simulator dependency-lock SHA-256
  `c218b2fb441f1016746c100f4b28899b0422585980e934cad5abd76a277dba9f`.
- All commands used scenario version `1` and seed `224`, recorded as unused.
- Reports span `2026-10-05T23:12:05.122397Z` to `2026-10-05T23:21:35.730258Z`.

### Commands and outcomes

From the repository root, after `make sim-setup`, `make sim-catalog-check`, and
credential-free Staging preflight, the maintainer used `r1` and one fresh ignored
report directory. Secrets were supplied only at hidden prompts.

```bash
make sim-smoke TARGET=staging VERSION=1 SEED=224 REPORT_DIR="$SIM224_REPORT_DIR/smoke"
make sim-pool-smoke POOL=r1 COUNT=3 VERSION=1 SEED=224 REPORT_DIR="$SIM224_REPORT_DIR/pool-smoke"
make sim-fixture-smoke POOL=r1 OWNERS=2 FURSUITS=1 CATCHERS=2 VERSION=1 SEED=224 REPORT_DIR="$SIM224_REPORT_DIR/fixture-smoke"
make sim-journeys POOL=r1 VERSION=1 SEED=224 REPORT_DIR="$SIM224_REPORT_DIR/journeys"
make sim-journeys POOL=r1 VERSION=1 SEED=224 REPORT_DIR="$SIM224_REPORT_DIR/reproduction"
```

- `smoke`: setup, workload and reconciliation passed.
- `pool-smoke`: three identities; setup, workload, reconciliation and release passed.
- `fixture-smoke`: four identities and two fixture fursuits; cleanup reported
  convention=1, enrollment=4, fursuit=2, activation=2, catch=0, session=0,
  credential=0, image=2. Release passed.
- Both `journeys` runs: seven identities and four fixture fursuits; all 13 journeys
  passed, 14 reconciliation checks completed with no discrepancies, cleanup and
  release passed. Each cleanup reported convention=1, enrollment=6, fursuit=5,
  activation=4, catch=1, session=4, credential=5, image=5.
- All five reports passed the strict offline `load_report` validator and had
  outcome/correctness `passed`, clean simulator provenance, expected source SHA,
  version/seed and verified attribution. Five run UUIDs were distinct.
- Original and reproduced journeys matched scenario descriptor/digest/configuration,
  source/runtime identity, population, operation profile and limits. Fresh fixtures
  and credentials were used; UUIDs and timestamps/durations differed as expected.
- Before and after: `r1` total=10, available=10, leased=0, quarantined=0;
  retained=0, unfinished=0. Working tree was clean afterward.

### Retained report evidence

The operator retained the five JSON artifacts under the Git-ignored directory
`tools/simulator/reports/224-live-20261005T231122Z/`, one scenario subdirectory per
row below. The SHA-256 digests bind this acceptance record to the original bytes;
raw JSON is retained by the operator and is not committed here.

| Command / evidence | Run UUID | Report SHA-256 |
| --- | --- | --- |
| smoke | `ccb0be6b-008c-4c22-a60e-e5195ceaff5d` | `c632ba2dd6ca8629bbea46e29da7788629666a29ac78b3cb9b220924a147b56a` |
| pool-smoke | `d6b08e60-4fb8-4a65-92cb-a856aaee3dc2` | `6405b8a5c02c0dfb11bb9055a0d80930cd6b4d432921777738be25048ece85d7` |
| fixture-smoke | `4a4f0efe-6394-4e30-8f2f-a9a0365b4ded` | `060ad264ab4af5672cbc10d1b45ed14dba78b6b673d0d8225bc962b8b9b43522` |
| journeys | `e5b3be24-96ca-44fe-8ce3-b5c510b72e9a` | `8f19c848489dbbbfb066582ac58b5fd5c925929aa91feafb97dd8ed2fe988306` |
| reproduction | `2902538c-6065-48cf-bcbe-7691c150c086` | `20346ebee44cf9dcd6ac5298632d7b2dcf4cf8c18badc83fc6902e325c3aad19` |

This closes successful live workload, final attribution, fixture cleanup/release,
report serialization and meaningful reproduction evidence for #224. Live failures,
interruptions, deployment drift and storage faults were not injected; their distinct
negative behavior remains covered by the automated suite and prior container proof.
PR review/merge remains a separate gate; no issue or review thread was closed.

## Post-merge report finalization follow-up — 2026-10-06

After PR #295 merged, a retained CodeRabbit concern was confirmed: recorder phase
updates re-resolved descriptors from disk before entering guarded persistence.
A missing, invalid or changed descriptor could raise `ReportFailed` before fixture
retention/quarantine, session revocation or lease release. This left refined AC8
and original AC5's broader report-stability criterion unchecked.

The recorder now keeps an isolated copy of the resolved scenario admitted at
construction. One shared validator checks recorder candidates against that admitted
contract, while public offline validation and guarded snapshot persistence continue
checking the supported versioned catalog. Unsafe adapters still fail validation.
Later catalog failures set the existing sticky persistence-failure flag, preserve
the last complete snapshot and prevent a successful exit without vetoing resource
obligations. Initial admission remains fail closed before external work. No workload,
schema/version, backend, migration or deployment behavior changes.

Verification for this focused ADW STANDARD COMPACT reliability/data-integrity unit:

- Independent Test Author: seven new cases failed against the original recorder;
  existing unsafe-adapter cases passed. Temporary catalog copies isolate faults
  from the published descriptors.
- After implementation, all seven cases passed. They cover missing/malformed/
  digest-consistent changed descriptors, sticky failure after catalog recovery,
  fixture retention/quarantine before release, release after successful cleanup,
  the separate pool-runner release path, preserved snapshots and sanitized evidence.
- `make sim-check`: 624 tests passed; catalog/history, Ruff format/lint, strict
  Pyright (zero errors), three Semgrep fixtures and 15 rules on 17 production
  modules passed with zero findings.
- `./scripts/doctor.sh`: repository and GitHub authentication checks passed;
  the required Docker-daemon check failed because the daemon was unavailable.
  The optional Dev Container CLI was absent. These tests use filesystem and
  external-provider boundary rigs and require no Docker or live Staging access.
- Fresh independent review: SPEC, QUALITY, TEST, SCOPE, RELIABILITY, DATA INTEGRITY
  and TEST ADEQUACY passed with no findings. Full environment readiness could not
  be verified because the Docker daemon was unavailable.
- Logs: `.refinement/224-finalization-red.log`,
  `.refinement/224-finalization-green.log`,
  `.refinement/224-finalization-sim-check.log` and
  `.refinement/224-finalization-doctor.log`.

The follow-up is reversible by reverting its focused recorder/test/documentation
change. Live provider failure injection and deployment are outside this proof.
The remaining issue checkboxes await review and merge of the follow-up PR; no
CodeRabbit comment is replied to or resolved by this work.
