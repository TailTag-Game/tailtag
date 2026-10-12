# External simulation host implementation plan

> **For agentic workers:** Use subagent-driven development under ADW; Test Author, Implementer and Reviewer remain independent. Steps use checkboxes for tracking.

**Goal:** Implement the approved #228 operator workflow locally, ready for separately authorized DigitalOcean provisioning and live proof.

**Architecture:** A trusted maintainer manifest binds a finite privileged session. Two private Unix sockets forwarded by an owned foreground SSH process carry orchestration and cheap health; a Linux supervisor runs the immutable simulator image and interrupts it on supervision loss. Existing backend relays and public-only simulation remain authoritative.

**Tech stack:** Existing Python 3.13/httpx/uv/Ruff/Pyright/pytest/Semgrep; standard-library asyncio Unix sockets, subprocess, filesystem and flock; OpenSSH and Docker Engine. No new runtime dependency.

## Current native acceptance — 2026-10-10 UTC

The [native Staging proof](2026-10-10-external-simulation-host-staging-proof.md) records the passed twenty-identity five-minute normal run on merged release `28c0799f8a3eea49477e8459587a90178e027503`, the separate intentionally interrupted stop run, public-path observation in its exact container, and complete exact-run recovery. Both completed setup without a 429; this does not identify Clerk's limiter or guarantee future admission. The checked-in normal example now records the separately approved 360-second generation ceiling around the unchanged 300-second traffic schedule, with no other profile or safety changes.

The original reports and earlier failed attempts remain preserved. All twenty identities are available and no task containers or recovery holds remain. Private provider plan class, transfer allowance, usage/overage and project/billing ownership confirmation remain pending before issue closeout. The following dated checkpoints are historical; they are not current pending live gates.

## Historical acceptance follow-up — 2026-10-09

