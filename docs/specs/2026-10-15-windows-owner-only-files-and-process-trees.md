# Windows owner-only files and process trees

Issue #315, slice 3. Status: **approved** (security review: approve with
changes, all applied; maintainer approval 2026-10-15).

Issue #315 requires every `Taskfile.yml` task to run natively on Windows,
macOS, and Linux. Where a platform physically cannot support a command, the
command must fail fast with a message that names the requirement. Slices 1
and 2 (#321, #322) ported the portable commands, `doctor`, and the mobile
tooling. This spec covers what remains: the Staging operator tasks, plus the
simulator's Staging and host tasks.

## Problem

The remaining tasks fail on native Windows for three reasons:

1. **Owner-only checks use POSIX ownership and modes.** Before reading a local
   file that holds Staging secrets or bindings, the operator tooling checks
   two things:
   - the parent directory is owned by the current user and has mode `0o700`;
   - the file is a regular, non-symlink file owned by the current user with
     mode `0o600`.

   Windows has no `os.getuid` or `O_NOFOLLOW`, and its mode bits carry no
   access meaning, so these checks crash at import or when called.
2. **Private files are created with mode `0o600`.** Windows ignores that mode
   apart from the read-only bit. The file inherits its folder's access list.
   Outside the user profile, that list commonly grants `Users` read access and
   `Authenticated Users` modify access. Files that should be private are then
   readable, and their folders writable, by other accounts.
3. **Timeouts kill process groups.** Launchers start children with
   `start_new_session=True` and kill the whole tree with `os.killpg`. Windows
   has neither. The launcher chain is `task` → `uv` → Python → `railway ssh`.
   Killing only the direct child leaves the descendants running, and they keep
   the pipes open.

No existing spec states the threat model behind the POSIX checks. The operator
documents state only the `0600`/`0700` requirements:

- `docs/development/staging.md`
- `docs/operations/simulation-host.md`
- `docs/development/replacement-staging-promotion-contract.md`

This spec is the first written threat model, and it defines the Windows
equivalent.

## Maintainer decisions (2026-10-15)

- **D1. Simulation host workflow.** On Windows, `sim-host-prepare`,
  `sim-host-run`, `sim-host-collect`, `sim-host-release-export`, and
  `sim-host-release-load` fail fast with a message. The workflow has no
  faithful Windows equivalent:
  - it relays Unix-domain sockets over OpenSSH stream-local forwards;
  - it uses `fcntl` locks;
  - it walks evidence trees with directory descriptors (`O_DIRECTORY`,
    `dir_fd`).

  `sim-host-bootstrap-check` keeps its existing `SKIP` line.
- **D2. Scope is the Taskfile.** Staging operator scripts that no task runs
  stay POSIX-only, and so do their tests: the operator matrix, managed-auth
  diagnosis, password rotation, the emergency operator, and restart. Those
  that share `config.replacement_target_binding` benefit automatically.
- **D3. Windows access rule.** The owner is the current user. Only the current
  user, `SYSTEM`, and `Administrators` may hold access entries. Every other
  account or group is refused. Files TailTag creates get exactly this access
  list, with inheritance off.
- **D4. The restore drill on Windows accepts only a local Docker named pipe.**
  The drill keeps refusing any Docker endpoint that is not local. On Windows
  the accepted form is exactly `npipe:////./pipe/<name>`. A remote form such
  as `npipe:////host/pipe/...` is refused, so the Staging dump can only reach a
  local daemon. The `unix://` rule on POSIX is unchanged.
- **D5. Checkout location is documented, not enforced.** On Windows, the
  checkout, the uv cache, and the tool binaries must sit under
  `%USERPROFILE%`, or anywhere no other account can write. The docs state
  this. No code checks it.
- **D6. Inheritance on checked objects.** This refines D3; the security
  review and the maintainer approved it. Objects that TailTag only
  checks do not have to have inheritance turned off. The check reads the
  entries actually stored on the object. Objects TailTag creates still get a
  protected access list.

## Goals

- G1. These tasks run on native Windows:
  - `api-replacement-auth-smoke`, `api-staging-reset-ssh`, and
    `api-staging-reset-provision-ssh`;
  - `api-staging-restore-drill`;
  - the `sim-pool-*` tasks, `sim-fixture-smoke`, `sim-journeys`,
    `sim-convention`, `sim-cleanup`, and `sim-retained`;
  - `sim-image`.

  They keep the same safety properties as on POSIX, or as close as Windows
  allows. Every deviation is stated in this spec.
- G2. One implementation per concern. The duplicated owner-only checks in
  `config/replacement_target_binding.py` and `scripts/api_staging_reset_ssh.py`
  become one helper.
- G3. POSIX behavior is unchanged: the same inputs are accepted and refused.
  This includes the production use of `replacement_target_binding` on Railway,
  which runs Linux.
- G4. Standard library only (`ctypes`, `msvcrt`). No new dependency.

## Non-goals

- Porting the simulation host workflow (D1) or the operator scripts without a
  task (D2).
- Windows support for remote code. The Linux host runner, the scripts run
  inside Railway containers, and container-side `umask` stay POSIX.
- Hidden-input (pty and termios) test harnesses on Windows. Production prompts
  use `getpass`, which already hides input on a Windows console.
- Running live Staging, Railway, Docker, or PostgreSQL from a Windows machine
  as part of verification (see Verification limits).
- An automated check of the checkout's own access list (D5).

## Threat model

The files involved hold Staging secrets, or bindings that decide which Railway
target an operation touches:

- `~/.config/tailtag/staging-reset-replacement.env` (database URLs);
- the replacement target manifest;
- restore-drill evidence;
- simulator reports and evaluations, which may name Staging identifiers.

The adversaries are:

- **A1. Another local account** on the same machine reads secrets or evidence.
- **A2. Another local account substitutes or redirects files.** It replaces a
  file, or plants a symlink, junction, or hard link. As a result, the
  operator's tooling reads attacker-chosen bindings and acts on the wrong
  Railway target, or one of its writes overwrites another file.
- **A3. The operator's own mistakes.** Examples are a permissive folder in a
  shared location, or a file copied in with broad access. The tooling should
  refuse these rather than silently use them.

Out of scope, as on POSIX:

- administrators, `SYSTEM`, and Backup Operators, who can bypass access lists
  through backup privileges;
- malware already running as the operator.

**The code itself must be private too (D5).** The tasks run Python from the
checkout: `uv run --project services/api`, the checkout's `.venv`, and
`PYTHONPATH` set to the repository root. Suppose another account can write
there. It could edit `config/replacement_target_binding.py`, including its
pinned digests, or drop a `.pth` file into the virtual environment. Its code
would then run as the operator, and the owner-only file checks would no longer
matter.

On POSIX this needs an unusually group- or world-writable checkout. On Windows
it is the default for any folder created under a drive root. For example,
`C:\src` inherits modify access for `Authenticated Users` from `C:\`. The
operator setup therefore requires a private checkout location.

POSIX enforces owner-only through the owner uid, the mode bits, and refusing
to follow symlinks. Windows enforces the same properties through the owner
SID, the access list (DACL), and refusing reparse points.

## Windows owner-only rule

The **allowed set** has exactly three SIDs:

- the current user's SID, taken from the process token's `TokenUser`;
- `SYSTEM` (`S-1-5-18`);
- `Administrators` (`S-1-5-32-544`).

Matching is by exact SID equality. Groups that contain the operator are
refused because their SIDs differ. These include `Users`, `Authenticated
Users`, `INTERACTIVE`, the logon SID, `CREATOR OWNER` (`S-1-3-0`),
`CREATOR GROUP` (`S-1-3-1`), and `OWNER RIGHTS` (`S-1-3-4`). These refusals are
deliberate, and they fail closed.

**The owner must be the `TokenUser` SID.** An `Administrators` owner is never
accepted. An elevated token can make `Administrators` the default owner of new
objects, which is one more reason for the read-back step under Creating a
private file.

### Checking an existing directory or file

`open_owner_only_file(path, *, max_bytes)` works in three steps.

**1. Check the parent folder.** It opens `path.parent` as a directory, with
`CreateFileW` and these flags:

- `FILE_FLAG_BACKUP_SEMANTICS`;
- `FILE_FLAG_OPEN_REPARSE_POINT`;
- share mode `FILE_SHARE_READ | FILE_SHARE_WRITE`, deliberately without
  `FILE_SHARE_DELETE`.

It applies every check below to that handle, and keeps the handle open until
step 3 finishes. Because the handle denies delete sharing, nobody can rename or
delete the parent folder while the file is being opened and checked. This
closes the parent-swap window that the POSIX path-based check leaves open.

**2. Open and check the file.** It opens the file with `CreateFileW`, using
`GENERIC_READ | READ_CONTROL`, `OPEN_EXISTING`, and
`FILE_FLAG_OPEN_REPARSE_POINT`. It applies every check below to that handle.

**3. Read only after everything passes.** Only then does it convert the handle
with `msvcrt.open_osfhandle` and return a binary file object. The bytes read
are therefore the bytes of the object that was checked.

An object is refused when any of these holds:

| Check | Refused when | POSIX equivalent |
| --- | --- | --- |
| Type | Any reparse point: `FILE_ATTRIBUTE_REPARSE_POINT` is set, which covers symlinks, junctions, and any other tag, whether or not its filter is running. A directory is refused if it lacks `FILE_ATTRIBUTE_DIRECTORY`. A file is refused unless `GetFileType` is `FILE_TYPE_DISK` and `FILE_ATTRIBUTE_DIRECTORY` is clear. | `lstat`, `O_NOFOLLOW`, `S_ISDIR` / `S_ISREG` |
| Owner | The owner SID is absent, or is not the `TokenUser` SID. | `st_uid == getuid()` |
| DACL | Any of these: `SE_DACL_PRESENT` is not set; the DACL pointer is NULL (a NULL DACL grants everyone full access); the security information cannot be read (for example on FAT, exFAT, or some network shares). | — (fails closed) |
| Entry types | Any entry is neither a basic allow entry (`ACCESS_ALLOWED_ACE_TYPE`) nor a basic deny entry (`ACCESS_DENIED_ACE_TYPE`). Object entries, callback entries, and every other type fail closed. Before an entry's SID is parsed, its `AceSize` is bounds-checked and the SID is validated with `IsValidSid`. | — |
| Allow entries | Any allow entry names a SID outside the allowed set, whatever its flags. Inherit-only and inherited entries count too: on a folder, inherit-only entries decide what files created later can be read by. | Group and other mode bits are 0. |
| Size | A file is larger than `max_bytes`. | `st_size` limit |

**Deny entries are accepted.** Basic deny entries only remove access, and the
allow-entry rule does not depend on entry order.

**The SACL is deliberately not read.** Mandatory labels, central access
policies, and resource attributes live there. They can only restrict access,
and reading them needs `SeSecurityPrivilege`.

**Inheritance is not required to be off on a checked object (D6).** NTFS
inheritance is static: inherited entries are written onto each object when it
is created, or when an owner changes the parent and propagates the change.
Access checks read only the object's own access list. A file inside a verified
folder therefore passes with the entries it inherited from that folder.
Changing the folder's list requires `WRITE_DAC`, which only the owner and the
allowed set hold. Every read checks the folder and the file again.

**Hard links.** The current POSIX checks for these files do not check the link
count. Windows also keeps one security descriptor per file, not per link. The
helper therefore checks the link count on neither platform, which preserves G3.

**Errors.** The helper raises exactly one refusal type, `OwnerOnlyError`. It
subclasses `OSError` so that both callers' existing `except` clauses keep
catching it. Every ctypes failure is converted to `OwnerOnlyError`, including
`ArgumentError`, `OverflowError`, `AttributeError`, and a zero return from a
Win32 call. The refusal carries no detail.

**Decoding stays in the callers.** The helper returns bytes, and the callers
decode them strictly. This keeps today's text handling on POSIX (G3). If the
manifest's bytes went straight to `json.load`, JSON's own encoding detection
would start accepting a UTF-8 BOM, UTF-16, and lone surrogates, which the
text-mode reader refuses today.
- `_read_local_manifest` wraps the handle in
  `io.TextIOWrapper(fp, encoding="utf-8")` and passes text to `json`.
- `_read_configuration` keeps `.decode("utf-8").splitlines()`.

**Reading the reset configuration from the descriptor.**
`_read_configuration` currently calls `lstat` and then `read_text`. Reading
from the open descriptor instead is an intended tightening. It changes the
result only for a file swapped between those two calls.

### Creating a private file

`create_private_file(path)` returns a writable descriptor for a new file. It
raises `OwnerOnlyError` if it cannot create the file.

On Windows it calls `CreateFileW` with:

- `CREATE_NEW` **together with** `FILE_FLAG_OPEN_REPARSE_POINT`. Both are
  required. Together they refuse any existing name, including a dangling
  symlink or junction.
- No sharing.
- `SECURITY_ATTRIBUTES` holding an absolute security descriptor:
  - the owner is the `TokenUser` SID;
  - the DACL is **protected** (inheritance off);
  - the DACL holds exactly three allow entries, each granting full control: to
    the current user, `SYSTEM`, and `Administrators`.

**Read-back is required.** A file system without security support silently
ignores the security descriptor. So, before returning, the function reads the
owner and DACL back through the new handle and runs the same checker on them.
It also confirms that the DACL is protected. On any mismatch it closes the
handle, deletes the file, and raises. This also confirms that the owner
assignment took effect.

On POSIX the function is today's
`os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)`.

### Ancestor checks for reports

The simulator refuses report directories whose path contains a symlink
(`reports.py`). On Windows it must also refuse junctions. The check becomes
`p.is_symlink() or p.is_junction()`; Python 3.13 is the project's floor.

### Every private write on a slice 3 path

`RunReport` reserves its path with an exclusive create, and then writes each
snapshot through `tempfile.mkstemp` followed by `os.replace` (`reports.py`).
On Windows, mkstemp's mode is ignored, and the replaced file keeps the
temporary file's inherited access list. So each snapshot's temporary file is
created with `create_private_file`, under a random name in the same folder,
and then replaced. The implementation plan lists every writer on a slice 3
path that uses `mkstemp`-and-replace, or writes a file directly, and routes
private ones the same way. Public files, such as `baselines.py` `0o644`
baseline data, are named and left alone.

## Process trees

`process_tree` replaces `start_new_session=True` plus `os.killpg`:

- `spawn_options()` returns the keyword arguments for `subprocess.Popen` or
  `asyncio.create_subprocess_exec`. Both pass `creationflags` through on
  Windows; asyncio forwards them to `subprocess.Popen`.
  - POSIX: `{"start_new_session": True}`.
  - Windows: `{"creationflags": CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP}`.
    `CREATE_NEW_PROCESS_GROUP` keeps the terminal's Ctrl+C away from the
    children, as `start_new_session` does on POSIX.
- `ProcessTree.attach(pid)` is a no-op on POSIX. On Windows it runs while the
  child is still suspended:
  1. Create a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
     - The job never sets `JOB_OBJECT_LIMIT_BREAKAWAY_OK` or
       `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`. Its handle is not inheritable
       (`CreateJobObjectW` with NULL security attributes).
     - Windows documents that a child breaking away from an inner job moves
       up the job chain only until it reaches a job that does not permit
       breakaway. Descendants in inner jobs that allow silent breakaway
       therefore stay inside TailTag's job.
  2. Assign the child to the job.
  3. Take a Toolhelp thread snapshot. It must contain exactly one thread of
     the child. Open that thread and check that `GetProcessIdOfThread` equals
     `pid`. Then call `ResumeThread`, which must report a previous suspend
     count of exactly 1.

  The child cannot run before it is in the job. If any step fails, `attach`
  raises, terminating the child when its process could be opened. Callers
  still kill and wait their own process handle on any `attach` exception. The
  pid stays valid during attach, because the caller's `Popen` object holds the
  process handle open.
- **Caller discipline.** There is no `await` between spawning the child and
  calling `attach`. `attach` runs before the `try` block that kills on
  `BaseException`.
- `ProcessTree.terminate()` and `ProcessTree.kill()`:
  - POSIX: `killpg` with `SIGTERM` or `SIGKILL`, suppressing
    `ProcessLookupError`.
  - Windows: `TerminateJobObject` for both. Windows has no graceful group
    signal. Termination is asynchronous, so callers then wait for the direct
    child as they do today. A failed call on an already-empty job is ignored.
- `ProcessTree.close()` is a no-op on POSIX. On Windows it closes the job
  handle, and because of `KILL_ON_JOB_CLOSE` any descendant still running is
  killed too.
  - It is called only during the caller's cleanup, never from `__del__`.
  - A caller whose descendants must outlive one stage keeps the job open until
    its final cleanup. For example, the restore drill's tunnel lives across
    stages.
  - If the Python process dies, the job's processes die as well. This is
    stronger than POSIX, where an orphaned process group survives its
    launcher.

The callers are:

- `tools/simulator/tailtag_simulator/pool.py` `run_launcher`, which serves
  every `sim-*` Staging task;
- `scripts/api_staging_restore_drill.py`: the Railway tunnel, `pg_dump`, and
  the `docker exec` receiver, plus `cleanup_task_resources`.

### Restore drill on Windows

**Pipe streaming.** The drill uses `select.select` on subprocess pipes in two
places: to read the tunnel details within a deadline, and to stream the dump
from `pg_dump` into `docker exec` through a buffer bounded to one chunk.
Windows `select` accepts only sockets. Both places are replaced by a single
portable implementation with daemon reader and writer threads over a queue
that holds one chunk:

- Exceptions in either thread are passed to the main thread, which re-raises
  them as the existing denial.
- Streaming succeeds only when all of these hold: the reader reached end of
  file, the queue is empty, the writer finished, and the bytes written equal
  the bytes read. Otherwise a silent writer failure could close the receiver's
  stdin and leave a truncated dump that exits 0.
- The tunnel reader stops once the details parse. The tunnel's stdout stays
  open for the tunnel's whole lifetime.
- The main thread keeps the existing deadlines. On timeout it kills the
  process trees, which closes the pipes and ends the threads.

This changes the POSIX code but not its behavior. The deadlines, size bounds,
and denial messages stay the same, and the existing tests cover them.

**Docker endpoint (D4).** The drill accepts `unix://` on POSIX, and on Windows
exactly `npipe:////./pipe/<name>`, where `<name>` matches `[A-Za-z0-9_.-]+`.
Anything else is denied with the existing message, which now names both local
forms. A test covers both the remote form `npipe:////host/pipe/docker_engine`
and the `npipe:///` variants.

