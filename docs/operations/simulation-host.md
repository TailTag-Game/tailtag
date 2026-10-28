# External Staging simulation host

This runbook implements the [approved #228 contract](../specs/2026-10-08-external-simulation-host.md) and [implementation plan](../specs/2026-10-08-external-simulation-host-implementation-plan.md). The [native Staging proof](../specs/2026-10-10-external-simulation-host-staging-proof.md) records completed live normal, controlled-stop and public-path milestones; private provider inventory remains pending. Local implementation and offline verification alone do not establish live acceptance. Provisioning and Staging traffic require separate explicit authorization; do not close #228 until the external evidence below is collected. CI validates/builds only and never starts sustained load.

The Mac side of the host workflow (`sim-host-collect`, `sim-host-release-export`, `sim-host-release-load`) needs macOS or Linux on the maintainer machine; WSL works. It uses `fcntl` locks and walks evidence trees with directory descriptors. On native Windows these tasks print `FAIL  The simulation host workflow needs macOS or Linux (WSL works)` and fail. `sim-image` and the offline simulator tasks run natively on Windows. Runs start on the host itself, in a [host operator session](#host-operator-session).

## Host selection and private inventory

The provisioned host uses the maintainer-approved override: **DigitalOcean RIC1, v5, 2 vCPUs, 4 GiB RAM, 30 GiB disk**, at **US$0.052/hour**, with a **US$40/month before-tax operating budget**. This supersedes the original NYC3/80-GiB, US$24/month proposal and US$30/month operating budget. The original proposal and research remain historical evidence in the implementation plan. Plan class, transfer allowance and billing ownership are not established by this override; retain verified provider details in private inventory. Review metered usage and potential overage after each milestone. No paid add-ons, automatic resizing, additional paid service, registry, scheduled workload or automatic restart is approved. Further provisioning or a host/budget change requires separate authorization.

Use DigitalOcean image `ubuntu-24-04-x64` (Ubuntu 24.04 LTS Noble amd64). Keep the owning account, billing owner, Droplet ID/IP, SSH key fingerprint, allowed maintainer source addresses, and firewall inventory in private operator records. Use key-only SSH access and the dedicated `tailtag_sim` owner account, which has no sudo access. Perform administrative root setup through the trusted provider console; ordinary transfer, runtime and recovery commands use owner SSH. Permit SSH only from approved maintainer addresses; expose no application or bridge port. Gameplay and Clerk requests leave the container directly through public HTTPS, rather than through the maintainer bridge.

Bootstrap is secret-free. Its supported Docker packages are fixed, with no latest fallback:

| Package | Version |
| --- | --- |
| `docker-ce`, `docker-ce-cli` | `5:29.9.0-1~ubuntu.24.04~noble` |
| `containerd.io` | `2.4.1-2~ubuntu.24.04~noble` |
| `docker-buildx-plugin` | `0.38.0-1~ubuntu.24.04~noble` |
| `docker-compose-plugin` | `5.6.0-1~ubuntu.24.04~noble` |

Use the official signed Docker apt repository. Host control uses owner-local uv **0.9.17**, whose official amd64 archive SHA-256 is `0114d54f9aafd07516cf1cadfe72afa970f5fd293fbe82dd924b8a7b42c984d8`, and managed CPython **3.13.11** from that uv release's checksum-bound metadata. Ubuntu's system Python remains unchanged. Record installed OS/kernel, Docker, uv, Python and locked dependency versions. The [plan's pinned upstream sources](../specs/2026-10-08-external-simulation-host-implementation-plan.md#task-3-host-admission-artifacts-and-immutable-releases-u3) explain these choices; package availability is mutable and upgrades require a deliberate reviewed pin update between runs.

Disable disk-backed swap, kernel/process core dumps and terminal recording before credential entry. Verify `swapon --show` is empty, `ulimit -c` is zero in the operator session, and `/proc/sys/kernel/core_pattern` is exactly `|/bin/false`; Docker also applies core limit zero. Host prepare/run require Linux amd64 and a nonroot owner. CI configures these same swap/core settings only on its disposable Ubuntu 24.04 runner so the real Linux admission/signal test runs without bypassing policy; it starts no hosted load. Do not run `script`, record a raw TTY, enable shell tracing around prompts, or retain unsanitized diagnostic transcripts. Docker uses logging driver `none`. Clerk secrets are hidden interactive inputs only; no arguments, environment variables, files or image layers carry them.

Railway credentials exist on the host only during an attended [host operator session](#host-operator-session). During a session, the host holds a Railway login and a registered SSH key. They reach every environment and every service variable in the Railway workspace, and Production too once it exists. Nothing remains on the host outside a session. `railway logout` does not revoke the login, so every session ends with a revoke on the Railway account security page and the removal of the session key. If the host is compromised during a session, revoke all Railway sessions and SSH keys. Then rotate the account and workspace tokens, and every variable that `railway variable list` can read. Production must not be created in this Railway workspace until host sessions are reviewed again, or Production gets its own workspace. The workload container runs as the same Linux user as the session. A separate container user is required before Production shares this workspace.

Keep a private SSH configuration, for example:

```sshconfig
Host tailtag-sim
    HostName <private-inventory-address>
    User tailtag_sim
    IdentityFile <private-key-path>
    IdentitiesOnly yes
    ForwardAgent no
    StrictHostKeyChecking yes
    UserKnownHostsFile <private-known-hosts-path>
```

Verify the host key fingerprint through the provider console or another independently trusted channel before adding it to known_hosts. `ssh-keyscan` alone does not authenticate a key. Protect configuration/key/inventory files with owner permissions. Do not bypass a changed key warning. Bootstrap turns off all forwarding for the owner with `DisableForwarding yes` (TCP, stream-local, agent and X11) and `PermitTunnel no`. TTY access stays on for the host operator session. Runs bind their bridge sockets locally on the host, so no session needs forwarding.

## Immutable release handoff

Use a clean, verified contributor checkout and the locked simulator environment. Build for `linux/amd64` explicitly; source, dependency-lock hash, image ID and packaged files must verify. A dirty relevant source tree cannot produce an attributed release. Record the resulting immutable `sha256:<64hex>` image ID as `IMAGE_ID`; a tag is only a build convenience.

```sh
SIM_REPO_ROOT="$PWD"
task sim-image PLATFORM=linux/amd64
IMAGE_ID="$(docker image inspect --format '{{.Id}}' tailtag-simulator:local)"
umask 077
mkdir -p "$HOME/.local/state/tailtag-host-transfer"
TRANSFER="$HOME/.local/state/tailtag-host-transfer"
task sim-host-release-export IMAGE_ID="$IMAGE_ID" \
  ARCHIVE="$TRANSFER/simulator.tar" RELEASE="$TRANSFER/release.json"
```

After provisioning authorization and key verification, an administrator creates the owner-private host transfer directories in the trusted provider console as root. The existing `tailtag_sim` account must be present before bootstrap:

```sh
install -d -m 0700 -o tailtag_sim -g "$(id -gn tailtag_sim)" \
  /srv/tailtag-simulator /srv/tailtag-simulator/incoming
```

The owner transfers files through ordinary `tailtag-sim` SSH/SCP. Archive and metadata must be owner-only regular files (0600) owned by `tailtag_sim`, as required by bootstrap.

Release metadata is a closed schema-1 object containing only `schema_version`, `simulator_sha`, `dependency_lock_sha256`, `image_id`, `platform`, and `archive_sha256`. Keep the trusted local metadata alongside the archive. Transfer both with authenticated SSH/SCP to an owner-only incoming directory outside source/image. Record the trusted archive hash locally and compare it on the host before Docker loads anything:

```sh
shasum -a 256 "$TRANSFER/simulator.tar"
scp "$TRANSFER/simulator.tar" "$TRANSFER/release.json" tailtag-sim:/srv/tailtag-simulator/incoming/
ssh tailtag-sim 'sha256sum /srv/tailtag-simulator/incoming/simulator.tar'
```

The host's verified release loader independently compares the archive against trusted metadata before `docker load`, then verifies exact image ID, `linux/amd64`, packaged source SHA and dependency-lock hash. Never select execution by a mutable tag. Retain the previous approved immutable image and release metadata; do not prune them as part of the report budget.

Installed image/source verification has a shared 30-second deadline and captures at most 65,536 stdout bytes per external command; stderr is discarded. Its offline source container has a unique `tailtag-sim-source-<UUID>` name, no network, a read-only root, no extra capabilities and no Docker logging. Cleanup targets that exact probe with a separate five-second Docker removal deadline, and interrupted/cancelled verification cancels and joins its owned worker and client processes before returning failure. A preflight interruption or failed verification never launches the named workload. Archive save/load, `/app` copy and locked runtime sync commands each have a 300-second deadline; the stdout cap does not cap archive contents. Newly created copy containers likewise have exact task-owned names and bounded removal.

Initial source transfer runs a fixed stdlib copier inside the verified immutable image, with only the newly created empty owner-private runtime mounted writable. That offline container runs as the owner UID/GID with init, a read-only root, no network, dropped capabilities, no new privileges, no logging and core limit zero. It copies source bytes without following symlinks and omits only the top-level image `.venv`; the host validates copied hashes and paths before normalizing permissions or creating its own locked environment. A failed partial installation remains refused; installation never mounts or overwrites an existing approved release.

The bootstrap's first source probe uses the same finite 30-second/65,536-byte limits and exact named cleanup; it checks copied source hashes before runtime sync. Handled SIGINT/SIGHUP/SIGTERM and async cancellation stop verification and attempt bounded exact-resource cleanup. An unreachable Docker daemon or uncatchable SIGKILL can prevent confirmed removal. Preserve the failed attempt and inspect any remaining task-owned probe/copy containers by their exact names from host Docker inventory before later admission; do not claim cleanup or broadly kill/prune unrelated Docker resources.

The initial control runtime is installed by the secret-free repository-owned `tools/simulator/host/bootstrap.sh`, delivered from the same clean approved maintainer checkout. Hash it locally, transfer over the verified SSH connection and compare the host hash with the trusted local value before running it. Never download or execute a replacement script to work around a failed check.

```sh
shasum -a 256 tools/simulator/host/bootstrap.sh
scp tools/simulator/host/bootstrap.sh tailtag-sim:/srv/tailtag-simulator/incoming/bootstrap.sh
ssh tailtag-sim 'sha256sum /srv/tailtag-simulator/incoming/bootstrap.sh'
```

After comparing the hash with the trusted local value, an administrator executes the verified script in the trusted provider console as root:

```sh
bash /srv/tailtag-simulator/incoming/bootstrap.sh \
  --user tailtag_sim --root /srv/tailtag-simulator \
  --archive /srv/tailtag-simulator/incoming/simulator.tar \
  --metadata /srv/tailtag-simulator/incoming/release.json
```

Bootstrap installs the pinned OS/tools/SSH configuration, verifies archive hash and immutable image ID/platform, verifies packaged provenance inside that image, and copies `/app` into the owner release directory. It performs a standard-library-only `source.json` file-hash check before any locked host dependency sync, then runs the installed venv's `tailtag_simulator.provenance inspect` locally from that release directory. Bootstrap validates clean attribution, simulator SHA, dependency-lock hash and managed Python 3.13.11 from the actual installed runtime; it does not invoke a nested Docker installer. Root setup and nonroot owner runtime installation are distinct; the dedicated owner is in the Docker group and owns `root/tools/uv` and `root/releases/<simulator_sha>`. The simulator container never mounts the Docker socket.

For a later approved release, use the **previous verified release** to run `install-runtime`. Set `PREVIOUS_SIMULATOR_SHA` from the currently approved host release and `NEW_SIMULATOR_SHA` from the newly trusted incoming metadata. The new directory does not exist yet; do not select its Python before installation. This is separate from first-host bootstrap:

```sh
HOST_ROOT=/srv/tailtag-simulator
PREVIOUS_RELEASE="$HOST_ROOT/releases/$PREVIOUS_SIMULATOR_SHA"
HOST_PY="$PREVIOUS_RELEASE/.venv/bin/python"
cd "$PREVIOUS_RELEASE" || exit 1
"$HOST_PY" -m tailtag_simulator.host_release install-runtime \
  --archive "$HOST_ROOT/incoming/simulator.tar" \
  --metadata "$HOST_ROOT/incoming/release.json" \
  --root "$HOST_ROOT" || exit 1
SIMULATOR_SHA="$NEW_SIMULATOR_SHA"
cd "$HOST_ROOT/releases/$SIMULATOR_SHA" || exit 1
HOST_PY="$HOST_ROOT/releases/$SIMULATOR_SHA/.venv/bin/python"
```

`install-runtime` verifies the new trusted archive/source and performs locked no-dev sync. Select the new `SIMULATOR_SHA`, runtime and fresh prepare/run only after installation succeeds. Preserve the previous approved release for rollback; a failed installation does not change the selected release or authorize traffic.

Bootstrap prints the exact installed host Python path and records package/uv/Python versions in `/srv/tailtag-simulator/tools/versions.txt`. Incoming archive/metadata must remain readable by the dedicated owner. No repository clone, GitHub credential, Railway credential or maintainer home directory is transferred. Installation failures prevent host readiness; a local bootstrap review does not establish that installation on an unprovisioned VM succeeded.

## Profiles and run supervision

The checked-in profile wrappers have exactly `scenario_id`, `scenario_version`, `seed`, and `configuration`. They are preparation examples, with pool `host228`: select an already provisioned, approved Staging synthetic pool in a private copy before prepare. Do not edit the manifest after preparation or put pool/credential inventory in the repository.

| Profile | Population | Traffic | Seed |
| --- | --- | --- | ---: |
| `tools/simulator/host/normal-profile.json` | 2 normal + 2 popular owners; 8 casual + 8 active attendees; one fursuit per owner | baseline convention-v2, active mode, ten actors for 300 seconds | 22801 |
| `tools/simulator/host/stop-profile.json` | 1 normal + 1 popular owner; 1 casual + 1 active attendee; one fursuit per owner | baseline convention-v2, active mode, two actors for 120 seconds | 22802 |

The [operations guide](simulation-operations.md#profile-assumptions) lists the further committed cadence profiles: `smoke-profile.json` (`journeys` v1, seed 0, seven identities), the four `nightly-*-profile.json` family profiles, `weekend-profile.json`, and the one-time `expiration-profile.json`. The expiration profile requires `expiration-safety.json`. Host admission accepts that file's raised ceilings only for the closed expiration shape: `convention-baseline` v2, `domain_case: expired`, at most two identities, and up to 46,800 s of execution. Journeys manifests run through the same bridge with a fixed seven-identity partition and the `inspect` reconciliation operation.

Traffic uses existing finite scheduler semantics, so realized starts, concurrency and completion can differ from the target. Both profiles cap ordinary in-flight requests at ten. The normal profile explicitly sets `configuration.limits.attempts=9000`: this is a per-request execution attempt budget, not a ten-requests-per-second target. Its active mode selects ten actors; each journey can issue multiple requests. The approved `limits.generation_seconds=360` includes owner preparation and scheduling overhead around the unchanged 300-second traffic schedule. It is a ceiling, not a six-minute traffic schedule; request and safety budgets are unchanged. `host/safety.json` is a separate safety policy: 900 seconds for setup/execution and 600 seconds shared finalization reserve, 10,000 public execution attempts, 1,000 finalization attempts and at most 50 identities. The five-minute traffic window therefore has setup/drain margin; it is not the entire wall-runtime budget. A reserved control request slot is additional to the ten ordinary requests. Host admission refuses limits beyond 50 identities, ten actors/in-flight requests or 900+600 seconds; health, lease renewals and RPC activity never renew those deadlines.

Shared Staging setup waits asynchronously for four seconds between completed identity attempts, including failed attempts, before the next identity lookup and fresh single-use ticket mint. Each identity receives only one attempt. There is no initial or trailing wait. Twenty identities add 76 seconds of setup waiting; the 300-second workload window, scheduling, request budgets, deadlines, lease TTL and finalization reserve remain unchanged. Host lease renewal continues during the wait, and cancellation, deadline or target veto still stops setup under existing recovery rules. Renewal tolerates up to two consecutive transient heartbeat relay failures and retries each on the next 60 s tick. A third consecutive failure, or a reply that shows a lost lease, ends the run with `FAIL_LEASE`.

The native diagnostic run observed HTTP 429 at `frontend_sign_in` for the final five identities. [Clerk's system limits](https://clerk.com/docs/guides/how-clerk-works/system-limits) document an IP-based frontend limit and a CreateSignIn `/v1/sign_ins` limit of five requests per ten seconds. The simulator uses the legacy `/v1/client/sign_ins` route, so its precise rejecting limiter/window remains unknown. Four-second spacing is a conservative mitigation. Both subsequently authorized native milestones completed setup without a 429; see the [live proof](../specs/2026-10-10-external-simulation-host-staging-proof.md). These observations do not establish the unidentified provider limit or guarantee future admission. A subsequent 429 remains a setup failure and requires targeted provider-limit investigation before another workload.

Each workload runs in a [host operator session](#host-operator-session). `host_operator prepare` verifies the current public Staging identity twice, resolves configuration and safety, validates the release metadata, generates a fresh UUID and writes an owner-only manifest without changing Staging. `host_operator run-local` then runs `host_runner prepare`, binds the run's bridge sockets, runs `host_runner run` as a child process, and resolves the hold with the bridge receipt. A manifest UUID is used once. Each workload needs a fresh `prepare`. The bridge invokes only the fixed pool, fixture and inspection relays. Setup authority is finite: one allocation, one provision attempt, the exact manifest pool, run and index partitions, and bounded inspection and terminal operations. A target mismatch permanently revokes the bridge, including cleanup and release.

`sim-host-release-export` invokes `host_release export --image --archive --metadata`. `sim-host-release-load ARCHIVE=path RELEASE=path` invokes the same verified `load --archive --metadata` implementation on a machine with Docker. `task sim-host-bootstrap-check` checks Bash syntax without running bootstrap, and is part of `task sim-check`.

The Linux runner holds a whole-host exclusive lock through work and evidence finalization, and creates a durable recovery hold before external work. An overlapping invocation or unresolved hold refuses admission; do not steal a lock or kill an unknown process. Hard host/process failure may leave only the last durable snapshot with unfinished fixtures and unreleased or expired leases, so use the exact-run recovery procedure below even after a reboot. Container name is exactly `tailtag-sim-<UUID>`, but supervision identifies the new container by its full 64-character lowercase-hex CID persisted in supervisor-private `control/container.cid`. This must be a fresh Docker-created, single-link owner-only regular file for the current invocation; validated creation proves that invocation owns the CID before metadata inspection. Normal admission and success additionally require Docker inspection to match `Id` to the stored CID, `Name` to `/tailtag-sim-<UUID>`, `Image` to the manifest's immutable image ID, and `Config.Labels["tailtag.run_id"]` to the exact run UUID. Runtime inspection/stats/signals/wait/removal use that owned CID. If initial metadata inspection fails after launch, the supervisor still attempts bounded SIGINT/wait/SIGKILL cleanup of its freshly owned CID and preserves uncertainty with a hold; inspection failure cannot authorize abandoning its Python process. Unknown or missing CID evidence in a name collision grants no container action. The manual stop CLI requires the complete stored-CID/metadata binding before SIGINT; a mismatched persisted manual-stop record grants no action against that container. Its convention invocation uses `--host-manifest /manifest.json --host-socket-dir /bridge` and the manifest family/pool/version/seed. It omits `--config` and `--safety-config`, so the existing CLI consumes the immutable manifest configuration and safety directly; no competing runtime copy is accepted. It runs direct Python with Docker init, nonroot host UID/GID, core limit zero, no restart and no Docker logging. Only `runs/<UUID>/rpc` and the exact control manifest are mounted read-only; only `runs/<UUID>/reports` is writable. Supervisor control, Docker socket, SSH agent and maintainer credential directories are never mounted.

The attached Docker client has its own process session and uses `--sig-proxy=false`, while retaining inherited terminal descriptors for hidden input. The supervisor controls workload signals explicitly by owned CID; terminal process-group HUP cannot bypass graceful SIGINT by Docker's default signal proxy.

The supervisor polls health every five seconds, allowing two seconds per request. Thirty seconds since its last fresh live response permanently latches supervision loss and sends SIGINT to that owned container's Python process. Recovery of health does not resume traffic. Operator SIGINT, SIGTERM or SIGHUP and the execution deadline revoke workload liveness. Terminal recovery remains bounded when transport survives. After finalization allowance plus ten seconds, the supervisor kills only the owned task container and records hard-stop uncertainty; child exit is never proof of remote rollback.

## Host operator session

A host operator session runs an attended run from the host itself. The bridge, the Railway relays and the host runner run as `tailtag_sim` in one tmux session, with no SSH between them. The maintainer can disconnect, and the run continues. The [trust rules](#host-selection-and-private-inventory) above apply.

### One-time setup

Do these steps once, and again after each new release.

1. Make sure that 2FA is on for the maintainer's Railway account.
2. On the host, install go-task 3.53.1 into `/srv/tailtag-simulator/tools/bin`. Check it against the pinned SHA-256 in `.github/actions/install-go-task/action.yml`.
3. On the host, install the latest Railway CLI into `/srv/tailtag-simulator/tools/bin`. Check the download against the SHA-256 that GitHub publishes for that release asset. The CLI updates itself only from a `bin` directory.
4. Append the output of `task --version` and `railway --version`, and the SHA-256 of each binary, to `/srv/tailtag-simulator/tools/versions.txt`. Bootstrap rewrites that file, so append them again after any bootstrap.
5. On the host, install the selector manifest at `~/.config/tailtag/staging-clean-rebuild-targets.json` with mode 0600. It holds only the five `rebuild_*` identifiers that `validate_selectors` reads. Copy those keys from the maintainer's own manifest, and no others.
6. On the Mac, create the workspace archive from a clean checkout of the installed release SHA:

   ```sh
   git archive --format=tar.gz -o "$TRANSFER/workspace.tar.gz" "$SIMULATOR_SHA"
   shasum -a 256 "$TRANSFER/workspace.tar.gz"
   ```

7. Copy the archive to `/srv/tailtag-simulator/incoming/` with scp. On the host, install the workspace from the release directory:

   ```sh
   HOST_ROOT=/srv/tailtag-simulator
   cd "$HOST_ROOT/releases/$SIMULATOR_SHA" && .venv/bin/python -m tailtag_simulator.host_release install-operator \
     --archive "$HOST_ROOT/incoming/workspace.tar.gz" --archive-sha256 "$ARCHIVE_SHA256" \
     --source-sha "$SIMULATOR_SHA" --root "$HOST_ROOT"
   ```

   The command makes sure that the archive digest matches and that the SHA names an installed release. It extracts into `operator/<sha>` with private modes, then runs a locked `uv sync` of `services/api`. Any failure leaves no workspace.

8. On a host bootstrapped before forwarding was turned off, apply the new sshd policy once from the trusted provider console as root. Bootstrap writes the same file on a new host.

   ```sh
   printf 'Match User %s\n    DisableForwarding yes\n    PermitTunnel no\n    PermitTTY yes\nMatch all\n' tailtag_sim > /etc/ssh/sshd_config.d/90-tailtag.conf
   sshd -t && systemctl reload ssh
   ```

   If `sshd -t` fails, do not reload. Report the error.

### Session start

Run these steps in order, in a new SSH login as `tailtag_sim`. Do not start a session unless railway.com is reachable from a second device, because the dashboard is the [kill switch](#kill-switch).

1. Run `tmux new-session -s operator`. Do not use tmux `pipe-pane` or any session logging.
2. Run `umask 077`, and turn off shell history with `set +o history`.
3. Make sure that `swapon --show` is empty, `ulimit -c` is 0, and `/proc/sys/kernel/core_pattern` is `|/bin/false`.
4. Make sure that systemd-logind `KillUserProcesses` is false, so tmux survives an SSH logout.
5. Choose the key location. Create an owner-only test file in `/dev/shm`, detach tmux, log out of SSH, log in again and reattach. If the file is still there, keep the key in `/dev/shm`. If it is gone, keep the key in the owner-only workspace instead, and remove it with `shred -u` at session end.
6. Run `export PATH="/srv/tailtag-simulator/tools/bin:$PATH"`. Then run `railway upgrade`, and record `railway --version` and the SHA-256 of the `railway` binary.
7. Run `export RAILWAY_NO_AUTO_UPDATE=1`. Make sure that `railway autoupdate status` reports disabled, and that `~/.railway/staged-update` and `~/.railway/backups` do not exist.
8. Generate an ed25519 key with the comment `tailtag-sim-<date>` in the chosen location.
9. Add a `Host ssh.railway.com` block to `~/.ssh/config` with `IdentityFile` set to that key, `IdentitiesOnly yes`, `ForwardAgent no` and `StrictHostKeyChecking yes`.
10. Make sure that the `ssh.railway.com` host key fingerprint equals the recorded value `SHA256:+S1xg92FrnHz6pY3bpkmh1OGtWQGNANXilPzlxA7B1g`.
11. Run `railway login --browserless`, and enter the pairing code from the Mac. Make sure that `stat -c %a ~/.railway/config.json` prints `600`.
12. Run `railway ssh keys list` and record the output. Remove any leftover `tailtag-sim-*` key by its exact name. The `tailtag-sim-` prefix is reserved for session keys.
13. Link the key pair into `~/.ssh/`, because the Railway CLI looks for keys only there and in the SSH agent. Run `ln -s <key> ~/.ssh/tailtag-sim-session` and `ln -s <key>.pub ~/.ssh/tailtag-sim-session.pub`. The key bytes stay in the chosen location.
14. Run `railway ssh keys add --key ~/.ssh/tailtag-sim-session.pub --name tailtag-sim-<date>`.

### Running a workload

Prepare and run each workload from the release directory. The workspace holds the committed profiles with private modes.

```sh
HOST_ROOT=/srv/tailtag-simulator
RELEASE_DIR="$HOST_ROOT/releases/$SIMULATOR_SHA"
WORKSPACE="$HOST_ROOT/operator/$SIMULATOR_SHA"
STATE="$HOST_ROOT/operator-state"
install -d -m 0700 "$STATE" "$STATE/manifests"
cd "$RELEASE_DIR"
.venv/bin/python -m tailtag_simulator.host_operator prepare \
  --profile "$WORKSPACE/tools/simulator/host/smoke-profile.json" \
  --safety-config "$WORKSPACE/tools/simulator/host/safety.json" \
  --release "$RELEASE_DIR/release.json" --output "$STATE/manifests/smoke-1.json"
.venv/bin/python -m tailtag_simulator.host_operator run-local \
  --manifest "$STATE/manifests/smoke-1.json" --host-root "$HOST_ROOT" \
  --workspace "$WORKSPACE" --tools "$HOST_ROOT/tools" --state-dir "$STATE"
```

`run-local` refuses to start unless `RAILWAY_NO_AUTO_UPDATE` is `1` and stdin and stdout are terminals. It also refuses unless the workspace and the tools are complete. It writes `<UUID>.used.json` and `<UUID>.bridge.json` in the state directory, and `sim-host-collect` copies them with the run. Enter the Clerk Staging secret at the hidden prompt. Each workload needs a fresh `prepare` and a new manifest.

### Session end

The session end is mandatory after any exit, including a crash or a reboot.

1. If the shell is new, for example after a reboot, run `umask 077`, `export PATH="/srv/tailtag-simulator/tools/bin:$PATH"` and `export RAILWAY_NO_AUTO_UPDATE=1` before any `railway` command.
2. Run `railway ssh keys remove`, and choose the session key by its exact name.
3. If the private key still exists, run `shred -u` on it. Remove the public key.
4. Remove the `Host ssh.railway.com` block from `~/.ssh/config`, and run `rm -f ~/.ssh/tailtag-sim-session ~/.ssh/tailtag-sim-session.pub`.
5. Run `railway logout`, then `rm -rf ~/.railway`.
6. Revoke the host's CLI session on the Railway account security page (railway.com/account/security). Logout alone leaves the login valid on Railway's side.
7. On the Mac, run `railway ssh keys list`. Make sure that no `tailtag-sim-*` key remains.

### Kill switch

To stop a session's privileged authority from anywhere, revoke the host's CLI session and remove its key on railway.com. Every relay then fails with `FAIL_LAUNCHER`. The run fails with `FAIL_LEASE` after three failed heartbeats, and its hold stays in place. If the relays fail fast, this takes about three minutes. If they hang until the 180 s launcher timeout, it takes up to about twelve minutes. Recover the held run from the Mac with the [recovery procedure](#recovery-and-refusal-handling). With access to the host, reattach tmux and press Ctrl-C, or use the controlled stop below.

## Observation and controlled stop

For the authorized normal run, observe host Docker CPU/memory and Linux CPU steal, report realized active/in-flight peaks and scheduling lag, and observe existing Staging Railway/Sentry evidence. The companion samples CPU/memory percentages and the cumulative Linux CPU-steal tick counter; retain its actual units, rather than label raw ticks a percentage. Record offered/admitted/skipped/completed work from the report alongside these observations. Record unavailable evidence explicitly; automated backend saturation monitoring is unavailable. Generator saturation or resource failure requires investigation and separate resizing authorization before larger work. Do not equate an offered actor count or a single VM run with backend capacity.

For the separately authorized small stop run, prepare `stop-profile.json` into a new manifest and have a second SSH session ready before you start `run-local`. Interrupt promptly after setup with Ctrl-C in the operator tmux pane, or with the host stop command. Do not wait for a chat response during the finite traffic window. In that new host session, set `SIMULATOR_SHA` and canonical `RUN_ID` from the original trusted manifest, then establish the release cwd and absolute Python explicitly:

```sh
HOST_ROOT=/srv/tailtag-simulator
cd "$HOST_ROOT/releases/$SIMULATOR_SHA" || exit 1
HOST_PY="$HOST_ROOT/releases/$SIMULATOR_SHA/.venv/bin/python"
"$HOST_PY" -m tailtag_simulator.host_runner stop \
  --root /srv/tailtag-simulator --run-id "$RUN_ID"
```

SIGINT uses the existing `interrupted`, nonzero report semantics. The watchdog records `supervision_lost` in companion evidence, not as a new schema-4 abort reason. For an observed resource-saturation event, explicitly request the existing resource abort instead. In a trusted host session, set `RUN_ID` and `IMAGE_ID` from the original manifest, verify supervisor-private CID-file ownership/mode/link count, then verify the exact Docker tuple before sending SIGUSR1 to that CID:

```sh
HOST_ROOT=/srv/tailtag-simulator
CID_PATH="$HOST_ROOT/runs/$RUN_ID/control/container.cid"
test ! -L "$CID_PATH" || exit 1
test "$(stat -c '%a:%u:%h:%F' "$CID_PATH")" = "600:$(id -u):1:regular file" || exit 1
CID="$(cat "$CID_PATH")" || exit 1
[[ "$CID" =~ ^[0-9a-f]{64}$ ]] || exit 1
ACTUAL="$(docker inspect --format '{{.Id}} {{.Name}} {{.Image}} {{index .Config.Labels "tailtag.run_id"}}' "$CID")" || exit 1
test "$ACTUAL" = "$CID /tailtag-sim-$RUN_ID $IMAGE_ID $RUN_ID" || exit 1
docker kill --signal=USR1 "$CID"
```

Use only the canonical UUID and immutable image ID from the trusted manifest; if any CID-file or tuple check fails, keep the manual hold and investigate rather than signal by name. SIGUSR1 must reach Python through init and records `resource_saturation`; it is distinct from manual interruption and does not measure saturation. Keep the relevant resource observation separately. Neither stop mode can produce a passing workload report. Wait for bounded finalization and inspect acknowledged fixture/session/lease recovery before another workload. Every failed, interrupted or otherwise nonzero runner keeps its manual recovery hold, even when the bridge acknowledged release; complete the exact-run manual checks and resolution below before a new run.

## Recovery and refusal handling

An attempted identity that fails during SETUP emits one bounded diagnostic line:

```text
DIAG setup index=15 step=frontend_sign_in failure=http status=429 elapsed=lt_1s
```

The index is the leased pool slot, not a provider identity. Steps and failure categories are fixed labels; HTTP status is a bounded number or `none`, and elapsed time is a coarse monotonic bucket (`lt_1s`, `lt_5s`, `lt_10s`, `ge_10s`, or `unknown`). A nested token failure keeps its token-step attribution. Diagnostics contain no credentials, provider IDs, URLs, response bodies, headers or exception text. Diagnostics themselves do not retry a ticket or request or establish recovery authority; setup pacing is the separate fixed wait described above. An unknown result remains unknown; use the observed failing step to investigate before another workload. Successful or unattempted identities emit no diagnostic.

A report PASS, validated report, clean-looking pool, expired lease, process exit or old hold timestamp cannot clear a recovery hold. Allocation/provision attempts are reserved before dispatch; a lost acknowledgement may mean the remote operation committed. Never retry allocation/provision on the same session or race cleanup/retention/release against a mutation that may still commit. Preserve uncertainty and settle the exact run manually. A pinned-target mismatch requires investigation before any further TailTag recovery action; do not substitute the new deployment tuple for the original receipt.

From the maintainer's existing trusted environment, independently verify current Staging `/health/identity` using the target check and compare its exact source/deployment/environment tuple with the held manifest. Existing relays independently verify provider and deployed target too. Confirm all bridge-owned mutating operations have settled remotely, including any indeterminate provision. Preserve report/companion evidence and inspect the exact retained/unfinished run, then use the existing commands:

```sh
task sim-retained
task sim-pool-status POOL="$POOL"
task sim-cleanup POOL="$POOL" RUN_ID="$RUN_ID"
task sim-pool-status POOL="$POOL"
```

Set `POOL` and canonical `RUN_ID` from the original trusted manifest before these commands, not an assumed example value. `sim-cleanup` accepts retained/provisioned runs and readmits the run's quarantined identities only after verified clean. It does not accept a cleaned/failed row; do not reinterpret that refusal as proof that a lost provision never committed. `FAIL_ATTRIBUTION`, `FAIL_VERIFY`, `FAIL_TARGET`, `FAIL_STORAGE`, `FAIL_LIMIT` or other failure requires investigation, not host hold removal. After storage failure the documented exact-run cleanup may be retried; setup authority remains closed. Existing independent Clerk session closure must also be acknowledged or uncertainty retained.

Set `REPAIRED_INDEX` only from the exact-run verified repair record. Only if an identity remains independently quarantined after verified repair/cleanup, use the existing explicit per-index recovery and recheck pool status:

```sh
task sim-pool-readmit POOL="$POOL" INDEX="$REPAIRED_INDEX"
task sim-pool-status POOL="$POOL"
```

Readmission alone removes no fixtures and cannot establish cleanup. Review the [existing cleanup failure/recovery semantics](../../tools/simulator/README.md#run-lifecycle) before this step.

Completion is deliberately two-phase. The attached runner can exit 0 only with a present schema-valid report whose exact run, clean simulator/lock attribution and pinned backend identity match the manifest and whose `outcome` is `passed`; container exit 0 alone cannot pass. Missing, malformed, misattributed or nonpassing evidence makes the runner fail and preserves its hold. It records available validated completion evidence in `runs/<UUID>/host.json` and leaves `recovery-hold.json` in place. For nonpassing runs, report target identity differences do not discard host evidence: `evidence.report_attribution` is `matched` when both starting and safety identities match the manifest, `mismatched` when both are available but either differs, and `unavailable` when either identity or the report is absent. Report schema, exact run and clean simulator/lock attribution remain mandatory when a report is present; validation or storage failure may leave only the last durable snapshot, manifest and hold. After the runner child exits, `run-local` revokes workload authority, joins its owned mutations, fsyncs `<UUID>.bridge.json` in the operator state directory, and derives the trusted recovery receipt. Only after runner exit 0 does it send a `released` or `no_mutation` receipt on stdin to a local `host_runner recovery-resolve --root ABSOLUTE_PATH --run-id UUID --receipt -`. Host resolution records `control/recovery.json` and clears only the exact matching hold. Outer operator exit 0 requires runner exit 0, no operator interruption/deadline breach, settled bridge recovery and a successful separate resolution exit 0. A runner exit 0 or passing report alone is insufficient. Failed/interrupted/nonzero runners retain a manual hold even if the bridge receipt says `released`; automatic receipt resolution is not attempted for those outcomes.

The trusted receipt's exact shape is `{schema_version:1, run_id, backend_identity, disposition}`. `released` derives only from acknowledged bridge lease release; `no_mutation` only when no mutating dispatch started; every unresolved case is `held`. The UUID and backend tuple must match the original manifest. The simulator's report/RPC reply cannot supply this authority, and the container never mounts the receipt directory.

For manual resolution, after the original target and exact-run recovery checks above have established settled fixture/session/lease state, the maintainer explicitly prepares an owner-private receipt tied to that original tuple, transfers it by verified SSH into the run's supervisor-only control directory, and resolves only that run. In this separate host session, set `SIMULATOR_SHA` and canonical `RUN_ID` from the original trusted manifest and establish its release cwd/Python again:

```sh
HOST_ROOT=/srv/tailtag-simulator
cd "$HOST_ROOT/releases/$SIMULATOR_SHA" || exit 1
HOST_PY="$HOST_ROOT/releases/$SIMULATOR_SHA/.venv/bin/python"
"$HOST_PY" -m tailtag_simulator.host_runner recovery-resolve \
  --root /srv/tailtag-simulator --run-id "$RUN_ID" \
  --receipt "/srv/tailtag-simulator/runs/$RUN_ID/control/recovery.json"
```

`--receipt PATH` reads an owner-private file; `--receipt -` reads bounded JSON from trusted stdin. Automatic delivery uses stdin after runner completion and never asks the container for a receipt. For manual file delivery, copy only the maintainer-validated receipt into the supervisor control directory and run the command as its owner. Do not fabricate `no_mutation` from absence of a report or `released` from a lease timeout. Missing, mismatched, held or unacknowledged recovery evidence preserves the hold. Investigate retained/unfinished state, acknowledge verified cleanup and lease/session settlement, finalize evidence, and only then admit a new UUID. Do not delete holds by hand or automatically resolve them at startup.

Invalid profile/manifest/release, reused UUID, unsafe/symlinked/foreign paths, missing hidden TTY, unverified host key, target mismatch, overlap, recovery hold or inadequate storage all refuse execution. Capacity/privileged-operation exhaustion, supervision loss, stage/report write failure and safety stops cannot produce PASS. Read only sanitized stage/companion output; do not enable raw diagnostics to work around a refusal.

## Artifacts, retrieval and maintenance

Owner-only run directories contain `runs/<UUID>/reports/<UUID>.json`, fixed sanitized `runs/<UUID>/reports/stages.log` (at most one MiB), and supervisor-owned `runs/<UUID>/host.json`. `control/manifest.json`, `control/recovery.json`, `control/container.cid` and `recovery-hold.json` stay outside the container-writable report mount. The runner also writes a non-authoritative `runs/<UUID>/control/health.json` (per-check health counts, longest gap between live replies and the last 64 failed checks) for any run that reached supervision; read it over ssh when diagnosing a `supervision_lost` stop. It is not part of `host.json` and is not collected, and a failure to write it changes no outcome. The operator's local `<state>/<UUID>.bridge.json` records the bridge's own `health` counters and the first `revocation` cause. Its `heartbeat` field records failed heartbeats as non-authoritative diagnostics. Reports/companion are retained 30 days and stage logs seven days, so collect evidence at least every six days. The aggregate report/log/companion budget is one GiB; each admitted run reserves 32 MiB within both that budget and free filesystem space. During execution, budget/write failures stop work and prevent PASS. Only expired completed-run artifacts are pruned. Active or recovery-held evidence is never pruned or used as expendable storage; resolve its hold explicitly. When admission is storage-blocked, the maintainer owns hash-verified export and exact-run recovery; prune only eligible expired completed evidence, then rerun admission. Do not delete held/live evidence or expand the paid host automatically. Images and rollback releases have their separate lifecycle.

For routine operation, `task sim-host-collect HOST=tailtag-sim HOST_ROOT=/srv/tailtag-simulator RELEASE=path ARCHIVE=path` runs a read-only `host_runner inventory` on the host, copies every settled, not-yet-collected run with size and SHA-256 verification, validates and evaluates it, and never writes to the host or resolves holds; see the [operations guide](simulation-operations.md#collection-and-evaluation). The manual procedure below remains valid for a single run.

Retrieve selected evidence through verified SSH to an owner-private maintainer archive. Enumerate exact files for the selected UUID; do not copy runtime credential/configuration directories. Capture a SHA-256 inventory on the host, transfer those same report/stage/companion files, and verify hashes locally. For example, after verifying the original canonical UUID and filenames:

```sh
ssh tailtag-sim "sha256sum /srv/tailtag-simulator/runs/$RUN_ID/reports/$RUN_ID.json /srv/tailtag-simulator/runs/$RUN_ID/reports/stages.log /srv/tailtag-simulator/runs/$RUN_ID/host.json"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/reports/$RUN_ID.json" "$TRANSFER/"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/reports/stages.log" "$TRANSFER/"
scp "tailtag-sim:/srv/tailtag-simulator/runs/$RUN_ID/host.json" "$TRANSFER/"
shasum -a 256 "$TRANSFER/$RUN_ID.json" "$TRANSFER/stages.log" "$TRANSFER/host.json"
task sim-report-validate REPORT="$TRANSFER/$RUN_ID.json"
```

Keep each milestone in its own owner-private archive directory with original manifest, release metadata, hash inventory and bounded observations; avoid overwriting another run's `host.json`. Validate using the recorded simulator revision/release, rather than assuming the current validator is compatible. Preserve original reports when rolling back.

Patch Linux/Docker and deliberately update pins only between runs after all workload processes end and holds are investigated. Record old/new installed versions and reverify host prerequisites and offline wiring before the next authorized live run. For rollback, select the previous approved immutable image/release, verify its original archive/source/lock/platform again, use its matching host runtime, then prepare a fresh manifest. Do not retag a running workload, reopen its manifest, overwrite its reports, or remove the retained previous image as general cleanup.

## Backend context for performance evaluation

Use this after a normal run, once its report and `host.json` have been retrieved
into the milestone archive. Evaluation is offline. Run it on the maintainer machine
from a checkout of the merged simulator, not on the host:

```bash
task sim-report-evaluate REPORT="$ARCHIVE/<run-uuid>.json" \
  HOST_COMPANION="$ARCHIVE/<run-uuid>/host.json" CONTEXT="$ARCHIVE/<run-uuid>.context.json"
```

The companion turns the execution context into `external_host:linux/amd64` and
supplies peak Docker CPU and memory and the CPU-steal tick delta, in their recorded
units.

A companion that records a stop, a hard stop, a non-zero container exit, or an
unmatched report attribution makes the evaluation `not_evaluated`. Keep the
companion exactly as written; never edit it to change that result.

Before evaluating, the operator may fill in the optional context file. Use the
evaluation window printed in the summary, which is the report's UTC start and end.
Filter by the report's backend `source_sha` and the Sentry release, and record one
closed value per signal:

| Signal | Where to look | Reference |
| --- | --- | --- |
| `http_5xx` | `tailtag.http.server.requests` with `http.response.status_class` `5xx`, by `http.route` | [service signals](backend-service-signals.md) |
| `server_latency` | Sentry trace p95 by transaction for the routes in the simulator README's operation table | [service signals](backend-service-signals.md) |
| `db_connections` | `tailtag.db.connection.attempts` outcomes and `tailtag.db.connection.duration` p95 | [dependency health](backend-dependency-health.md#postgresql) |
| `worker_timeouts` | `WORKER TIMEOUT` or `SIGKILL` lines from `gunicorn.error` in Railway logs | [runtime failures](backend-service-signals.md#runtime-failures) |
| `restarts_or_oom` | Railway deployment events: restarts, redeploys, out-of-memory kills | [dependency health](backend-dependency-health.md#runtime-resources) |
| `runtime_resources` | Railway API service CPU and memory graphs for the window | [dependency health](backend-dependency-health.md#runtime-resources) |
| `domain_outcomes` | #213 outcome counts, such as `tailtag.catches.confirmation` rejected by `tailtag.reason` | [domain outcomes](backend-domain-outcomes.md) |

Use `observed_pressure` only for evidence of saturation or failure inside the
window, `observed_normal` when the signal was checked and looked ordinary, and
`not_observed` when it was not checked or not available. The file contains no
free text, links or screenshots. Keep any screenshots in the private archive,
separate from the file. The context helps readers tell an application or domain
failure apart from database or runtime pressure. It never changes the verdict.
Sentry traces are sampled, so the simulator's own latency remains the primary
measurement.

Promote a reviewed run with `task sim-baseline-promote`, as described in the
simulator README. Promotion takes effect only through a reviewed pull request.
Never promote from the host.

## Hybrid replica sessions

This section runs the simulator against the hybrid replica of [#359](https://github.com/TailTag-Game/tailtag/issues/359). The replica is an isolated copy of Staging on Cloud Run and Neon. The [replica trust runbook](../development/hybrid-replica-trust.md) gives its identities and its compromise steps. Placeholders such as `<PROJECT_ID>` have the meanings in the [provisioning runbook](../development/hybrid-replica-provisioning.md#placeholders). `<REPLICA_HOST>` is the private `run.app` host of the replica service.

Every live step needs owner approval, one step at a time. A replica session never uses Railway. The relays run the pinned Cloud Run jobs as `tt-simrelay`, with a short-lived token.

### Replica session setup

Do the first two steps on the Mac:

1. Make sure that the `tt-simrelay` account, its job bindings and the `simrelay-job-results` view exist, as the trust runbook IAM readback shows.
2. Mint a token for this session. It lasts 1 hour, so mint a new one for each workload:

   ```sh
   gcloud auth print-access-token --impersonate-service-account=tt-simrelay@<PROJECT_ID>.iam.gserviceaccount.com
   ```

Then, on the host, as `tailtag_sim`:

1. Do steps 1 to 5 of the [session start](#session-start). Skip every Railway step.
2. Make a private folder in the chosen key location, for example `install -d -m 0700 /dev/shm/tailtag-replica`.
3. Write the session file with the project and the host:

   ```sh
   umask 077
   printf '{"project": "%s", "host": "%s"}\n' '<PROJECT_ID>' '<REPLICA_HOST>' > /dev/shm/tailtag-replica/session.json
   ```

4. Enter the token at a hidden prompt and write it to the token file:

   ```sh
   read -rs TOKEN && printf '%s\n' "$TOKEN" > /dev/shm/tailtag-replica/token && unset TOKEN
   ```

5. Export both paths:

   ```sh
   export TAILTAG_REPLICA_SESSION_FILE=/dev/shm/tailtag-replica/session.json
   export TAILTAG_REPLICA_TOKEN_FILE=/dev/shm/tailtag-replica/token
   ```

`run-local` checks that the session host equals the manifest host. It does not check the project. Copy the project ID from the owner-private setup record exactly.

### Running a replica workload

Use the profiles in `tools/simulator/host/replica/`. They use the pool `replica1`. Pass the newest promoted release receipt in the workspace. Prepare refuses an older one.

```sh
RECEIPT="$WORKSPACE/docs/development/replica-deployments/<RUN_ID>-<RUN_ATTEMPT>.json"
.venv/bin/python -m tailtag_simulator.host_operator prepare \
  --profile "$WORKSPACE/tools/simulator/host/replica/normal-profile.json" \
  --safety-config "$WORKSPACE/tools/simulator/host/safety.json" \
  --release "$RELEASE_DIR/release.json" --output "$STATE/manifests/replica-normal-1.json" \
  --replica-session "$TAILTAG_REPLICA_SESSION_FILE" --receipt "$RECEIPT"
.venv/bin/python -m tailtag_simulator.host_operator run-local \
  --manifest "$STATE/manifests/replica-normal-1.json" --host-root "$HOST_ROOT" \
  --workspace "$WORKSPACE" --tools "$HOST_ROOT/tools" --state-dir "$STATE"
```

Prewarm the replica right before `run-local`, and record the UTC time when the request returns. The run's warm results count only from a prewarmed start:

```sh
curl -fsS -o /dev/null https://<REPLICA_HOST>/health/ready && date -u +%Y-%m-%dT%H:%M:%SZ
```

The burst profile uses `tools/simulator/host/replica/burst-safety.json`. Enter the secret key of the replica Clerk application at the hidden prompt. `run-local` refuses to start unless both relay files are owner-only and the session host matches.

### Replica ladder

Run the steps in this order. Each step needs its own owner approval of target, profile, seed, ceilings and UTC window.

| Step | Profile | Purpose |
| --- | --- | --- |
| R0 | None. A pool of 3 with one fixture provision, inspection and cleanup | First relay round trip. It also closes #355 AC6. |
| R1 | `replica/journeys-profile.json` | Journeys correctness with 7 identities |
| R2 | `replica/normal-profile.json`, twice | Warm latency, errors and throughput at the baseline load |
| R3 | `replica/soak-profile.json` | Longer load at the soak rate |
| R4 | `replica/hotspot-profile.json`, then `replica/retry-profile.json` | Hotspot and retry shapes |
| R5 | `replica/burst-profile.json` with `replica/burst-safety.json` | The 2x burst |
| Cold | Cold probe, below | Cold start in three states |

Stop rules:

- Any correctness failure or recovery hold stops the ladder.
- From R3 on, a step needs the step before it to pass correctness and an error rate of 1% or less.
- A latency miss does not block a step of the same size, but it blocks R5.

After R0 passes, grow the pool to 20 with an approved `register` request. Before R5, grow it to 40 the same way.

### Quiet window and cold probe

A quiet window is a period with no traffic and no probes. It lasts at least 30 minutes. Read its state only from the control planes, on the Mac, with the owner `gcloud` login and `NEON_API_KEY` in the token terminal:

```sh
task replica-idle-state -- --project <PROJECT_ID> --neon-project <NEON_PROJECT_ID> state
```

The output gives the Cloud Run instance count by state and the Neon compute state. In the first window, read it twice, one minute apart, and make sure that `suspended_at` does not change. Before each window, record the possible blockers: Sentry uptime monitors, Cloud Scheduler jobs, job runs and open database sessions.

The cold probe runs on the host from the release directory. It sends single requests with no credentials. It claims its output file before any request, so make the folder first:

```sh
install -d -m 0700 "$STATE/cold"
.venv/bin/python -m tailtag_simulator.cold_probe --replica-session "$TAILTAG_REPLICA_SESSION_FILE" \
  --state both-cold --idle-seconds 1800 --output "$STATE/cold/both-cold-1.json"
```

Set up each state like this:

- `both-cold`: wait at least 20 minutes after the last request. The state reading shows 0 active and 0 idle instances, and an idle Neon compute. An idle instance is still warm, so it does not count as cold.
- `database-cold`: send one request that wakes only the service, because `/health/live` does not use the database: `curl -fsS -o /dev/null https://<REPLICA_HOST>/health/live`. Then suspend the Neon compute with the Neon API. Wait until the state reading shows the compute idle and at least 1 instance.
- `app-cold`: wait until the state reading shows 0 active and 0 idle instances. Then start the Neon compute with the Neon API, and wait until the state reading shows it active.

Right before each sample, take one state reading and save its line next to the sample record. That line is the state before the request.

The Neon API calls take the endpoint ID from the Neon console. `-o /dev/null` keeps the response, which names the host and IDs, out of the terminal:

```sh
curl -fsS -o /dev/null -X POST -H "Authorization: Bearer $NEON_API_KEY" https://console.neon.tech/api/v2/projects/<NEON_PROJECT_ID>/endpoints/<ENDPOINT_ID>/suspend
curl -fsS -o /dev/null -X POST -H "Authorization: Bearer $NEON_API_KEY" https://console.neon.tech/api/v2/projects/<NEON_PROJECT_ID>/endpoints/<ENDPOINT_ID>/start
```

Each record gives each request's outcome and latency, and whether the first request finished within 5 seconds. A miss is a FAIL result, not a stop condition. Take 3 samples for `both-cold` and 5 each for the other states.

### Replica backend context and cost

Fill in the backend context file with these replica sources. A signal with no source is `not_observed`.

| Signal | Replica source |
| --- | --- |
| `http_5xx` | Cloud Monitoring `run.googleapis.com/request_count` with `response_code_class` `5xx`, checked against the Cloud Logging request lines |
| `server_latency` | Cloud Monitoring `run.googleapis.com/request_latencies`, or Sentry if #358 has wired it |
| `db_connections` | Neon monitoring view: connections count, and deadlocks as the sign of transaction contention |
| `worker_timeouts` | `not_observed`. The replica runs Gunicorn with `--timeout 0`, so Cloud Run owns request timeouts. |
| `restarts_or_oom` | Cloud Logging container start and exit lines for the service |
| `runtime_resources` | Cloud Monitoring `container/cpu/utilizations`, `container/memory/utilizations` and `container/instance_count` |
| `domain_outcomes` | Cloud Logging structured outcome lines of the service |

Record each run's cost as an estimate. Right before the run, read the Neon counters on the Mac:

```sh
task replica-idle-state -- --project <PROJECT_ID> --neon-project <NEON_PROJECT_ID> neon
```

At least 5 minutes after the run ends, read the usage for the run window. Monitoring points can arrive up to 3 minutes late, so an earlier reading undercounts:

```sh
task replica-idle-state -- --project <PROJECT_ID> --neon-project <NEON_PROJECT_ID> \
  usage --start <RUN_START> --end <RUN_END>
```

The output gives the service and the relay jobs apart, because jobs bill as Cloud Run jobs. The Neon counters are totals for the Neon period, so the run's use is the difference between the two readings. Neon calls these counters usage, not billing. Multiply by the list prices in the proof. Later, compare the estimates with the monthly bill, using the #344 method.

### Replica session end and kill switch

At session end, run `shred -u` on the token and session files, remove the folder, and unset both variables. The token expires within 1 hour in any case.

To stop the relays from anywhere, disable `tt-simrelay`, as the trust runbook compromise steps say. Every relay then fails with `FAIL_LAUNCHER`. The run fails with `FAIL_LEASE` after three failed heartbeats, and its hold stays in place. Recovery needs the relays again, so enable the account and mint a new token only after the cause is clear.

## External acceptance record

Keep preparation/offline evidence separate from live evidence. An authorized live milestone needs:

- Provider evidence that this exact host matches the approved RIC1 v5 override (2 vCPU/4 GiB/30 GiB, US$0.052/hour, with a US$40/month before-tax operating budget), plus installed OS/runtime/package versions and SSH/firewall/swap/core/logging checks.
- The verified immutable image ID, `linux/amd64`, simulator SHA, lock/archive hashes, prepared UUID/configuration/safety, and actual pinned backend source SHA/deployment/environment.
- Public DNS resolution, TLS certificate/hostname verification and actual public peer address evidence from the host. Correlate bounded observation with the run; a maintainer-side probe alone cannot prove container traffic used public ingress. Record provider/region/backend identity without publishing private account or billing identifiers.
- The five-minute/20-identity run's versioned report and companion with CPU, memory, CPU steal, realized concurrency and scheduling-lag evidence, plus backend observations or explicit unavailable status.
- A separate small manual-interrupt run, nonzero/interrupted report, bounded finalization and acknowledged fixture/session/lease recovery; no resumption or overlapping workload.
- Trusted terminal receipts or documented exact-run manual recovery, pool/retained checks, any holds/uncertainty, and hash-verified SSH retrieval into the maintainer's milestone archive.

Current checkpoint (2026-10-10 UTC): the [native Staging proof](../specs/2026-10-10-external-simulation-host-staging-proof.md) records the passed twenty-identity five-minute normal run, a separate intentional interrupt, public connections observed in that stop container, and acknowledged exact-run recovery. All twenty identities are available, with no leases, quarantine, retained/unfinished fixtures, host holds or task containers remaining. Original failed/interrupted evidence is preserved. Plan class, included transfer, usage/overage and project/billing ownership still require private provider confirmation before issue closeout; no new live workload is needed for these completed milestones.
