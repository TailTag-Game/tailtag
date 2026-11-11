# Implementation plan: Windows owner-only files and process trees

Implements the approved [spec](2026-10-15-windows-owner-only-files-and-process-trees.md)
(issue #315, slice 3). Section names and S3-n criteria refer to the spec. The
branch is `issue-315-parity-3`. Delivery is one pull request, "Part of #315".

## Review units

### U1. Shared modules

The new module pairs:

| Module | services/api copy | tools/simulator copy |
| --- | --- | --- |
| Owner-only files | `services/api/config/owner_only.py` | `tools/simulator/tailtag_simulator/owner_only.py` |
| Process trees | `services/api/config/process_tree.py` | `tools/simulator/tailtag_simulator/process_tree.py` |

Each copy is byte-identical to its partner. Each module is standard library
only and imports `ctypes` and `msvcrt` only on Windows. The modules implement
the Windows owner-only rule, Creating a private file, and Process trees. They
cover S3-1, S3-2, S3-4 (the module half), and S3-9.

- **Public API:**
  - `OwnerOnlyError(OSError)`
  - `open_owner_only_file(path, *, max_bytes) -> BinaryIO`
  - `create_private_file(path) -> int`
  - `spawn_options() -> dict[str, object]`
  - `ProcessTree` with `attach(pid)`, `terminate()`, `kill()`, and `close()`
- **POSIX branches:** they reproduce today's checks exactly:
  - for the parent folder: `lstat`, is a directory, owned by the current uid,
    mode `0o700`;
  - for the file: `O_NOFOLLOW` open, `fstat`, is a regular file, owned by the
    current uid, mode `0o600`, size;
  - for creation: `O_EXCL | O_NOFOLLOW` with mode `0o600`;
  - for process trees: `start_new_session` and `killpg`, suppressing
    `ProcessLookupError`.
- **Windows-only code:** every Windows-only line is guarded by
  `sys.platform == "win32"`, so Pyright on macOS and Linux treats it as
  unreachable. CI checks types with Pyright on Linux. The Windows branches are
  proven by the Windows CI tests.
- **Wiring:** the simulator copies are imported only by modules that run
  locally. The API copies sit under `config/`, so the scripts reach them
  through the existing `PYTHONPATH`. Ruff, Pyright, and Semgrep already cover
  both directories.

### U2. API callers

S3-1 and S3-3 (the callers), S3-4 (the restore drill), S3-5, S3-6 (the
evidence), S3-7, and S3-12.

- **`config/replacement_target_binding.py` `_read_local_manifest`:** call
  `open_owner_only_file(path, max_bytes=65536)`, wrap the result in
  `io.TextIOWrapper(encoding="utf-8")`, and keep `json.load` with
  `_unique_object`. The existing `except` tuple maps failures to
  `TargetBindingError`.
- **`scripts/api_staging_reset_ssh.py` `_read_configuration`:** call
  `open_owner_only_file(path, max_bytes=16 * 1024)`, then
  `.read().decode("utf-8").splitlines()`. The parsing and errors are
  unchanged.
- **`scripts/api_staging_restore_drill.py`:**
  - The tunnel, `pg_dump`, and `docker exec` children use `spawn_options()`
    plus `ProcessTree.attach`. `cleanup_task_resources` uses the trees in
    place of `killpg`. Processes without a tree keep the existing
    `terminate`/`kill` fallback.
  - The tunnel-details read and the dump streaming use daemon threads, as
    described under "Restore drill on Windows" in the spec, in place of
    `select.select`, `os.set_blocking`, and `os.read`.
  - The Docker endpoint rule follows D4. The denial message names both local
    forms.
  - The evidence publish uses `create_private_file`, and skips the directory
    `fsync` on Windows with a comment.

### U3. Simulator callers and tasks

S3-4 (pool), S3-6 (reports and evaluations), and S3-8.

- **`pool.py` `run_launcher`:** use `spawn_options()` and `attach` straight
  after `create_subprocess_exec`, with no `await` in between. Cleanup
  (`kill`, `await process.wait()`, and `close`) goes in `finally`.
- **`reports.py`:**
  - The reservation uses `create_private_file`.
  - Each snapshot writes through `create_private_file` under a random
    `.snapshot-<hex>.tmp` name, then `os.replace`.
  - The ancestor check refuses junctions as well as symlinks.
  - `NO_FOLLOW` is removed.
- **`evaluation.py` `write_evaluation`:** use `create_private_file`.
- **`Taskfile.yml`:** each `sim-host-*` task gets a `platforms: [windows]`
  command that prints the D1 line and exits `1`. Its current command moves
  under `platforms: [linux, darwin]`.
- **Tests:**
  - The `tools/simulator/tests/conftest.py` comment says the host modules are
    POSIX-only by design (D1).
  - The timeout cases in `test_pool.py` and `test_fixture_channel.py` run on
    Windows again.
  - `test_evaluation.py` gains Windows access-list assertions next to its
    mode assertions.

### U4. Documentation

S3-11.

- `docs/development/getting-started.md`, Native Windows section: covers which
  slice 3 tasks now work, the `sim-host-*` fail-fast, the checkout location,
  and the remaining POSIX-only operator scripts (D2).
- `docs/development/staging.md`: the Windows operator setup, using the
  PowerShell and `icacls` commands from the spec.
- `docs/operations/simulation-host.md`: the workflow needs macOS or Linux, and
  WSL works.
- The simulator README, if it lists platforms.
- `services/api/tests/conftest.py`: the comment names D2 for the modules that
  stay skipped.

## Tests

Tests are written before the implementation, by an independent test author,
from the spec's "Tests and CI" section.

| Test file | Covers |
| --- | --- |
| `services/api/tests/test_owner_only.py` (new) | The owner-only rule and private create on every OS. Windows fixtures use `icacls`, `mklink /J`, and SDDL through ctypes. It includes the BOM parity case for the manifest reader. |
| `services/api/tests/test_process_tree.py` (new) | Tree kill, close, and the inner-job breakaway case. A fail-closed `attach` is driven through a test seam only if one is needed. The test author should prefer a real failure, such as a pid that has already exited. |
| `services/api/tests/test_vendored_modules.py` (new) | The byte-identical pairs (S3-9). |
| `services/api/tests/test_api_staging_restore_drill.py` | The npipe rule, a writer failure becoming a denial, and Windows branches for its POSIX-only fixtures. |
| `tools/simulator/tests/test_reports*.py` or the existing report tests | The report access list after a snapshot, and junction ancestors. |
| `test_replacement_target_binding.py`, `test_replacement_candidate_origin.py`, `test_replacement_migrate.py`, `test_api_staging_reset_ssh.py` | Collected on Windows again. Windows fixture branches are added through the helper, or `icacls`. The POSIX fixtures and assertions are untouched (S3-12). |
| `tools/simulator/tests/test_tasks*.py` or `test_task_commands.py` | The `sim-host-*` fail-fast. Use a dry run on non-Windows, and the real message on Windows. |

The simulator tests use the simulator's own copy of each module. The helper
tests live in `services/api` only, because the copies are identical, which
S3-9 enforces.

## Sequence

1. The test author writes the tests listed above. The parent reviews and
   approves the test set.
2. The implementer builds U1, then U2 and U3.
3. Local gates on macOS:
   - `task api-check`, using a scratch PostgreSQL cluster;
   - `task sim-check`;
   - `git add -N` for new files before Semgrep;
   - Ruff with `--no-cache`.
4. Push and open a draft PR. The Windows jobs (`Windows API commands`,
   `Windows simulator commands`) prove the Windows branches. Iterate from the
   full run logs.
5. One fresh reviewer, with SECURITY and RELIABILITY assurance and verdicts
   per unit. Fix the findings.
6. The PR is ready for review once the maintainer agrees.

## Out of scope

- The items under "Non-goals" in the spec.
- Every operator script without a task (D2).
- An automated check of the checkout location (D5).