**Evidence.** Restore-drill evidence keeps its atomic, no-overwrite publish:
it is written to a private temporary file through `create_private_file` and
then published with `os.link`, which NTFS supports. Windows cannot `fsync` a
directory, so that step is skipped there, with a comment in the code. NTFS
journals metadata, so the link is durable once it is created.

## Module layout

There are two small standard-library modules. Each is kept identical in both
Python projects, because `services/api` and `tools/simulator` are separate uv
projects and images.

| Module | services/api copy | tools/simulator copy |
| --- | --- | --- |
| Owner-only files | `services/api/config/owner_only.py` | `tools/simulator/tailtag_simulator/owner_only.py` |
| Process trees | `services/api/config/process_tree.py` | `tools/simulator/tailtag_simulator/process_tree.py` |

A test fails if either pair differs by even one byte. A shared path dependency
would change both lockfiles, both Docker build contexts, and the simulator
image provenance inputs. That is more change than two vendored files.

The callers of each function:

- `open_owner_only_file`:
  - `config/replacement_target_binding.py` (`_read_local_manifest`);
  - `scripts/api_staging_reset_ssh.py` (`_read_configuration`).

  Each caller keeps its own exception type and message.
- `create_private_file`:
  - simulator `reports.py`, for both the reservation and the snapshots;
  - simulator `evaluation.py`;
  - the restore drill's evidence publish.

  `reports.NO_FOLLOW` is removed.

