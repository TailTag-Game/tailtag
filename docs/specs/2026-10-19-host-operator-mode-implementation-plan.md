# Implementation plan: host operator mode

Implements #316 AC7 to AC11 and the AC6 security conditions C1 to C9. The source of truth is the approved refinement and its amendments on [#316](https://github.com/TailTag-Game/tailtag/issues/316). The branch is `issue-316-host-operator-mode`. Delivery is one pull request, "Part of #316".

Host operator mode runs an attended session on the external host. The bridge, the Railway relays and the host runner run on one machine, with no SSH between them. The maintainer starts the session in tmux over an ordinary SSH login. The Mac operator mode stays until the live proof in PR 3 (AC13).

## Facts that shape the design

- The relays run `task -s api-sim-*-ssh` with the working directory `Path(__file__).resolve().parents[3]` (`host_bridge.py:103-112`). On the host, this resolves to `/srv/tailtag-simulator`, which has no `Taskfile.yml` and no `services/api`.
- The relays use `uv` from the `UV` variable or `PATH`, and `railway` from `PATH` (`Taskfile.yml:13`, `216-235`). They read the selector manifest at `~/.config/tailtag/staging-clean-rebuild-targets.json` (`services/api/config/replacement_target_binding.py:29-31`).
- `BridgeServer` binds both sockets in one directory (`host_bridge.py:599-638`). Local mode needs `runs/<UUID>/rpc/rpc.sock` and `runs/<UUID>/control/health.sock`. `host_runner prepare` creates both parent directories with mode 0700.
- `host_runner run` polls `control/health.sock` from its first loop and stops after 30 s without a live reply (`host_runner.py:440`). It never waits for the sockets, so the bridge must bind them before `run` starts.
- `host_runner run` handles SIGINT, SIGTERM and SIGHUP itself. It starts Docker in a new session with `--sig-proxy=false` (`host_runner.py:265-267`, `333`, `371`). It adds `--tty` only when its own stdin and stdout are terminals (`host_runner.py:338`). The container's Clerk prompt needs that terminal (`__main__.py:73-80`).
- `run_session` (`host_operator.py:457-631`) holds the state files, signal handling, revocation, receipt-based `recovery-resolve` and the exit-code rules. Only `_control`, the `ssh -R` child and `SSH_OPTIONS` are specific to SSH.
- `host_runner inventory` and `collect` use a closed, validated schema (`host_operator.py:214-271`). They never read `<UUID>.used.json` or `<UUID>.bridge.json`.

## Review units

### U1. Bridge sockets and relay dispatch

AC8 (the binding half), C2 and C3.

- `BridgeServer` takes an explicit path for each socket kind instead of one directory. For each socket, the server makes sure of these points before it binds:
  - no component of the path is a symlink
  - the parent directory exists, is owned by the current user and has mode 0700
  - the socket path does not exist.
- The process sets `umask 077` before it binds. Each socket gets mode 0600. `close()` unlinks a socket only if its device and inode still match, as today.
- The Mac mode keeps its temporary directory and passes the two paths inside it. Its behavior does not change.
- A relay dispatch factory replaces the module-level `fixed_dispatch`. It takes the workspace root, the absolute `task` path and an explicit environment:
  - `PATH` holds the host tools directory and the standard system directories only
  - `UV` names the host's owner-local `uv`
  - `RAILWAY_NO_AUTO_UPDATE=1`
  - `HOME` is inherited, because the relays read the selector manifest and the Railway login from it.
- `run_launcher` gains an optional `env` argument. Existing callers pass nothing, so nothing else changes.
- The Mac mode builds the dispatch with today's values: the repository root and `task` from `PATH`. The local mode never derives the root from a file location.

### U2. Local session

AC8 (the session half) and C1, C3.

- The shared part of `run_session` moves into one core function. It covers the state files, the bridge session, the signal handlers, revocation, the receipt, `recovery-resolve` and the exit code. Two small adapters supply the transport. The SSH adapter keeps today's commands. The local adapter runs `host_runner prepare`, `run` and `recovery-resolve` as local child processes from the release directory.
- A new subcommand runs a local session:

  ```
  host_operator run-local --manifest PATH --host-root PATH --workspace PATH --tools PATH --state-dir PATH
  ```

  The maintainer runs it from the release virtual environment on the host. No new `Taskfile` task is needed on the host.
- `run-local` refuses to start in these cases. It then exits 1 before it runs prepare:
  - `RAILWAY_NO_AUTO_UPDATE` is not `1` (C1)
  - stdin or stdout is not a terminal, because the Clerk prompt needs one
  - the workspace has no `Taskfile.yml` or no `services/api`
  - the tools directory has no executable `task`, `railway` or `uv`.
- The order is: prepare, bind the two sockets, then start `host_runner run`. The child stays in the operator's process group, so a Ctrl-C in tmux reaches both, as it does today through `ssh -tt`. The operator also forwards SIGTERM and SIGHUP to the child explicitly (C3).
- The state directory is `/srv/tailtag-simulator/operator-state` (AC10). It is owner-only, and `.used.json` and `.bridge.json` keep today's format and their create-once rule.

