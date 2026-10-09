# External simulation host implementation plan

> **For agentic workers:** Use subagent-driven development under ADW; Test Author, Implementer and Reviewer remain independent. Steps use checkboxes for tracking.

**Goal:** Implement the approved #228 operator workflow locally, ready for separately authorized DigitalOcean provisioning and live proof.

**Architecture:** A trusted maintainer manifest binds a finite privileged session. Two private Unix sockets forwarded by an owned foreground SSH process carry orchestration and cheap health; a Linux supervisor runs the immutable simulator image and interrupts it on supervision loss. Existing backend relays and public-only simulation remain authoritative.

**Tech stack:** Existing Python 3.13/httpx/uv/Ruff/Pyright/pytest/Semgrep; standard-library asyncio Unix sockets, subprocess, filesystem and flock; OpenSSH and Docker Engine. No new runtime dependency.

## Global constraints

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
- [ ] Record red; implementer wires explicit host path and supervised runtime, preserving local entrypoints.
- [ ] Real socket + small child process walking skeleton proves disconnect stop/no resumption, secret-free stage capture and bounded named-process finalization.
- [ ] Focused tests/static/security checks, commit with verified identity, independent unit reviewer; resolve material findings.

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

Runtime integration consumes `host_release.read_release(path:Path)->dict[str,object]` and `verify_image(release:Mapping[str,object])->dict[str,object]`. Both raise `SourceRejected` on malformed release metadata or image/source mismatch and share the existing closed metadata validation and immutable-image inspection used by archive loading. The source verification container is a bounded offline probe; it does not launch the named workload. This avoids duplicate parsers or temporary metadata workarounds in U2.

`RunArtifacts.record_completion(evidence)->None` validates report attribution, writes durable bounded completion evidence, and checks the budget before and after persistence without accepting a receipt or clearing a hold. `finalize` reuses it before receipt-dependent settlement. The outer operator can pass only after workload success and separately authenticated exact-run recovery resolution. Local pretty-printed JSON inputs use shared `host_protocol.decode_document(raw)`; wire `decode_frame` retains its exact single-newline framing rule.

- [x] Independent Test Author proposes and writes minimum lock/hold/retention/budget/tamper/platform tests, real filesystem/child locks and external Docker boundary substitutes; record red.
- [x] Implementer completes admission/artifacts/releases/bootstrap; U2 subsequently consumes these real domain helpers.
- [x] Narrow checks then independent reviewer; resolve findings.
- [ ] Commit clean verified source; real local container build/provenance/UID/signal/Unixsocket proof with offline boundaries. Task container names carry `tailtag-228-`; no live Staging or secret input.

## Task 4: Operator documentation and integrated evidence (U4)

**Files:** Create `docs/operations/simulation-host.md`, `tools/simulator/host/{normal-profile.json,stop-profile.json,safety.json}` and release metadata example if useful; modify Makefile, simulator README and `.github/workflows/simulator.yml`. Update spec/plan and ignored phase/evidence ledger.

**Interfaces:** Document exact U1–U3 CLI, secret-free Make wrappers, manual recovery commands and all refusal outcomes. Workflow path filters include operator docs/bootstrap/relay inputs. CI remains validation/image build only, never sustained load.

Normal proof profile: twenty identities, five-minute convention-v2 traffic segments with adequate execution/setup margin; ten actor/in-flight caps. Stop profile: smaller bounded existing family suitable for explicit operator SIGINT. Both are preparatory artifacts until live authorization. Include report validation, closed acknowledgement state, exact-run retained inspection/cleanup/pool readmission checks and SSH/hash retrieval. Document DigitalOcean region/plan/budget/account ownership, firewall/key inventory, Linux/Docker patching only between runs, rollback, no automatic restart and explicit recovery-hold resolution.

- [ ] Reviewer verifies each approved AC against code/docs/offline proof or explicit later external gate; no new duplicate tests for prose.
- [ ] Canonical `make sim-check`; `./scripts/doctor.sh` after verified GitHub acting identity; `git diff --check`.
- [ ] Targeted plausible-mutant analysis: repeated allocate, identity override, pending-provision release, renewable health, lock bypass, held-artifact deletion, image tag substitution.
- [ ] Astra implementation security review focused on new privilege/secret boundary; fresh independent whole-change reviewer at Sol/xhigh; resolve material findings.
- [ ] Record local evidence and remaining external ACs; stop/remove only task-owned disposable resources; commit local implementation after Git identity verification. No push or PR publication without authorization.

## Execution record

Design approved on 2026-10-08. Baseline `make sim-check`: 1,115 tests plus catalog/format/lint/types/Semgrep passed. Docker engine became reachable before implementation without this task starting it; 13 pre-existing stopped containers/164 images recorded, preserve them.

Dependency correction during test-surface preparation: U2's real supervisor consumes U3 admission/release helpers, and independent tests correctly do not mock those domain collaborators. Execute U3 filesystem/release/bootstrap production and its focused review after U1, then U2 runtime/walking skeleton; run U3's real-image integration proof after U2. U3 does not edit the not-yet-existing host_runner; U2 wires the approved admission/recovery CLI seams. This changes execution order only, preserving the approved architecture, acceptance contracts, role independence and four review units.

Authoritative live state and detailed review/test outcomes are recorded in `.refinement/228-phase-ledger.md` and this plan's SDD workspace; update after each unit. Tests and production ownership must be disjoint. No independently required role may be collapsed into controller implementation.