## Simulation host tasks on Windows (D1)

On Windows each `sim-host-*` task prints the following line and exits `1`:

```
FAIL  The simulation host workflow needs macOS or Linux (WSL works); see docs/operations/simulation-host.md.
```

The tasks use go-task's `platforms:` split, as `sim-host-bootstrap-check`
already does. The host modules and their eight test modules stay POSIX-only by
design, and the simulator conftest comment says so.

## Operator setup on Windows

`docs/development/staging.md` and `docs/development/getting-started.md` gain
the following.

**Checkout location (D5).** Clone TailTag under `%USERPROFILE%`, for example
`$HOME\repos\tailtag`. Keep uv and its cache in their default per-user
locations. Do not use a folder under a drive root, such as `C:\src`, unless no
other account can write to it.

**Configuration folder.** The PowerShell equivalent of `mkdir -m 700` and
`chmod 600`:

```powershell
New-Item -ItemType Directory -Force "$HOME\.config\tailtag" | Out-Null
icacls "$HOME\.config\tailtag" /setowner "$env:USERNAME"
icacls "$HOME\.config\tailtag" /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
```

The `/setowner` line matters in an elevated shell, where new folders are owned
by `Administrators`; it is harmless otherwise.

Files created in that folder afterwards inherit only those three entries.