### U3. Operator workspace

AC7 and C2.

- A new `host_release install-operator` subcommand installs a workspace for one source SHA:

  ```
  host_release install-operator --archive PATH --archive-sha256 HEX --source-sha SHA --root PATH
  ```

  It does the following:
  - it makes sure that the archive digest matches `--archive-sha256`
  - it makes sure that `--source-sha` matches an installed release
  - it extracts the archive with `tarfile`'s `data` filter into `/srv/tailtag-simulator/operator/<sha>`, with directories 0700 and files 0600
  - it runs `tools/uv sync --project services/api --locked` in the workspace.
- It refuses an existing workspace directory. A failed install leaves no partial workspace.
- On the Mac, the maintainer creates the archive with `git archive` from a clean checkout of the release SHA and records its SHA-256. This needs no new task.
- The runbook installs go-task 3.53.1 with the pinned checksum from `.github/actions/install-go-task`. It installs the latest Railway CLI with GitHub's published asset digest. Both go into `/srv/tailtag-simulator/tools/bin`. The CLI only self-updates from a `bin` directory, so the path matters for C1.
- The runbook installs the five-ID selector manifest at `~/.config/tailtag/staging-clean-rebuild-targets.json` with mode 0600. It holds identifiers only, not credentials.

### U4. Operator evidence collection

AC10.

- `host_runner inventory` reports the operator evidence for a settled run when it exists. The evidence is `operator-state/<UUID>.used.json` and `<UUID>.bridge.json`, each with its size and SHA-256. A run from the Mac mode has no host-side operator evidence, so the field is optional.
- The Mac validator accepts inventories with and without the field. A Mac checkout can then collect from an older host release, and the reverse also works.
- `collect` copies the two files into the run's archive directory, makes sure that their digests match, and records them in `collected.json`. A digest mismatch refuses that run, as it does for the report today.

### U5. Documentation

AC9, AC11, C4 to C8 and the corrected C6 timing.

- `docs/operations/simulation-host.md` gains a "Host operator session" section. It covers these steps:
  - the one-time setup: tools, the selector manifest and 2FA (C7)
  - the session start checklist, in the C4 order
  - the session end checklist, which is mandatory after any exit (C5)
  - the out-of-band kill switch (C6).
- The kill switch text states the real timing. If the relays fail fast, the run stops within about 3 minutes. If they hang until the 180 s launcher timeout, it takes up to about 12 minutes.
- The trust statement replaces "Railway/platform credentials and their existing relay configuration remain exclusively on the maintainer machine" with the C8 text. This covers the reach, the compromise response and the rule against Production in this workspace.
- `docs/operations/simulation-operations.md`: the operating model says that an attended session can run from the host.
- `docs/specs/2026-10-10-unattended-simulation-scheduling-design.md`: a short note links the host session rules and the deferred separate container user.

## Tests

An independent test author writes the tests before the implementation, from AC7 to AC10 and C1 to C3. Extend the existing seams.

| Test file | Covers |
| --- | --- |
| `test_host_bridge.py` | Binding in two directories. Refusal of a symlink ancestor, a foreign or wrong-mode parent, and an existing path. Sockets at mode 0600. Cleanup only on a matching identity. |
| `test_host_bridge.py` or `test_host_renewal.py` | The dispatch factory: absolute `task`, the workspace as working directory, the explicit environment, and no use of the file location. |
| `test_host_cli.py` | `run-local`: each refusal (C1, no terminal, no workspace, no tools). The prepare, bind, run order. SIGINT revokes the workload and stops the child. SIGTERM and SIGHUP are forwarded. The local `recovery-resolve` with the receipt. The state files. Use a real child script, not Docker. |
| `test_host_release.py` | `install-operator`: a digest mismatch, an unknown source SHA, a path traversal or link in the archive, an existing workspace, and a failed sync, each leaving no workspace. The modes. The locked sync command. |
| `test_host_collect.py` | Inventory with and without operator evidence. Collection of both files with matching digests. A digest mismatch refuses the run. |

Socket paths on macOS have a limit of about 104 bytes, so the tests use short temporary roots.

## Sequence

1. The maintainer approves this plan.
2. The test author writes the tests above. The parent approves the test set and checks the case count.
3. The implementer builds U1 and U2, then U3 and U4, then U5.
4. Local gates: `task sim-check`, with Ruff `--no-cache`. Run `git add -N` on new files before Semgrep. The two known macOS-only `test_host_runtime` cases are expected to fail.
5. One fresh reviewer gives verdicts per unit, including SECURITY (the PR 2 half of AC6) and RELIABILITY. The findings are fixed.
6. The maintainer approves the push and the pull request.
7. After the merge, the new host release goes through `install-runtime` and passes a smoke gate in the Mac mode (AC4). The first local session belongs to PR 3 (AC12).

## Out of scope

- The first live local session and its evidence (AC12, C9).
- Retiring the Mac mode and turning off sshd forwarding (AC13).
- A separate Linux user for the container (deferred).
- Any change to admission, ceilings, the heartbeat rules or the relays' own checks.
- Unattended scheduling.