The [approved spec follow-up](2026-10-08-external-simulation-host.md#historical-acceptance-follow-up--2026-10-09) supersedes the original NYC3/80-GiB selection below with the provisioned maintainer-approved **RIC1 v5, 2 vCPU, 4 GiB, 30 GiB, US$0.052/hour, with a US$40/month before-tax operating budget** override. Plan class, transfer allowance and billing ownership are not inferred. Preserve original design/execution records as dated evidence.

Native Ubuntu bootstrap and exact host-run recovery are proven; the local Mac twenty-identity pool authentication smoke passed. Full normal DigitalOcean and separate manual-stop acceptance remain pending. Follow-up U1 repairs generated OpenSSH policy with `AllowTcpForwarding remote` + `PermitListen none`, retains the other restrictions, and requires independent real Unix-positive/TCP-negative proof. Root administration uses the trusted provider console; `tailtag_sim` has no sudo. The sole normal-profile change is per-request `limits.attempts=9000`; ten active actors is not ten RPS, and the safety execution cap remains 10,000. U2 separately repairs renewal/terminal ordering while preserving bridge authority and mutation uncertainty.

## Original global constraints — 2026-10-08

- Acceptance: adjacent approved design plus issue #228 comment 6072384020; no backend, gameplay, report-schema or scenario-semantics change.
- One DigitalOcean NYC3 x86 Basic VM: 2 vCPU, 4 GiB, 80 GiB; selected platform `linux/amd64`.
- One run; 50 identities, ten active actors, ten ordinary in-flight requests plus reserved control; execution at most 900 seconds, finalization at most 600 seconds.
- Manifest and release metadata version 1; direct public Staging/Clerk traffic; pinned exact backend tuple; fresh canonical run UUID.
- 65,536-byte JSON frames; reject duplicate/unknown keys and nonfinite numbers; exact types, including exclusion of boolean-as-integer.
- RPC connections ten; health connections two, independent; framing/write deadlines two seconds; privileged dispatches two with one mutation lane and at most 256/session. No unbounded queues.
- Health poll five seconds; monotonic loss threshold 30 seconds, sticky stop; named Python SIGINT; finalization plus ten-second scheduler margin.
- Owner-only artifacts; reports 30 days, stage logs seven days; aggregate one GiB with 32 MiB reserved/bounded per run; active/recovery holds never pruned.
- No raw TTY capture, secret env/argv/file/image/report/log values, agent forwarding, swap/core dumps or platform authority on VPS.
- Local code is TWO-WAY DOOR. Paid provisioning, live mutation/traffic, secrets, push/publication/deployment remain separately authorized.
- Normal checkout on focused branch is already approved for this work. ADW independent roles replace execution-choice prompts and redundant dual reviewers; carry the approved plan continuously.

## Task 1: Finite privileged bridge (U1)

**Files:** Create `tools/simulator/tailtag_simulator/host_protocol.py`, `host_bridge.py`; tests `tools/simulator/tests/test_host_bridge.py` and `test_host_protocol.py`.

**Interfaces:**

```python
# host_protocol.py: closed data, no network or provider import
def decode_frame(raw: bytes) -> dict[str, object]: ...
def encode_frame(value: dict[str, object]) -> bytes: ...
def validate_manifest(value: object) -> dict[str, object]: ...
# Validators raise fixed-message ValueError; no caller detail escapes.

# host_bridge.py
RelayDispatch = Callable[[str, dict[str, object]],
                         Awaitable[tuple[str, dict[str, object]]]]
class BridgeSession:
    def __init__(self, manifest: dict[str, object], dispatch: RelayDispatch,
                 *, clock: Callable[[], float] = time.monotonic): ...
    async def request(self, channel: str,
                      envelope: dict[str, object]) -> dict[str, object]: ...
    def health(self) -> dict[str, object]: ...  # exact {run_id, live}
    def revoke_workload(self) -> None: ...      # sticky, recovery reserve remains
    def close(self) -> None: ...                # all authority closed
    def evidence(self) -> dict[str, object]: ... # closed sanitized accounting
class BridgeServer:
    def __init__(self, session: BridgeSession, directory: Path): ...
    async def start(self) -> None: ...
    async def close(self) -> None: ...
```

Manifest normalization reuses `resolve_traffic_config` and `resolve_safety_policy`, requires fully normalized equality, pins target Staging and exact scenario/version/seed/release values, derives owner/attendee counts and bounds, and returns a detached copy. `seed` follows existing scenario/report validators. Reject unsupported release platform or missing values before any dispatch.

Dispatch implementation maps the three channels to fixed current Make targets, repository cwd and existing `run_launcher` timeout boundary. It never assembles a shell from caller fields. No API imports enter the simulator package. Each request requires exact existing envelope keys and manifest identity. Fixture arguments carry pool/run; pool envelope carries pool. Validate operation-specific full key sets before reserving attempts.

State algorithm:

```text
before dispatch: validate authority/deadline/envelope/role binding/capacity;
                count operation; atomically reserve one-attempt operations
allocate: require exact count/TTL; freeze validated unique ordered indexes
provision: require owner-first ordered partition and exact fursuit count;
           mark may_have_committed before dispatch; acknowledge only valid PASS
inspection: only exact ownerN/attendeeN mapping after acknowledged provision
terminal: exclude setup permanently; wait boundedly for owned mutation to settle
release: require no unresolved mutation and acknowledged cleanup/retain/all-index
         quarantine after attempted provisioning; close on acknowledged release
disconnect/cancellation: owned dispatch persists; never reset attempt or uncertainty
FAIL_TARGET: sticky revoke all TailTag dispatch; a matching retry cannot reopen
```

Retained counts is eligible once before allocation. Heartbeat only after acknowledged allocation while trusted session remains bounded. Quarantine each allocated index at most once in recovery. Validate existing relay acknowledgement fields using real current contracts (not invented replacements); unrecognized/malformed output cannot grant authority or leak raw fields. Population inspection returns only the existing closed read-only contract. Cache validated allocation/provision responses for session accounting; reject retries without redispatch. An indeterminate mutating outcome holds recovery and blocks unsafe terminal dispatch.

Two socket listeners isolate admission. Each handler reads at most limit+1 with a deadline, admits bounded clients without waiting in an unbounded queue, validates exactly one frame, and writes a bounded sanitized response. Health performs no provider command. Refuse symlink/pre-existing paths, use owner permissions, remove only owned sockets at close. Server shutdown joins owned operations within remaining reserve and records unresolved outcomes.

- [x] Test Author submits minimal Failure Mode Inventory/Test Value Map; parent approves shape.
- [x] Author writes real manifest/state/socket tests; boundary relay callback captures dispatches. Record red due missing production modules, not defective fixtures.
- [x] Implementer builds only the specified bridge files; demonstrate valid lifecycle, replay/disconnect, pending/uncertain mutation, wrong tuple/role and malformed/slow input refusal.
- [x] Run focused tests, Ruff, strict Pyright and Semgrep. Commit unit after identity check.
- [x] Fresh reviewer returns SPEC/QUALITY/TEST/SCOPE and SECURITY/DATA INTEGRITY/RELIABILITY; resolve material findings before U2.

Behavioral example for the independent author to adapt, rather than mirror implementation:

```python
async def exercise_replay(session, allocation):
    first, second = await asyncio.gather(
        session.request("pool", allocation),
        session.request("pool", allocation),
    )
    assert sum(reply["result"] == "PASS" for reply in (first, second)) == 1
    # Boundary capture must also prove exactly one external allocation dispatch.
```

Run focused tests using `uv --directory tools/simulator run --locked --no-sync pytest tests/test_host_protocol.py tests/test_host_bridge.py -q`.

## Task 2: Session orchestration, transport and supervision (U2)

**Files:** Create `tools/simulator/tailtag_simulator/host_channel.py`, `host_operator.py`, `host_runner.py`; modify `__main__.py`; tests `test_host_channel.py`, `test_host_runtime.py`, targeted existing CLI tests.

**Interfaces:** Consumes U1 manifest/BridgeSession/BridgeServer. `host_channel` is a launcher shim CLI with fixed channel and socket directory args; it accepts existing envelope on stdin, returns exact relay reply and matching exit code. `host_operator` is maintainer CLI `prepare` and `run`; `host_runner` is Linux CLI `run` and exact named-container `stop`.

```text
prepare --profile PATH --safety-config PATH --release PATH --output PATH
run --manifest PATH --host SSH_ALIAS --host-root ABSOLUTE_PATH
host-runner run --manifest PATH --release PATH --root ABSOLUTE_PATH
host-runner stop --root ABSOLUTE_PATH --run-id UUID
```

Freeze exact CLI grammar in the unit tests/runbook. `prepare` creates UUID, normalizes existing profiles/safety, loads verified release, and verifies public Staging identity using existing `open_client`/`resolve_target`/`verify_target` before writing owner-only manifest. It does not mutate Staging. Treat supplied manifests as immutable once session opens; keep durable local used-session markers, refuse reuse. `run` validates host alias/root as bounded safe values and constructs fixed SSH argv; disable agent forwarding, require verified host key and `ExitOnForwardFailure`, and two streamlocal forwards with unlink disabled. No input data becomes a shell command. Encode the remote fixed command's bounded path arguments with deliberate POSIX quoting where SSH requires a command string.

Approved Test Surface supplement: shim grammar is `python -m tailtag_simulator.host_channel --channel {pool,fixture,inspection} --socket-dir ABSOLUTE_PATH`. Profile wrapper is exactly `{scenario_id,scenario_version,seed,configuration}`. Production async seams are `host_operator.run_session(manifest, host, host_root, *, state_dir=None, clock=time.monotonic, sleep=asyncio.sleep)` and `host_runner.supervise_run(manifest, release, root, *, clock=time.monotonic, sleep=asyncio.sleep)`, returning integer exit code. Optional operator `--state-dir` defaults to `~/.local/state/tailtag-simulator`; used-UUID markers survive crashes/completion. The fixed container name is `tailtag-sim-<run UUID>`. Host-only `convention --stage-log PATH` captures only `_emit` output, with a one-MiB cap and owner permissions. Host manifest/socket flags are paired, convention-v2 only. Tests assert external observable behavior rather than internal getters.

Before workload: verify remote immutable release/manifest, establish private session paths, then serve sockets and start owned foreground SSH child with inherited TTY. Transfer secret-free data via authenticated SSH/SCP only. Relay credentials stay maintainer-side. On operator SIGINT/SIGHUP or SSH exit revoke workload immediately; allow bounded terminal recovery while transport survives; close session after settlement. Fresh health depends on trusted deadline plus owned SSH process state, not caller traffic. Clean only task-owned local session sockets/processes.

Remote layout: `root/runs/<UUID>/rpc/rpc.sock` is the only socket directory mounted read-only into the container. `root/runs/<UUID>/control/{health.sock,manifest.json,recovery.json}` is host/operator-only; only the manifest file is separately mounted read-only. Reports and bounded stage log live in `root/runs/<UUID>/reports`; `host.json` companion and recovery hold stay outside that writable mount. Local BridgeServer's two sockets remain in one private local directory. A preliminary bounded fixed SSH command invokes `host_runner prepare --root --manifest PATH` to create only owner-private rpc/control parents and exact manifest before the main SSH requests its two forwards. Admission accepts only this prepared skeleton (including expected owned sockets), with no prior reports, host evidence, hold or completion; it then locks and creates durable run state before workload. Unexpected files, foreign owners, symlinks or a changed manifest refuse admission.

`__main__` explicit `--host-manifest` and `--host-socket-dir` convention-only option loads/validates manifest, requires matching family/pool/config/safety/version/seed/source, passes run UUID to existing `RunReport`, and selects shim commands for all three launcher classes. Ordinary invocations preserve defaults and existing tests. No secret is supplied through these options. Finalizer, target probes and SIMULATION clients remain unchanged.

Host supervisor launches direct Python container with `--init`, no automatic restart, `--log-driver=none`, core limit zero, nonroot UID/GID, read-only socket/manifest mounts and owner-writable reports. No Docker socket/agent/platform dirs inside. Retain inherited TTY for hidden Clerk prompt; stage output is captured only through the simulator's fixed `_emit` channel, never raw terminal bytes. Add an explicit bounded stage-log destination if needed, safe file path host-owned, preserving ordinary console output.

Supervisor runs independently of interactive stdin, polls health every five seconds, latches at 30 seconds without fresh live response, SIGINTs exact named container, waits final_seconds+10, then kills only that container and records uncertainty. Python must receive SIGINT through init; preserve existing report interrupted semantics. Host wall execution deadline is independent and nonrenewable. Samples CPU/memory and Linux CPU-steal into closed bounded evidence; use Docker stats and `/proc/stat` as external boundaries. Resource saturation remains manual SIGUSR1. No capacity claim.

- [x] Independent Test Author submits minimal transport/CLI/foreground/signal failure modes and approved behavioral test shape.
- [x] Record red; implementer wires explicit host path and supervised runtime, preserving local entrypoints.
- [x] Real socket + small child process walking skeleton proves disconnect stop/no resumption, secret-free stage capture and bounded named-process finalization.
- [x] Focused tests/static/security checks, commit with verified identity, independent unit reviewer; resolve material findings.

Whole-change review tightened two existing success/ownership contracts. `RunArtifacts.record_completion(evidence, *, require_pass=False)` preserves bounded nonzero/pre-report evidence; prospective runner success requires a present, attributed schema-valid report with `outcome == "passed"`. A nonzero runner never triggers automatic receipt resolution, even when backend lease release was acknowledged: Clerk/session uncertainty requires exact-run manual recovery.

The attached Docker invocation writes its newly created full container ID to supervisor-only `control/container.cid` and labels the container `tailtag.run_id=<UUID>`. Safe owner/single-link/regular-file validation and mode 0600 establish the fresh Docker-created CID as this invocation's owned resource before awaiting inspection. Normal supervision/success and persisted manual stop additionally require inspection equality for Id/Name/immutable Image/run label. Subsequent inspect/stats/signal/wait/removal and stop use the bound CID, never name-only action authority. An initial exact-name check refuses collisions but is not ownership proof. Missing/invalid CID retains a manual hold and grants no foreign-container action. An initial inspection failure still triggers bounded cleanup of the positively created CID; it cannot abandon the owned Python workload. The pinned [Docker CLI29.9.0 create path](https://github.com/docker/cli/blob/v29.9.0/cli/command/container/create.go) writes CID before the [run path starts the container](https://github.com/docker/cli/blob/v29.9.0/cli/command/container/run.go); a missing CID cannot start the Python workload under that approved CLI. These are bounded corrections within the approved architecture.

Startup interruption freezes/reaps the owned Docker client, then discovers any fresh CID before bounded exact-ID cleanup. Cleanup is shielded and joined through repeated caller cancellation while the host lock remains held; client-reap uncertainty cannot skip an already-owned workload. The Docker client also uses `--sig-proxy=false` and its own session while retaining inherited terminal descriptors. The [pinned CLI signal path](https://github.com/docker/cli/blob/v29.9.0/cli/command/container/signals.go) otherwise forwards catchable process-group HUP into Python, bypassing supervisor-controlled graceful interruption. The supported-Linux SIGHUP proof therefore targets the isolated host process group and verifies client session separation, explicit SIGINT, interrupted report and preserved hold; the offline real-container proof verifies inherited hidden-input TTY behavior without live credentials.

Fresh validated CID ownership is independent of persistence success. File/directory fsync failure still refuses normal admission and preserves uncertainty, but bounded cleanup reads the validated current-invocation CID without requiring another successful sync. Cleanup also discovers a fresh CID when cancellation prevents assigning the Docker `Process`: the pinned [CPython 3.13.11 creation path](https://github.com/python/cpython/blob/v3.13.11/Lib/asyncio/unix_events.py) closes and joins its owned subprocess transport before propagating creation cancellation. No new spawn abstraction or name fallback is introduced. Independent file/parent-directory fsync failure partitions extend the existing real-child startup family.

## Task 3: Host admission, artifacts and immutable releases (U3)

**Files:** Create `host_artifacts.py` and `host_release.py`; modify `provenance.py`; create `tools/simulator/host/bootstrap.sh`; tests `test_host_artifacts.py`, `test_host_release.py`, targeted provenance tests. U2 owns all `host_runner.py` wiring after the U3 helper review gate.

**Interfaces:** Runtime consumes admission context that holds Linux flock through container/evidence finalization; release verifier consumes closed metadata with simulator_sha, dependency_lock_sha256, image_id, platform, archive_sha256, schema_version. Artifact operations accept only canonical run UUIDs within trusted owner root. No general path deletion API.

Host admission sequence:

```text
validate platform/prerequisites/no swap/core policy/root permissions
acquire nonblocking exclusive host lock; reject unresolved recovery holds
prune only expired completed artifacts, never held/active evidence
reserve 32 MiB under one-GiB total and filesystem free-space bound
create run directory 0700 and durable recovery-hold before any external work
verify archive hash, loaded image ID/platform and packaged provenance
launch; bounded sampling and artifact measurement; stop on write/budget failure
validate report and acknowledgement evidence; persist final companion atomically
clear recovery-hold only with acknowledged recovery; release lock
```

Report validation alone does not prove bridge settlement: host companion must receive the trusted operator recovery result without mounting supervisor control into the simulator. Define a separate operator-to-host final receipt through the owned SSH channel, containing exact run/target/closed disposition; absent/mismatched receipt preserves hold. A cleanup-pass report or caller-controlled socket reply cannot clear it. Exact manual resolution requires operator's documented recovery checks and an explicit command, never startup heuristic.

Approved Test Surface supplement: `host_artifacts.admit_run(root, manifest, *, clock=time.time)` is a context manager returning `RunArtifacts` with `report_dir`, `stage_log_path`, `companion_path`, `check_budget()` and `finalize(evidence, recovery_receipt=None)`. `resolve_recovery(root, run_id, receipt)` backs explicit `host_runner recovery-resolve --root --run-id --receipt PATH`. Receipt shape is exactly `{schema_version:1,run_id,backend_identity,disposition}`; dispositions are `released`, `no_mutation`, `held`. Maintainer derives `released` only from acknowledged bridge release; `no_mutation` only when no mutating dispatch started; otherwise `held`. Host accepts only matching original UUID/tuple from its separate trusted operator control channel. Manual recovery binds the original tuple in the receipt and independently verifies current Staging identity before existing exact-run recovery commands. Release CLI `export --image sha256:ID --archive PATH --metadata PATH` and `load --archive PATH --metadata PATH` share `load_release(archive:Path, metadata:Path)->str` immutable-ID verification. `provenance inspect` returns actual `load_source` JSON for packaged verification.

Pruning uses fixed file classes and persisted completed timestamp; symlinks/foreign modes/paths fail closed. Monitor actual report/log/companion bytes and halt before reserving budget is consumed; preserve current/held files, record disk uncertainty. Retrieval copies selected owner artifacts over SSH and verifies SHA-256 against owner manifest; milestone archive destination is operator-managed, not another paid service.

Extend provenance build with optional explicit `--platform linux/amd64` (ordinary default unchanged), validate platform against supported list before subprocess, retain clean inputs and source.json hashes. Release CLI exports archive and closed metadata after verifying image inspection/source, then `load` verifies archive hash before Docker load and exact loaded ID/platform/source after. Execute immutable ID, never a tag. Keep previous approved image; rollback never overwrites reports. Track and remove only task-created disposable build resources at local completion.

Bootstrap targets DigitalOcean `ubuntu-24-04-x64`, Ubuntu 24.04 LTS Noble amd64, and the official signed Docker apt repository. Research on 2026-10-08 froze these available pins: `docker-ce` and `docker-ce-cli` = `5:29.9.0-1~ubuntu.24.04~noble`; `containerd.io` = `2.4.1-2~ubuntu.24.04~noble`; `docker-buildx-plugin` = `0.38.0-1~ubuntu.24.04~noble`; `docker-compose-plugin` = `5.6.0-1~ubuntu.24.04~noble`. No silent latest-version fallback or arbitrary environment override. Maintainer updates pins intentionally between runs and records installed versions; the upstream index is mutable, not an immutable mirror.

Sources: [DigitalOcean images](https://docs.digitalocean.com/products/droplets/details/images/), [Docker Ubuntu install](https://docs.docker.com/engine/install/ubuntu/), [official Noble amd64 package index](https://download.docker.com/linux/ubuntu/dists/noble/stable/binary-amd64/Packages.gz), [OpenSSH reverse socket forwarding](https://man.openbsd.org/ssh.1#-R), [streamlocal socket permissions](https://man.openbsd.org/sshd_config#StreamLocalBindMask), [Docker init](https://docs.docker.com/reference/cli/docker/container/run/#init).

Nonsecret idempotent preflight/configuration refuses wrong OS/arch, disables swap/core dumps/TTY recording, and configures private directories and SSH streamlocal forwarding for the operator account. Do not provision or run bootstrap on a real VM during local implementation. No public bridge port, paid add-on or auto-resize.

Host control runs outside the simulator container. Ubuntu's system Python stays unchanged; bootstrap installs host-local uv `0.9.17` from its official amd64 archive, SHA-256 `0114d54f9aafd07516cf1cadfe72afa970f5fd293fbe82dd924b8a7b42c984d8`, and uses its checksum-bound metadata to install managed CPython `3.13.11`. This is the newest 3.13 patch in that uv release's frozen download list and satisfies current project/lock constraints. The verified image's `/app` source, source.json and lock are copied into owner-only `root/releases/<simulator_sha>`; locked no-dev sync creates its host venv. Invoke that venv's Python explicitly for host_runner; no GitHub/platform credential or repository clone is required on VPS. Record installed tool/runtime/dependency versions. Source: [uv0.9.17 release](https://github.com/astral-sh/uv/releases/tag/0.9.17), [versioned Python metadata](https://github.com/astral-sh/uv/blob/0.9.17/crates/uv-python/download-metadata.json), [frozen Python lists](https://docs.astral.sh/uv/concepts/python-versions/).

`host_release.install_runtime(archive:Path, metadata:Path, root:Path)->Path` backs `install-runtime --archive --metadata --root`; it uses verified immutable image/source, copies into the owner release directory, revalidates copied source.json against trusted metadata before locked sync, and refuses incompatible existing source. Host-local uv resides at `root/tools/uv`. A targeted distinct test proves that tampered copied control source cannot reach sync/execution; this closes the newly discovered host-runtime readiness seam without adding an alternate distribution channel.

The actual immutable-image walking proof invalidated the original Docker-copy fixture assumption: nonroot `docker cp` applied read-only image directory modes before extracting their files and failed at `.venv/.gitignore`. Replace that extraction with a bounded fixed stdlib copier inside the already verified immutable image. It mounts only the freshly created empty owner-private runtime at `/output`, copies `/app` with `shutil.copytree`, `copy_function=shutil.copyfile` and `symlinks=True`, and excludes exactly the top-level image `.venv`. It runs as the owner UID/GID with init, no network, read-only root, dropped capabilities, no new privileges, no logging and core limit zero. Serialize the bind mount as CSV; caller paths never enter the fixed Python program. Keep the 300-second/65,536-byte transfer bound and five-second exact named cleanup, including failure/cancellation. An existing approved runtime is never granted this mount. Host source/hash/path/symlink validation still precedes permission normalization, locked dependency sync and copied-code execution; a partial failed install remains refused. Remove obsolete copied-image-venv deletion logic. Bootstrap's stdlib `copy_runtime(image, runtime)` follows the same ordering, without importing unverified host code. Independent authors extend the existing install family for real read-only extraction ordering and add one distinct actual bootstrap-helper case; nested manifest-bound `.venv` source remains preserved. Astra accepted this TWO-WAY correction within the approved architecture.

Runtime integration consumes `host_release.read_release(path:Path)->dict[str,object]` and `verify_image(release:Mapping[str,object])->dict[str,object]`. Both raise `SourceRejected` on malformed release metadata or image/source mismatch and share the existing closed metadata validation and immutable-image inspection used by archive loading. The source verification container is a bounded offline probe; it does not launch the named workload. This avoids duplicate parsers or temporary metadata workarounds in U2.

`verify_image_async(release, *, timeout_seconds=30.0)` shares those validators, cancels and joins its owned worker on interruption, and uses a total inspection/source deadline of at most 30 seconds. External stdout is capped at 65,536 bytes, stderr discarded, transfer/install commands bounded at 300 seconds, and named source/copy cleanup shares one five-second removal/absence-confirmation deadline plus bounded client reaping. Cleanup must acknowledge removal or successfully confirm exact absence; daemon/removal uncertainty cannot become success. Bootstrap's initial standard-library probe follows the same contract. After locked host sync, bootstrap validates local installed-interpreter provenance directly; it does not nest another Docker-owning installer.

`RunArtifacts.record_completion(evidence)->None` validates report attribution, writes durable bounded completion evidence, and checks the budget before and after persistence without accepting a receipt or clearing a hold. `finalize` reuses it before receipt-dependent settlement. The outer operator can pass only after workload success and separately authenticated exact-run recovery resolution. Local pretty-printed JSON inputs use shared `host_protocol.decode_document(raw)`; wire `decode_frame` retains its exact single-newline framing rule.

- [x] Independent Test Author proposes and writes minimum lock/hold/retention/budget/tamper/platform tests, real filesystem/child locks and external Docker boundary substitutes; record red.
- [x] Implementer completes admission/artifacts/releases/bootstrap; U2 subsequently consumes these real domain helpers.
- [x] Narrow checks then independent reviewer; resolve findings.
- [x] Commit clean verified source; real local container build/provenance/UID/signal/Unixsocket proof with offline boundaries. Task container names carry `tailtag-228-`; no live Staging or secret input.

## Task 4: Operator documentation and integrated evidence (U4)

**Files:** Create `docs/operations/simulation-host.md`, `tools/simulator/host/{normal-profile.json,stop-profile.json,safety.json}` and release metadata example if useful; modify Makefile, simulator README and `.github/workflows/simulator.yml`. Update spec/plan and ignored phase/evidence ledger.

**Interfaces:** Document exact U1–U3 CLI, secret-free Make wrappers, manual recovery commands and all refusal outcomes. Workflow path filters include operator docs/bootstrap/relay inputs. CI remains validation/image build only, never sustained load.

Normal proof profile: twenty identities, five-minute convention-v2 traffic segments with adequate execution/setup margin; ten actor/in-flight caps. Stop profile: smaller bounded existing family suitable for explicit operator SIGINT. Both are preparatory artifacts until live authorization. Include report validation, closed acknowledgement state, exact-run retained inspection/cleanup/pool readmission checks and SSH/hash retrieval. Document DigitalOcean region/plan/budget/account ownership, firewall/key inventory, Linux/Docker patching only between runs, rollback, no automatic restart and explicit recovery-hold resolution.

- [x] Reviewer verifies each approved AC against code/docs/offline proof or explicit later external gate; no new duplicate tests for prose.
- [x] Canonical `make sim-check`; `./scripts/doctor.sh` after verified GitHub acting identity; `git diff --check`.
- [x] Targeted plausible-mutant analysis: repeated allocate, identity override, pending-provision release, renewable health, lock bypass, held-artifact deletion, image tag substitution.
- [x] Astra implementation security review focused on new privilege/secret boundary; fresh independent whole-change reviewer at Sol/xhigh; resolve material findings.
- [x] Record local evidence and remaining external ACs; stop/remove only task-owned disposable resources; commit local implementation after Git identity verification. No push or PR publication without authorization.

## Execution record

Design approved on 2026-10-08. Baseline `make sim-check`: 1,115 tests plus catalog/format/lint/types/Semgrep passed. Docker engine became reachable before implementation without this task starting it; 13 pre-existing stopped containers/164 images recorded, preserve them.

Dependency correction during test-surface preparation: U2's real supervisor consumes U3 admission/release helpers, and independent tests correctly do not mock those domain collaborators. Execute U3 filesystem/release/bootstrap production and its focused review after U1, then U2 runtime/walking skeleton; run U3's real-image integration proof after U2. U3 does not edit the not-yet-existing host_runner; U2 wires the approved admission/recovery CLI seams. This changes execution order only, preserving the approved architecture, acceptance contracts, role independence and four review units.

Authoritative live state and detailed review/test outcomes are recorded in `.refinement/228-phase-ledger.md` and this plan's SDD workspace; update after each unit. Tests and production ownership must be disjoint. No independently required role may be collapsed into controller implementation.

Integrated correction checkpoint: U1, U3 helper/bootstrap and U4 integration unit reviews passed; U2 corrections include attributed passed-report enforcement, fresh CID ownership, joined startup/cancellation cleanup and isolated Docker signal handling. Native process-group HUP reproduced the missing graceful finalization, then passed unchanged on commit `3f99623` in a real isolated Ubuntu 24.04 amd64 guest (one case, 10.59 seconds; no swap, core limit zero, core pattern `|/bin/false`). This proves local signal handling, not DigitalOcean capacity or live acceptance. Final CID-durability review, real image/runtime/TTY proof, canonical validation and final whole-change verdict remain open at this checkpoint.

Canonical checkpoint at `6fb0343`: 1,341 tests passed, one macOS supported-Linux case skipped (separately proven above), Ruff/format/strict Pyright/catalog/bootstrap syntax passed, and Semgrep reported zero findings. Final U2 and U4 scoped reviews and targeted Astra implementation review passed. Real archive export/load/hash/platform/provenance passed. Actual Docker CID/init/nonroot/SIGINT and inherited hidden-input TTY passed; macOS-shared Unix socket connection was refused, so an isolated trusted Linux controller and task-private volume proved the actual read-only RPC socket/ACK without exposing Docker authority to the workload. Temporary controller/volume are disposable. The failed first installation requires the bounded copier correction, independent regressions/review, clean rebuild and actual install proof before final completion; this checkpoint does not claim those gates passed.

### Final local implementation — 2026-10-08

Production source is `912f3d70c1f23b7e717b0e5a8311acdb15682a33` on `feat/external-simulator-host-228`, against baseline `9eecb7a`. U1–U4 and the fresh whole-change reviewer returned SPEC, QUALITY, TEST, SCOPE, SECURITY, DATA INTEGRITY and RELIABILITY PASS. Targeted Astra implementation and extraction-delta reviews passed. All material findings are resolved. The read-only-source first-install assumption was corrected only after actual Docker failure and independent regression evidence; the replacement then passed the actual installation. No unrelated scope or material code/test sprawl remains.

| Required proof | Final result |
| --- | --- |
| `make sim-check` on `912f3d7` | 1,342 passed, one macOS Linux-only skip, 80.24 seconds; 90 files formatted, Ruff and strict Pyright clean, catalog/bootstrap syntax passed; three Semgrep fixtures passed and 15 rules/38 targets found zero issues |
| Supported Linux signal behavior | Actual nonroot Ubuntu 24.04 amd64 guest, no swap/core dumps; unchanged process-group HUP case failed before the two signal fixes and passed at `3f99623` in 10.59 seconds |
| Actual immutable delivery | Clean `linux/amd64` image build, archive export/load, immutable ID/platform and packaged provenance verified |
| Actual corrected host installation | Nonroot read-only source copy; checksum-pinned uv 0.9.17, managed Python 3.13.11, locked no-dev sync/httpx 0.28.1; all 56 source files and `source.json` match image bytes after sync; root/runtime 0700 and source/receipt files 0600 |
| Docker wiring and hidden input | CID/UUID-label/image binding, init/direct nonroot Python SIGINT, restricted mounts and private Linux RPC socket/ACK passed; inherited PTY/new session/no signal proxy accepted hidden fake input without echo or persisted transcript |
| Contributor environment | Fresh `gh api user --jq .login` returned `FinnThePanther`, then `./scripts/doctor.sh` passed; optional Dev Container CLI absent warning |

Selected release source: `912f3d70c1f23b7e717b0e5a8311acdb15682a33`. Immutable image: `sha256:df6e7d18a7af10457653a4ecc7b32ad79c30c4c726a0977d0a0f89b1e4077901`. Archive SHA-256: `3d015d6a8b147dc3f2ded3b71dc591e3dd439b15a539914ffe1caf03f30333c8`. Parent independently verified the archive hash, image ID/platform and frozen dependency-lock hash. Selected image/archive/closed metadata remain useful local handoff artifacts. Detailed local proof and per-AC external-gate accounting live in ignored `.refinement/228-real-image-final-evidence.md`, `228-contract-coverage.md`, `228-assurance-map.md`, unit/whole review reports and the phase ledger.

Docker wiring proof used the earlier clean `6fb0343` image, with its exact SHA/ID recorded, and was retained for the source-copy-only correction because Dockerfile, runner flags and that wiring were unchanged. macOS-shared Unix socket connection refused with errno 111; the actual connection passed using an isolated trusted Linux controller and private disposable volume. Actual image/delivery checks used local amd64 emulation on ARM64; the separate Ubuntu signal proof used a real isolated guest kernel. Neither establishes native DigitalOcean readiness, capacity or live public-path acceptance.

Task-created VM/controller/probe containers, networks/volumes, guest keys/disks, temporary installed runtimes/uv/Python/caches, QA tools image and superseded release image are removed. Shared engine, base/reusable images and pre-existing services are preserved. Four durable task-retro lessons were captured locally; behavioral protections and runbook context carry the corrections without unrelated repository-guidance changes. Local source/docs remain a TWO-WAY DOOR.

**External acceptance status at 2026-10-08 (historical):** paid NYC3 provisioning, full native Ubuntu bootstrap, verified host/SSH policy, public Staging/Clerk normal twenty-identity five-minute and smaller stop runs, actual resource/accounting/lag and exact fixture/session/lease recovery, and authenticated artifact retrieval were pending. The later native acceptance checkpoint above records the approved override and completed live milestones; private provider inventory remains pending. Issue #228 remains open for private inventory confirmation and final publication/closeout. The original local implementation was committed; publication of the new acceptance record is a separate action.