**Inspect and fix.** The doc lists the `icacls` command that shows a file's
entries. If the owner is wrong, for example because the file was created from
an elevated shell, the fix is `icacls <file> /setowner "$env:USERNAME"`. A
refused file gets the same short failure as on POSIX.

## Tests and CI

### Owner-only helper

One test module runs on every OS, setting up each case with that platform's
own tools.

- **Windows fixtures:**
  - The owner is set explicitly to the `TokenUser` SID, because the elevated
    CI runner may default new objects to an `Administrators` owner.
  - `icacls` sets the ordinary access lists.
  - `mklink /J` creates junctions, which needs no privilege. `os.symlink`
    creates file symlinks, which works on the elevated runner; elsewhere that
    case is skipped with a reason.
  - The entries that `icacls` cannot create are built from SDDL with
    `ConvertStringSecurityDescriptorToSecurityDescriptorW` and applied with
    `SetSecurityInfo`. These are an object entry (for example
    `D:(OA;;GA;;;WD)`), a callback entry (`XA`), and a NULL DACL
    (`D:NO_ACCESS_CONTROL`).
- **Accepted:**
  - an owner-only folder and file;
  - a file whose only entries were inherited from that folder (D6);
  - an extra basic deny entry.
- **Refused:**
  - a broader allow entry, such as read for `Users`;
  - a broader inherit-only entry on the folder;
  - a `CREATOR OWNER` inherit-only entry on the folder;
  - an object entry, a callback entry, a NULL DACL, and a DACL that is not
    present;
  - a reparse point on the file (both a junction and a symlink);
  - a reparse point on the parent;
  - an `Administrators` owner;
  - a directory where a file is expected;
  - a file over the size limit;
  - a UTF-8 BOM in the manifest, a G3 parity case that runs on every OS.

