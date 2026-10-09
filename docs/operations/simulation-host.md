# External Staging simulation host

This runbook implements the [approved #228 contract](../specs/2026-10-08-external-simulation-host.md) and [implementation plan](../specs/2026-10-08-external-simulation-host-implementation-plan.md). Local implementation and offline verification do not establish paid-host readiness or live acceptance. Provisioning and Staging traffic require separate explicit authorization; do not close #228 until the external evidence below is collected. CI validates/builds only and never starts sustained load.

## Host selection and private inventory

The approved host is one DigitalOcean Basic x86 Droplet in **NYC3**, with **2 vCPUs, 4 GiB RAM, 80 GiB disk**, advertised at **US$24/month**. The operating budget is **US$30/month before tax**. The refinement quote included 4,000 GiB transfer. Review current included transfer, metered usage and potential overage before provisioning and after each milestone; the US$30 budget is operator policy, not a provider-enforced billing cap. No paid add-ons, automatic resizing, additional paid service, registry, scheduled workload or automatic restart is approved. Confirm the selected plan, price and budget before authorized provisioning; stop if the approved choice is unavailable or the budget would be exceeded. Provider selection and research sources are recorded in the implementation plan.

Use DigitalOcean image `ubuntu-24-04-x64` (Ubuntu 24.04 LTS Noble amd64). Keep the owning account, billing owner, Droplet ID/IP, SSH key fingerprint, allowed maintainer source addresses, and firewall inventory in private operator records. Use key-only SSH administration and a dedicated operator account. Permit SSH only from approved maintainer addresses; expose no application or bridge port. Gameplay and Clerk requests leave the container directly through public HTTPS, rather than through the maintainer bridge.

Bootstrap is secret-free. Its supported Docker packages are fixed, with no latest fallback:

| Package | Version |
| --- | --- |
| `docker-ce`, `docker-ce-cli` | `5:29.9.0-1~ubuntu.24.04~noble` |
| `containerd.io` | `2.4.1-2~ubuntu.24.04~noble` |
| `docker-buildx-plugin` | `0.38.0-1~ubuntu.24.04~noble` |
| `docker-compose-plugin` | `5.6.0-1~ubuntu.24.04~noble` |

Use the official signed Docker apt repository. Host control uses owner-local uv **0.9.17**, whose official amd64 archive SHA-256 is `0114d54f9aafd07516cf1cadfe72afa970f5fd293fbe82dd924b8a7b42c984d8`, and managed CPython **3.13.11** from that uv release's checksum-bound metadata. Ubuntu's system Python remains unchanged. Record installed OS/kernel, Docker, uv, Python and locked dependency versions. The [plan's pinned upstream sources](../specs/2026-10-08-external-simulation-host-implementation-plan.md#task-3-host-admission-artifacts-and-immutable-releases-u3) explain these choices; package availability is mutable and upgrades require a deliberate reviewed pin update between runs.

Disable disk-backed swap, kernel/process core dumps and terminal recording before credential entry. Verify `swapon --show` is empty, `ulimit -c` is zero in the operator session, and `/proc/sys/kernel/core_pattern` is exactly `|/bin/false`; Docker also applies core limit zero. Host prepare/run require Linux amd64 and a nonroot owner. CI configures these same swap/core settings only on its disposable Ubuntu 24.04 runner so the real Linux admission/signal test runs without bypassing policy; it starts no hosted load. Do not run `script`, record a raw TTY, enable shell tracing around prompts, or retain unsanitized diagnostic transcripts. Docker uses logging driver `none`. Clerk secrets are hidden interactive inputs only; no arguments, environment variables, files or image layers carry them. Railway/platform credentials and their existing relay configuration remain exclusively on the maintainer machine.

Keep a private SSH configuration, for example:

```sshconfig
Host tailtag-sim
    HostName <private-inventory-address>
    User <dedicated-operator>
    IdentityFile <private-key-path>
    IdentitiesOnly yes
    ForwardAgent no
    StrictHostKeyChecking yes
    UserKnownHostsFile <private-known-hosts-path>
    ExitOnForwardFailure yes
    StreamLocalBindUnlink no
```

Verify the host key fingerprint through the provider console or another independently trusted channel before adding it to known_hosts. `ssh-keyscan` alone does not authenticate a key. Protect configuration/key/inventory files with owner permissions. Do not bypass a changed key warning. The operator adds two run-private reverse Unix-socket forwards; neither a TCP bridge listener nor SSH agent forwarding is needed.

## Immutable release handoff

Use a clean, verified contributor checkout and the locked simulator environment. Build for `linux/amd64` explicitly; source, dependency-lock hash, image ID and packaged files must verify. A dirty relevant source tree cannot produce an attributed release. Record the resulting immutable `sha256:<64hex>` image ID as `IMAGE_ID`; a tag is only a build convenience.

```sh
make sim-image PLATFORM=linux/amd64
IMAGE_ID="$(docker image inspect --format '{{.Id}}' tailtag-simulator:local)"
umask 077
mkdir -p "$HOME/.local/state/tailtag-host-transfer"
TRANSFER="$HOME/.local/state/tailtag-host-transfer"
make sim-host-release-export IMAGE_ID="$IMAGE_ID" \
  ARCHIVE="$TRANSFER/simulator.tar" RELEASE="$TRANSFER/release.json"
```

After provisioning authorization and key verification, create owner-private host transfer directories:

```sh
ssh tailtag-sim 'sudo install -d -m 0700 -o "$(id -un)" -g "$(id -gn)" /srv/tailtag-simulator /srv/tailtag-simulator/incoming'
```

Release metadata is a closed schema-1 object containing only `schema_version`, `simulator_sha`, `dependency_lock_sha256`, `image_id`, `platform`, and `archive_sha256`. Keep the trusted local metadata alongside the archive. Transfer both with authenticated SSH/SCP to an owner-only incoming directory outside source/image. Record the trusted archive hash locally and compare it on the host before Docker loads anything:

```sh
shasum -a 256 "$TRANSFER/simulator.tar"
scp "$TRANSFER/simulator.tar" "$TRANSFER/release.json" tailtag-sim:/srv/tailtag-simulator/incoming/
ssh tailtag-sim 'sha256sum /srv/tailtag-simulator/incoming/simulator.tar'
```

The host's verified release loader independently compares the archive against trusted metadata before `docker load`, then verifies exact image ID, `linux/amd64`, packaged source SHA and dependency-lock hash. Never select execution by a mutable tag. Retain the previous approved immutable image and release metadata; do not prune them as part of the report budget.

The initial control runtime is installed by the secret-free repository-owned `tools/simulator/host/bootstrap.sh`, delivered from the same clean approved maintainer checkout. Hash it locally, transfer over the verified SSH connection and compare the host hash with the trusted local value before running it. Never download or execute a replacement script to work around a failed check.

```sh
shasum -a 256 tools/simulator/host/bootstrap.sh
scp tools/simulator/host/bootstrap.sh tailtag-sim:/srv/tailtag-simulator/incoming/bootstrap.sh
ssh tailtag-sim 'sha256sum /srv/tailtag-simulator/incoming/bootstrap.sh'
ssh -t tailtag-sim 'sudo bash /srv/tailtag-simulator/incoming/bootstrap.sh \
  --user "$(id -un)" --root /srv/tailtag-simulator \
  --archive /srv/tailtag-simulator/incoming/simulator.tar \
  --metadata /srv/tailtag-simulator/incoming/release.json'
```

Bootstrap installs the pinned OS/tools/SSH configuration, verifies archive hash and immutable image ID/platform, verifies packaged provenance inside that image, and copies `/app` into the owner release directory. It performs a standard-library-only `source.json` file-hash check before any locked host dependency sync, then invokes the installed venv's real `host_release install-runtime` verification. Root setup and nonroot owner runtime installation are distinct; the dedicated owner is in the Docker group and owns `root/tools/uv` and `root/releases/<simulator_sha>`. The simulator container never mounts the Docker socket.

`install-runtime` revalidates copied source and performs locked no-dev sync. Record `SIMULATOR_SHA` from trusted `release.json`; host control Python is `/srv/tailtag-simulator/releases/$SIMULATOR_SHA/.venv/bin/python`. For a later approved release, invoke the verified installed runtime explicitly:

```sh
HOST_PY="/srv/tailtag-simulator/releases/$SIMULATOR_SHA/.venv/bin/python"
cd "/srv/tailtag-simulator/releases/$SIMULATOR_SHA"
"$HOST_PY" -m tailtag_simulator.host_release install-runtime \
  --archive /srv/tailtag-simulator/incoming/simulator.tar \
  --metadata /srv/tailtag-simulator/incoming/release.json \
  --root /srv/tailtag-simulator
```

Bootstrap prints the exact installed host Python path and records package/uv/Python versions in `/srv/tailtag-simulator/tools/versions.txt`. Incoming archive/metadata must remain readable by the dedicated owner. No repository clone, GitHub credential, Railway credential or maintainer home directory is transferred. Installation failures prevent host readiness; a local bootstrap review does not establish that installation on an unprovisioned VM succeeded.

## Profile preparation and foreground execution

The checked-in profile wrappers have exactly `scenario_id`, `scenario_version`, `seed`, and `configuration`. They are preparation examples, with pool `host228`: select an already provisioned, approved Staging synthetic pool in a private copy before prepare. Do not edit the manifest after preparation or put pool/credential inventory in the repository.

| Profile | Population | Traffic | Seed |
| --- | --- | --- | ---: |
| `tools/simulator/host/normal-profile.json` | 2 normal + 2 popular owners; 8 casual + 8 active attendees; one fursuit per owner | baseline convention-v2, active mode, ten actors for 300 seconds | 22801 |
| `tools/simulator/host/stop-profile.json` | 1 normal + 1 popular owner; 1 casual + 1 active attendee; one fursuit per owner | baseline convention-v2, active mode, two actors for 120 seconds | 22802 |

Traffic uses existing finite scheduler semantics, so realized starts, concurrency and completion can differ from the target. Both profiles cap ordinary in-flight requests at ten. `host/safety.json` is a separate safety policy: 900 seconds for setup/execution and 600 seconds shared finalization reserve, 10,000 public execution attempts, 1,000 finalization attempts and at most 50 identities. The five-minute traffic window therefore has setup/drain margin; it is not the entire wall-runtime budget. A reserved control request slot is additional to the ten ordinary requests. Host admission refuses limits beyond 50 identities, ten actors/in-flight requests or 900+600 seconds; health, lease renewals and RPC activity never renew those deadlines.

On the maintainer machine, confirm the existing Railway relay environment and owner manifest are ready, without exporting them to the VPS. Use an interactive terminal with recording disabled. Prepare verifies the current public Staging identity twice using the existing target checker, resolves configuration/safety, validates release metadata, generates a fresh UUID, and writes an owner-only immutable manifest without mutating Staging:

```sh
make sim-host-prepare PROFILE=tools/simulator/host/normal-profile.json \
  SAFETY_CONFIG=tools/simulator/host/safety.json \
  RELEASE="$TRANSFER/release.json" MANIFEST="$TRANSFER/manifest.json"
make sim-host-run MANIFEST="$TRANSFER/manifest.json" HOST=tailtag-sim \
  HOST_ROOT=/srv/tailtag-simulator
```

These Make wrappers invoke the frozen `host_operator prepare --profile --safety-config --release --output` and `run --manifest --host --host-root` CLI. `sim-host-release-export` invokes `host_release export --image --archive --metadata`; `sim-host-release-load ARCHIVE=path RELEASE=path` invokes the same verified `load --archive --metadata` implementation on a machine with Docker. All parameters are secret-free paths, an SSH alias or an immutable image ID. `make sim-host-bootstrap-check` checks Bash syntax without executing bootstrap and is part of canonical `make sim-check`; simulator CI runs that check and builds explicitly for `linux/amd64`, never executes load.

Use a private profile copy when changing the pool. The default local operator state directory is `~/.local/state/tailtag-simulator`; optional `STATE_DIR=path` on `sim-host-run` (CLI `--state-dir PATH`) chooses another owner-private directory. It writes `<UUID>.used.json` before opening SSH and `<UUID>.bridge.json` after revoking workload and joining bridge-owned operations. Both are owner-only closed JSON evidence, with file/parent-directory fsync. The bridge record contains bounded dispatch/attempt/outcome and acknowledgement/uncertainty state, never raw requests or provider details. Preserve and archive these files alongside the original manifest; preserve used-UUID markers even after completion. A completed, interrupted or crashed manifest cannot reopen a session. Each subsequent workload uses `prepare` and a new manifest/UUID; no automatic restart or allocation retry is provided. `--unattended` remains refused. Later scheduling needs separately approved noninteractive authentication, overlap prevention, automated resource-abort policy and schedule-disable/recovery controls; these are outside this issue.

The foreground operator owns the bridge and attached SSH child. It selects the absolute host control Python at `root/releases/<simulator_sha>/.venv/bin/python`, then sends the manifest over a bounded separate SSH control command to `host_runner prepare --root ABSOLUTE_PATH --manifest -`. That command creates only the fresh run's private `rpc`/`control` parents and `control/manifest.json`. The operator then opens attached SSH with `rpc.sock` and `health.sock` reverse forwards and invokes `host_runner run --root ABSOLUTE_PATH --manifest root/runs/<UUID>/control/manifest.json --release root/releases/<simulator_sha>/release.json`. Host control imports from the installed release venv; manual host commands use that same venv and release working directory. The host runner verifies the same release and manifest before workload. The bridge invokes only the existing fixed pool/fixture/inspection relays: neither profile JSON nor socket traffic can select a command, provider or arbitrary path. Setup authority is finite: one allocation, one provision attempt, exact manifest pool/run/index partitions, and bounded inspection/terminal operations. A target mismatch permanently revokes forwarding, including cleanup/release.

The Linux runner holds a whole-host exclusive lock through work and evidence finalization, and creates a durable recovery hold before external work. An overlapping invocation or unresolved hold refuses admission; do not steal a lock or kill an unknown process. Hard host/process failure may leave only the last durable snapshot with unfinished fixtures and unreleased or expired leases, so use the exact-run recovery procedure below even after a reboot. Container name is exactly `tailtag-sim-<UUID>`. Its convention invocation uses `--host-manifest /manifest.json --host-socket-dir /bridge` and the manifest family/pool/version/seed. It omits `--config` and `--safety-config`, so the existing CLI consumes the immutable manifest configuration and safety directly; no competing runtime copy is accepted. It runs direct Python with Docker init, nonroot host UID/GID, core limit zero, no restart and no Docker logging. Only `runs/<UUID>/rpc` and the exact control manifest are mounted read-only; only `runs/<UUID>/reports` is writable. Supervisor control, Docker socket, SSH agent and maintainer credential directories are never mounted.

The supervisor polls health every five seconds, allowing two seconds per request. Thirty seconds since its last fresh live response permanently latches supervision loss and sends SIGINT to that named container's Python process. Recovery of SSH/health does not resume traffic. Operator SIGINT/SIGHUP, SSH exit and the execution deadline revoke workload liveness. Terminal recovery remains bounded when transport survives. After finalization allowance plus ten seconds, the supervisor kills only the named task container and records hard-stop uncertainty; child exit is never proof of remote rollback.

## Observation and controlled stop

For the authorized normal run, observe host Docker CPU/memory and Linux CPU steal, report realized active/in-flight peaks and scheduling lag, and observe existing Staging Railway/Sentry evidence. The companion samples CPU/memory percentages and the cumulative Linux CPU-steal tick counter; retain its actual units, rather than label raw ticks a percentage. Record offered/admitted/skipped/completed work from the report alongside these observations. Record unavailable evidence explicitly; automated backend saturation monitoring is unavailable. Generator saturation or resource failure requires investigation and separate resizing authorization before larger work. Do not equate an offered actor count or a single VM run with backend capacity.

For the separately authorized small stop run, prepare `stop-profile.json` into a new manifest, start foreground execution, then use Ctrl-C in its maintainer terminal or the host stop command from a second trusted SSH session:

```sh
"$HOST_PY" -m tailtag_simulator.host_runner stop \
  --root /srv/tailtag-simulator --run-id "$RUN_ID"
```

SIGINT uses the existing `interrupted`, nonzero report semantics. The watchdog records `supervision_lost` in companion evidence, not as a new schema-4 abort reason. For an observed resource-saturation event, explicitly request the existing resource abort instead:

```sh
ssh tailtag-sim "docker kill --signal=USR1 tailtag-sim-$RUN_ID"
```

Use only the canonical UUID from the trusted manifest and verify the named container belongs to it. SIGUSR1 must reach Python through init and records `resource_saturation`; it is distinct from manual interruption and does not measure saturation. Keep the relevant resource observation separately. Neither stop mode can produce a passing workload report. Wait for bounded finalization and inspect acknowledged fixture/session/lease recovery before another workload.

## Recovery and refusal handling

A report PASS, validated report, clean-looking pool, expired lease, process exit or old hold timestamp cannot clear a recovery hold. Allocation/provision attempts are reserved before dispatch; a lost acknowledgement may mean the remote operation committed. Never retry allocation/provision on the same session or race cleanup/retention/release against a mutation that may still commit. Preserve uncertainty and settle the exact run manually. A pinned-target mismatch requires investigation before any further TailTag recovery action; do not substitute the new deployment tuple for the original receipt.

From the maintainer's existing trusted environment, independently verify current Staging `/health/identity` using the target check and compare its exact source/deployment/environment tuple with the held manifest. Existing relays independently verify provider and deployed target too. Confirm all bridge-owned mutating operations have settled remotely, including any indeterminate provision. Preserve report/companion evidence and inspect the exact retained/unfinished run, then use the existing commands:

```sh
make sim-retained
make sim-pool-status POOL="$POOL"
make sim-cleanup POOL="$POOL" RUN_ID="$RUN_ID"
make sim-pool-status POOL="$POOL"
```

Set `POOL` and canonical `RUN_ID` from the original trusted manifest before these commands, not an assumed example value. `sim-cleanup` accepts retained/provisioned runs and readmits the run's quarantined identities only after verified clean. It does not accept a cleaned/failed row; do not reinterpret that refusal as proof that a lost provision never committed. `FAIL_ATTRIBUTION`, `FAIL_VERIFY`, `FAIL_TARGET`, `FAIL_STORAGE`, `FAIL_LIMIT` or other failure requires investigation, not host hold removal. After storage failure the documented exact-run cleanup may be retried; setup authority remains closed. Existing independent Clerk session closure must also be acknowledged or uncertainty retained.

Set `REPAIRED_INDEX` only from the exact-run verified repair record. Only if an identity remains independently quarantined after verified repair/cleanup, use the existing explicit per-index recovery and recheck pool status:

```sh
make sim-pool-readmit POOL="$POOL" INDEX="$REPAIRED_INDEX"
make sim-pool-status POOL="$POOL"
```

Readmission alone removes no fixtures and cannot establish cleanup. Review the [existing cleanup failure/recovery semantics](../../tools/simulator/README.md#run-lifecycle) before this step.

Completion is deliberately two-phase. The attached runner first validates available report attribution, persists `runs/<UUID>/host.json` completion evidence and leaves `recovery-hold.json` in place. After attached SSH exits, the maintainer operator revokes workload authority, joins its owned mutations, fsyncs local `<UUID>.bridge.json`, and derives the trusted recovery receipt. Only `released` or `no_mutation` may then be sent through a new authenticated SSH control command to `host_runner recovery-resolve --root ABSOLUTE_PATH --run-id UUID --receipt -`, where `-` reads bounded JSON from stdin. Host resolution records `control/recovery.json` and clears only the exact matching hold. Outer operator exit0 requires runner exit0, no operator interruption/deadline breach, settled bridge recovery and a successful separate resolution exit0. A runner exit0 or passing report alone is insufficient.

The trusted receipt's exact shape is `{schema_version:1, run_id, backend_identity, disposition}`. `released` derives only from acknowledged bridge lease release; `no_mutation` only when no mutating dispatch started; every unresolved case is `held`. The UUID and backend tuple must match the original manifest. The simulator's report/RPC reply cannot supply this authority, and the container never mounts the receipt directory.

For manual resolution, after the original target and exact-run recovery checks above have established settled fixture/session/lease state, the maintainer explicitly prepares an owner-private receipt tied to that original tuple, transfers it by verified SSH into the run's supervisor-only control directory, and resolves only that run:

```sh
"$HOST_PY" -m tailtag_simulator.host_runner recovery-resolve \
  --root /srv/tailtag-simulator --run-id "$RUN_ID" \
  --receipt "/srv/tailtag-simulator/runs/$RUN_ID/control/recovery.json"
```

`--receipt PATH` reads an owner-private file; `--receipt -` reads bounded JSON from trusted stdin. Automatic delivery uses stdin after runner completion and never asks the container for a receipt. For manual file delivery, copy only the maintainer-validated receipt into the supervisor control directory and run the command as its owner. Do not fabricate `no_mutation` from absence of a report or `released` from a lease timeout. Missing, mismatched, held or unacknowledged recovery evidence preserves the hold. Investigate retained/unfinished state, acknowledge verified cleanup and lease/session settlement, finalize evidence, and only then admit a new UUID. Do not delete holds by hand or automatically resolve them at startup.

Invalid profile/manifest/release, reused UUID, unsafe/symlinked/foreign paths, missing hidden TTY, unverified host key, failed forwarding, target mismatch, overlap, recovery hold or inadequate storage all refuse execution. Capacity/privileged-operation exhaustion, supervision loss, stage/report write failure and safety stops cannot produce PASS. Read only sanitized stage/companion output; do not enable raw diagnostics to work around a refusal.

## Artifacts, retrieval and maintenance

Owner-only run directories contain `runs/<UUID>/reports/<UUID>.json`, fixed sanitized `runs/<UUID>/reports/stages.log` (at most one MiB), and supervisor-owned `runs/<UUID>/host.json`. `control/manifest.json`, `control/recovery.json` and `recovery-hold.json` stay outside the container-writable report mount. Reports/companion are retained 30 days and stage logs seven days. The aggregate report/log/companion budget is one GiB; each admitted run reserves 32 MiB within both that budget and free filesystem space. During execution, budget/write failures stop work and prevent PASS. Only expired completed-run artifacts are pruned. Active or recovery-held evidence is never pruned or used as expendable storage; resolve its hold explicitly. When admission is storage-blocked, the maintainer owns hash-verified export and exact-run recovery; prune only eligible expired completed evidence, then rerun admission. Do not delete held/live evidence or expand the paid host automatically. Images and rollback releases have their separate lifecycle.

Retrieve selected evidence through verified SSH to an owner-private maintainer archive. Enumerate exact files for the selected UUID; do not copy runtime credential/configuration directories. Capture a SHA-256 inventory on the host, transfer those same report/stage/companion files, and verify hashes locally. For example, after verifying the original canonical UUID and filenames:

```sh
ssh tailtag-sim "sha256sum /srv/tailtag-simulator/runs/$RUN_ID/reports/$RUN_ID.json /srv/tailtag-simulator/runs/$RUN_ID/reports/stages.log /srv/tailtag-simulator/runs/$RUN_ID/host.json"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/reports/$RUN_ID.json" "$TRANSFER/"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/reports/stages.log" "$TRANSFER/"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/host.json" "$TRANSFER/"
shasum -a 256 "$TRANSFER/$RUN_ID.json" "$TRANSFER/stages.log" "$TRANSFER/host.json"
make sim-report-validate REPORT="$TRANSFER/$RUN_ID.json"
```

Keep each milestone in its own owner-private archive directory with original manifest, release metadata, hash inventory and bounded observations; avoid overwriting another run's `host.json`. Validate using the recorded simulator revision/release, rather than assuming the current validator is compatible. Preserve original reports when rolling back.

Patch Linux/Docker and deliberately update pins only between runs after all workload processes end and holds are investigated. Record old/new installed versions and reverify host prerequisites and offline wiring before the next authorized live run. For rollback, select the previous approved immutable image/release, verify its original archive/source/lock/platform again, use its matching host runtime, then prepare a fresh manifest. Do not retag a running workload, reopen its manifest, overwrite its reports, or remove the retained previous image as general cleanup.

## External acceptance record

Keep preparation/offline evidence separate from live evidence. An authorized live milestone needs:

- Provider evidence that this exact host is the approved NYC3 plan, plus installed OS/runtime/package versions and SSH/firewall/swap/core/logging checks.
- The verified immutable image ID, `linux/amd64`, simulator SHA, lock/archive hashes, prepared UUID/configuration/safety, and actual pinned backend source SHA/deployment/environment.
- Public DNS resolution, TLS certificate/hostname verification and actual public peer address evidence from the host. Correlate bounded observation with the run; a maintainer-side probe alone cannot prove container traffic used public ingress. Record provider/region/backend identity without publishing private account or billing identifiers.
- The five-minute/20-identity run's versioned report and companion with CPU, memory, CPU steal, realized concurrency and scheduling-lag evidence, plus backend observations or explicit unavailable status.
- A separate small manual-interrupt run, nonzero/interrupted report, bounded finalization and acknowledged fixture/session/lease recovery; no resumption or overlapping workload.
- Trusted terminal receipts or documented exact-run manual recovery, pool/retained checks, any holds/uncertainty, and hash-verified SSH retrieval into the maintainer's milestone archive.

A successful local test or image build covers only its local assertion. Paid-host, actual public path, live backend identity and acknowledged live recovery remain pending until observed under explicit authorization.
