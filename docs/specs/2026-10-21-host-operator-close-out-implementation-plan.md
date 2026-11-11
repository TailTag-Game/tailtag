# Implementation plan: host operator close-out

Implements #316 AC13, the runbook gap found in the first host session, and the two expiration-scenario defects found by the AC12 run. The source of truth is the refinement and its amendments on [#316](https://github.com/TailTag-Game/tailtag/issues/316). The branch is `issue-316-retire-mac-mode`. Delivery is one pull request, "Part of #316". The pull request also needs the PR 3 half of AC6, a diff-level SECURITY verdict.

## Facts that shape the design

- The AC12 run (`2cf1b668`) proved expiry. After expiry, the resolve endpoint returns 404 with the generic body "Catch credential not found." and no `code` field (`services/api/conventions/views.py:288-290`). The simulator expects `catch_target_unavailable` there (`tools/simulator/tailtag_simulator/traffic_behavior.py:264-275`). That code belongs to the confirm endpoint.
- In active mode, an actor keeps making visits until the traffic window ends. A worker holds its actor slot while it sleeps `think_seconds` after an entry (`traffic.py:371-381`). When the window ends, the scheduler waits `drain_seconds` for busy workers, then stops with `drain` (`traffic.py:505-511`). The expiration profile has `think_seconds` 60 and `drain_seconds` 15, so a window that ends during the think sleep always stops with `drain`.
- `max_entries` cannot limit the profile to one visit. In active mode, reaching the cap stops the run with `entries` (`traffic.py:469-471`, `494-496`), which also fails the run.
- The Mac mode is `host_operator run` (`run_session`, `host_operator.py:602`), the `sim-host-prepare` and `sim-host-run` tasks, and the sshd remote forwarding that bootstrap allows (`tools/simulator/host/bootstrap.sh:82`). `sim-host-collect` uses plain `ssh` and `scp` with `SSH_OPTIONS` and no forwarding.
- `tests/test_host_ssh.py` proves the bootstrap forwarding policy against real Linux OpenSSH. It runs only on a disposable Linux runner as root.
- Railway CLI 5.71.0 `ssh keys add` finds keys only in `~/.ssh/` and the SSH agent.

## Review units

### U1. Expiration scenario

- After the server's `expires_at`, a resolve that returns 404 with no `code` counts as an expected rejection (`step` with `404` and `"-"`). Any other non-200 reply still fails the visit, as today. A 200 reply keeps its current handling.
- `expiration-profile.json` sets `limits.drain_seconds` to 120. That covers the 60 s think sleep, one request and a margin. It stays within the closed expiration shape.
- The result: every visit after expiry becomes another rejected resolve and confirm, and the window can end during a think sleep without `drain`.

### U2. Retire the Mac mode

AC13.

- Remove the `host_operator run` subcommand and `run_session`. The `_operate` core then serves only the local adapter. Fold the adapter seam into it where that removes indirection, with no behavior change.
- Remove the `sim-host-prepare` and `sim-host-run` tasks from `Taskfile.yml`, and their entries in `test_task_commands.py`. The host session prepares on the host. Keep `host_operator prepare` and `collect`.
- `SSH_OPTIONS` keeps only the options that plain `ssh` and `scp` need for collection. Remove `ExitOnForwardFailure` and `StreamLocalBindUnlink`.
- `bootstrap.sh` turns off forwarding for the owner with `DisableForwarding yes`, which covers TCP, stream-local, agent and X11 forwarding, and keeps `PermitTunnel no`. It removes `PermitListen` and the stream-local bind options, which have no use without forwarding.
- `test_host_ssh.py`: the real-OpenSSH test now proves that remote Unix forwarding is refused as well.

### U3. Documentation

- `docs/operations/simulation-host.md`:
  - Replace "Profile preparation and foreground execution" with a short pointer to the host operator session.
  - Remove the reverse-forwarding text from the SSH configuration section.
  - Add the console step that applies the new sshd drop-in to the existing host. The step writes the file, runs `sshd -t` and reloads `ssh`. It does not run the full bootstrap again.
  - Add the session-key symlink step to session start: link the `/dev/shm` key pair as `~/.ssh/tailtag-sim-session` and `.pub`, then `railway ssh keys add --key ~/.ssh/tailtag-sim-session.pub`. Add the link removal to session end.
- `docs/operations/simulation-operations.md`: the smoke and nightly commands use the host session instead of `sim-host-prepare` and `sim-host-run`.
- `docs/development/getting-started.md` and `tools/simulator/README.md`: drop the removed tasks.
- `docs/specs/2026-10-13-simulation-operations-staging-proof.md`: one paragraph records the AC12 run and its two defects.
- Historical specs keep their text.

## Tests

An independent test author writes the tests before the implementation. Extend the existing seams.

| Test file | Covers |
| --- | --- |
| `test_traffic_behavior.py` | The expired case: a post-expiry resolve that gets 404 with no code counts as an expected rejection, and the visit passes. A post-expiry resolve with another non-200 reply still fails the visit. |
| `test_traffic_config.py` or `test_host_cli.py` | Every committed profile has `drain_seconds` greater than `think_seconds`. |
| `test_host_runtime.py` and `test_host_cli.py` | Remove the Mac-mode tests with the code they test. The local-mode tests keep covering the shared core. |
| `test_task_commands.py` | The removed tasks are gone from the task list. |
| `test_host_ssh.py` | Remote Unix forwarding is refused. This runs in Linux CI. |
| `test_host_collect.py` | No change. It proves that collection from the Mac still works without forwarding. |

## Sequence

1. The maintainer approves this plan.
2. The test author writes and adjusts the tests. The parent approves the test set.
3. The implementer builds U1 and U2. The parent writes U3.
4. Local gates: `task sim-check`, with Ruff `--no-cache`, and `task doctor`. The two known macOS-only `test_host_runtime` cases are expected to fail. Linux CI runs `test_host_ssh.py`.
5. One fresh reviewer gives verdicts per unit, including SECURITY (the PR 3 half of AC6). The findings are fixed.
6. The maintainer approves the push and the pull request.
7. After the merge:
   - the maintainer applies the sshd drop-in from the provider console
   - the new release goes through `install-runtime`, and a host-session smoke passes (AC4)
   - #316 closes after AC14 and the #199 comment for AC15.

## Out of scope

- A new expiration run. The maintainer accepted run `2cf1b668` for AC12.
- Unattended scheduling (#336).
- Any change to the API, admission, ceilings or the heartbeat rules.