### Private create

On every OS, private create refuses an existing file, an existing symlink, a
dangling symlink, and (on Windows) a dangling junction. On Windows it must
also pass these checks:

- the resulting owner is the `TokenUser` SID;
- the DACL is protected;
- the DACL contains exactly the allowed set;
- a simulator report still has that DACL after at least one snapshot has
  replaced it.

### Process tree

- On every OS, a child that starts a grandchild is killed as a tree. The test
  then waits, with a timeout, until both processes are gone, by polling the
  job's active-process count on Windows and the pids on POSIX.
- On Windows only:
  - closing the job kills a descendant that is still running;
  - a grandchild started inside an inner job that allows silent breakaway is
    still killed;
  - if the suspended-thread checks fail, `attach` fails closed.

### Restore drill

- The npipe acceptance and refusal cases (D4).
- A writer failure during streaming produces a denial, never a successful
  but truncated dump.

### Byte-identical copies

One repository test compares each pair of modules.

### Windows collection

These test modules are collected on Windows again:

- `test_replacement_target_binding.py`
- `test_replacement_candidate_origin.py`
- `test_api_staging_reset_ssh.py`
- `test_api_staging_restore_drill.py`

The timeout cases in `test_pool.py` and `test_fixture_channel.py` and the
private-file assertions in `test_evaluation.py` also run on Windows again.

`test_replacement_migrate.py` stays skipped on Windows: it runs the Railway
pre-deploy wrapper under production settings, which is remote Linux code (a
non-goal).

Their POSIX fixtures and assertions are left exactly as they are. Windows
branches are added next to them. Modules outside D2's scope stay skipped, and
the conftest comment names the maintainer decision.

### CI

The existing permanent Windows jobs (`api-check`, `sim-check`) run all of the
above, so no new job is needed.

## Acceptance criteria

- **S3-1.** On Windows, `open_owner_only_file` enforces every row of the
  checking table on one parent handle (held without delete sharing) and one
  file handle. It reads only through the checked handle, and only after every
  check passes. On POSIX it accepts and refuses exactly what the two current
  call sites accept and refuse.
- **S3-2.** On Windows, `create_private_file` creates the file with the
  protected, three-entry DACL and the `TokenUser` owner, and verifies both by
  reading them back. Otherwise it deletes the file and raises. It refuses
  existing names and dangling reparse points. On POSIX it is unchanged.
- **S3-3.** Both owner-only call sites use the helper, and their duplicated
  checks are removed. Each caller decodes strictly as today and keeps its
  error type and message. Every helper failure is an `OwnerOnlyError`.
- **S3-4.** `process_tree` kills the whole launcher tree on timeout or cancel
  on every OS. It meets every Windows condition in Process trees, and it fails
  closed if a Windows child cannot be put in a job. `pool.run_launcher` and the
  restore drill use it. `os.killpg` no longer appears in any code path in
  slice 3 scope.
- **S3-5.** The restore drill's tunnel read and dump streaming use no `select`
  on pipes. They keep their deadlines, bounds, and denial messages, and a
  writer failure can never pass as success.
- **S3-6.** Every private file written on a slice 3 path is created with
  `create_private_file`: simulator report reservations and snapshots,
  evaluations, and restore-drill evidence. Report ancestor checks refuse
  junctions.
- **S3-7.** On Windows the restore drill accepts exactly the local npipe form
  (D4). POSIX keeps `unix://`.
- **S3-8.** Each `sim-host-*` task fails fast on Windows with the D1 message.
- **S3-9.** The modules are byte-identical across both projects, and a test
  enforces it.
- **S3-10.** The listed test modules run on the Windows CI jobs and pass. The
  remaining skips state their reason.
- **S3-11.** The docs describe the Windows behavior, the checkout location
  (D5), and the operator setup. The docs are `getting-started.md` (Native
  Windows), `staging.md`, `simulation-host.md`, and the simulator README if it
  lists platforms.
- **S3-12.** `config.replacement_target_binding` behaves the same on Linux in
  production (G3). Its existing POSIX tests prove this, passing without any
  change to their POSIX fixtures or assertions.

## Verification limits

Windows CI exercises these with fakes and local files:

- the access-list logic;
- the job-object kill;
- the pipe threads;
- the npipe rule;
- the fail-fast messages.

CI does not run a live Staging reset, restore drill, or simulation against
Railway from Windows. Those runs need the maintainer's credentials. They stay
manual evidence, collected only if the maintainer chooses.

The security review could not confirm these Win32 behaviors from the
documentation. Windows CI tests them directly where possible:

- the default owner for elevated tokens;
- `TerminateJobObject` on an empty job;
- the thread count of a suspended process;
- whether a same-volume `os.replace` preserves the security descriptor;
- Docker Desktop's endpoint value.

## Risks

- **ctypes declarations.** Wrong structure layouts or argument types can fail
  silently. Mitigations:
  - explicit `argtypes` and `restype` on every function;
  - `use_last_error=True`, with every return value checked;
  - entry sizes and SIDs validated before they are parsed;
  - any unexpected result fails closed;
  - Windows CI exercising every branch.
- **Cases the rule does not model.** Some private setups are refused, for
  example an allow entry for a group whose only member is the operator. These
  refusals fail closed, and the docs list them.
- **A checkout another account can write (D5).** This is documented but not
  enforced, so an operator who ignores the docs is exposed to A2 through the
  code itself.
- **Nested jobs.** Windows 8 and later support them. If assignment fails,
  `attach` fails closed.
- **The production module change** (G3, S3-12). It is a two-way door, covered
  by the existing Linux tests and by review.

## Reversibility

Every change is a **two-way door**: local tooling, two vendored modules, and
tests. No data format, public API, or persistence change is involved. The
Windows access rule (D3, D6) and the npipe rule (D4) are the consequential
security decisions. Both were reviewed, and both are easy to tighten later.

## Security review record

An independent security review on 2026-10-15 returned **approve with
changes**. It found no BLOCKER or HIGH issues. The changes it asked for are
applied in this version. Three were MEDIUM:

- F1: report snapshots were not private;
- F2: the checkout location;
- F3: the Docker npipe endpoint.

The other five were LOW (F4–F8): the create flags and ancestor junctions, the
fail-closed contract details, the job-object conditions, decoding parity, and
the test plan.

The review approved the D6 inheritance refinement and recommended holding the
parent folder's handle open without delete sharing, in place of
`NtCreateFile` with `RootDirectory`.
