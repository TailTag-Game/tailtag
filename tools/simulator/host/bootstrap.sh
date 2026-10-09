#!/usr/bin/env bash
# Deliver this trusted, secret-free file by authenticated SSH and verify its
# maintainer-issued SHA-256 before executing. Never retrieve arbitrary host code.
set -euo pipefail
umask 077
user= root= archive= metadata=
while (($#)); do
  case "$1" in
    --user) user=${2:?}; shift 2;;
    --root) root=${2:?}; shift 2;;
    --archive) archive=${2:?}; shift 2;;
    --metadata) metadata=${2:?}; shift 2;;
    *) echo bootstrap_rejected >&2; exit 1;;
  esac
done
[[ $EUID == 0 && $user =~ ^[a-z_][a-z0-9_-]{0,31}$ && $user != root ]]
[[ $root == /* && $archive == /* && $metadata == /* ]]
[[ $root != / && ! -L $root && ! -L $archive && ! -L $metadata ]]
# shellcheck disable=SC1091
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(dpkg --print-architecture) == amd64 ]]
id "$user" >/dev/null
# Validate paths before root installs/chowns anything; reject an existing root
# belonging to another service and every symlink ancestor.
python3 - "$root" "$archive" "$metadata" "$user" <<'PATHS'
import os, pathlib, pwd, stat, sys
root, archive, metadata = map(pathlib.Path, sys.argv[1:4])
owner = pwd.getpwnam(sys.argv[4]).pw_uid
for path in (root,archive,metadata):
    assert path.is_absolute() and '..' not in path.parts
    assert not any(p.is_symlink() for p in (path,*path.parents))
if root.exists():
    info = root.stat()
    assert root.is_dir() and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700
for path in (archive,metadata):
    info = path.stat()
    assert path.is_file() and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o600
# These are privileged install/chown destinations. Refuse existing incompatible
# state before any package, swap, SSH or filesystem configuration is changed.
for path in (root/'tools',root/'releases'):
    assert not path.is_symlink()
    if path.exists():
        info = path.stat()
        assert path.is_dir() and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700
for path, mode in ((root/'tools/uv',0o700),(root/'tools/versions.txt',0o600)):
    assert not path.is_symlink()
    if path.exists():
        info = path.stat()
        assert path.is_file() and info.st_uid == owner and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == mode
releases = root/'releases'
if releases.exists():
    for path in releases.iterdir():
        assert not path.is_symlink()
        info = path.stat()
        assert path.is_dir() and info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o700
PATHS
# Refuse host configurations that capture interactive credentials.
if grep -RqE '^[^#]*(log_input|log_output|pam_tty_audit)' /etc/sudoers /etc/sudoers.d /etc/pam.d 2>/dev/null; then
  echo bootstrap_tty_recording_rejected >&2; exit 1
fi
swapoff -a
# Persist disabled swap without deleting its backing data.
sed -i '/^[^#].*[[:space:]]swap[[:space:]]/s/^/# tailtag-disabled /' /etc/fstab
printf '* hard core 0\n* soft core 0\n' > /etc/security/limits.d/90-tailtag-core.conf
printf 'kernel.core_pattern=|/bin/false\nfs.suid_dumpable=0\n' > /etc/sysctl.d/90-tailtag-core.conf
sysctl --system >/dev/null
apt-get update
apt-get install -y ca-certificates curl gnupg python3
install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
printf 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n' > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y \
  docker-ce=5:29.9.0-1~ubuntu.24.04~noble \
  docker-ce-cli=5:29.9.0-1~ubuntu.24.04~noble \
  containerd.io=2.4.1-2~ubuntu.24.04~noble \
  docker-buildx-plugin=0.38.0-1~ubuntu.24.04~noble \
  docker-compose-plugin=5.6.0-1~ubuntu.24.04~noble
apt-mark hold docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker "$user"
printf 'Match User %s\n    AllowAgentForwarding no\n    AllowTcpForwarding no\n    AllowStreamLocalForwarding remote\n    StreamLocalBindMask 0177\n    StreamLocalBindUnlink no\n    PermitTunnel no\n    PermitTTY yes\nMatch all\n' "$user" > /etc/ssh/sshd_config.d/90-tailtag.conf
sshd -t
systemctl reload ssh
systemctl enable --now docker
install -d -o "$user" -g "$(id -gn "$user")" -m 0700 "$root" "$root/tools" "$root/releases"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
curl --fail --silent --show-error --location https://github.com/astral-sh/uv/releases/download/0.9.17/uv-x86_64-unknown-linux-gnu.tar.gz -o "$work/uv.tar.gz"
printf '%s  %s\n' 0114d54f9aafd07516cf1cadfe72afa970f5fd293fbe82dd924b8a7b42c984d8 "$work/uv.tar.gz" | sha256sum --check --status
tar -xzf "$work/uv.tar.gz" -C "$work"
install -o "$user" -g "$(id -gn "$user")" -m 0700 "$work/uv-x86_64-unknown-linux-gnu/uv" "$root/tools/uv"
# First install cannot import host_release before its verified venv exists.
# This dedicated stdlib validator executes no copied package code before hashes.
runuser -u "$user" -- python3 - "$root" "$archive" "$metadata" <<'PY'
import csv, hashlib, io, json, os, pathlib, re, selectors, signal, subprocess, sys, threading, time, uuid
root, archive, metadata = map(pathlib.Path, sys.argv[1:])
def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('bootstrap_rejected')
        result[key] = value
    return result
def read(path):
    if path.is_symlink() or path.stat().st_size > 65536: raise ValueError('bootstrap_rejected')
    return json.loads(path.read_text(), object_pairs_hook=pairs)
cancelled = threading.Event()
probe_deadline = None
def request_stop(_sig, _frame):
    cancelled.set()
for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
    signal.signal(sig, request_stop)
def reap(process):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try: os.killpg(process.pid, sig)
        except ProcessLookupError: pass
        try:
            process.wait(timeout=1)
            return
        except subprocess.TimeoutExpired: pass
    raise ValueError('bootstrap_rejected')
def run(args, *, timeout_seconds=30.0, cleanup=False, deadline=None, cwd=None):
    if not cleanup and cancelled.is_set(): raise ValueError('bootstrap_rejected')
    deadline = min(deadline, time.monotonic()+timeout_seconds) if deadline is not None else time.monotonic()+timeout_seconds
    if not cleanup and probe_deadline is not None: deadline = min(deadline, probe_deadline)
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, start_new_session=True,
        cwd=str(cwd if cwd is not None else root))
    output = bytearray()
    completed = False
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or (not cleanup and cancelled.is_set()): raise ValueError('bootstrap_rejected')
                for key, _ in selector.select(min(0.05, remaining)):
                    chunk = os.read(key.fd, min(65536, 65536-len(output)+1))
                    if not chunk: selector.unregister(key.fileobj)
                    elif len(output)+len(chunk) > 65536: raise ValueError('bootstrap_rejected')
                    else: output.extend(chunk)
            if process.returncode != 0 or time.monotonic() >= deadline: raise ValueError('bootstrap_rejected')
            completed = True
        return output.decode('utf-8')
    finally:
        if not completed or process.poll() is None: reap(process)
        if process.stdout is not None: process.stdout.close()
def remove_named(name: str) -> None:
    deadline = time.monotonic()+5.0
    try:
        run(['docker','rm','--force',name], cleanup=True, deadline=deadline)
        return
    except ValueError:
        if time.monotonic() >= deadline: raise
    remaining = run(['docker','ps','--all','--filter','name=^/'+name+'$','--format','{{.Names}}'], cleanup=True, deadline=deadline)
    if remaining.strip(): raise ValueError('bootstrap_rejected')
def validate_source(source, record, *, managed=False):
    assert isinstance(source,dict) and set(source) == {'simulator_sha','provenance','reason','runtime'}
    assert source['provenance'] == 'clean' and source['reason'] is None
    assert source['simulator_sha'] == {'value':record['simulator_sha'],'reason':None}
    runtime_source = source['runtime']
    assert isinstance(runtime_source,dict) and set(runtime_source) == {'python','httpx','dependency_lock_sha256'}
    for entry in runtime_source.values():
        assert isinstance(entry,dict) and set(entry) == {'value','reason'}
        assert isinstance(entry['value'],str) and entry['reason'] is None
    assert runtime_source['dependency_lock_sha256'] == {'value':record['dependency_lock_sha256'],'reason':None}
    if managed: assert runtime_source['python']['value'] == '3.13.11'
    else: assert re.fullmatch(r'3\.13\.[0-9]+', runtime_source['python']['value'])
def verify_runtime(runtime: pathlib.Path, record: dict) -> None:
    source = json.loads(run([str(runtime/'.venv/bin/python'),'-m','tailtag_simulator.provenance','inspect'], cwd=runtime), object_pairs_hook=pairs)
    validate_source(source, record, managed=True)
def probe_source(image: str, *, timeout_seconds: float=30.0) -> str:
    global probe_deadline
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image)
    assert type(timeout_seconds) in {int,float} and 0 < timeout_seconds <= 30
    previous = probe_deadline
    probe_deadline = time.monotonic() + timeout_seconds
    name = 'tailtag-sim-source-' + str(uuid.uuid4())
    try:
        try:
            output = run(['docker','run','--name',name,'--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--log-driver=none','--entrypoint','python',image,'-m','tailtag_simulator.provenance','inspect'])
        finally:
            remove_named(name)
        if cancelled.is_set(): raise ValueError('bootstrap_rejected')
        return output
    finally:
        probe_deadline = previous
def copy_runtime(image: str, runtime: pathlib.Path) -> None:
    info = runtime.lstat()
    assert runtime.is_dir() and not runtime.is_symlink() and info.st_uid == os.getuid()
    assert info.st_mode & 0o777 == 0o700 and not any(runtime.iterdir())
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image)
    mount = io.StringIO()
    csv.writer(mount).writerow(['type=bind','src='+str(runtime),'dst=/output'])
    code = "import os, shutil; os.umask(0o077); shutil.copytree('/app','/output',dirs_exist_ok=True,symlinks=True,copy_function=shutil.copyfile,ignore=lambda path,names:['.venv'] if path=='/app' else [])"
    name = 'tailtag-sim-copy-' + str(uuid.uuid4())
    try:
        run(['docker','run','--name',name,'--rm','--init','--user',f'{os.getuid()}:{os.getgid()}','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--log-driver=none','--ulimit','core=0:0','--mount',mount.getvalue().removesuffix('\r\n'),'--entrypoint','python',image,'-c',code], timeout_seconds=300.0)
    finally: remove_named(name)
record = read(metadata)
assert set(record) == {'schema_version','simulator_sha','dependency_lock_sha256','image_id','platform','archive_sha256'}
assert type(record['schema_version']) is int and record['schema_version'] == 1
assert record['platform'] == 'linux/amd64'
for key, pattern in [('simulator_sha',r'[0-9a-f]{40}'),('dependency_lock_sha256',r'[0-9a-f]{64}'),('archive_sha256',r'[0-9a-f]{64}'),('image_id',r'sha256:[0-9a-f]{64}')]:
    assert isinstance(record[key], str) and re.fullmatch(pattern, record[key])
assert not archive.is_symlink()
with archive.open('rb') as stream:
    assert hashlib.file_digest(stream,'sha256').hexdigest() == record['archive_sha256']
loaded = run(['docker','load','--input',str(archive)], timeout_seconds=300.0)
assert 'Loaded image ID: '+record['image_id'] in loaded.splitlines()
image = record['image_id']
inspection = json.loads(run(['docker','image','inspect',image]), object_pairs_hook=pairs)
assert len(inspection) == 1 and inspection[0]['Id'] == image
assert inspection[0]['Os'] == 'linux' and inspection[0]['Architecture'] == 'amd64'
source = json.loads(probe_source(image), object_pairs_hook=pairs)
validate_source(source, record)
runtime = root / 'releases' / record['simulator_sha']
fresh_copy = not runtime.exists()
if fresh_copy:
    runtime.mkdir(mode=0o700)
    copy_runtime(image, runtime)
assert not runtime.is_symlink() and runtime.stat().st_uid == os.getuid()
packaged = read(runtime / 'source.json')
assert set(packaged) == {'schema_version','simulator_sha','dependency_lock_sha256','manifest'}
assert type(packaged['schema_version']) is int and packaged['schema_version'] == 1
assert packaged['simulator_sha'] == record['simulator_sha']
assert packaged['dependency_lock_sha256'] == record['dependency_lock_sha256']
manifest = packaged['manifest']
assert isinstance(manifest,dict) and manifest
actual = {'pyproject.toml','uv.lock'}
for directory in ('tailtag_simulator','services/api/simulation_fixtures/images'):
    base = runtime / directory
    assert base.is_dir() and not base.is_symlink()
    for path in base.rglob('*'):
        assert not path.is_symlink()
        if any(p in {'__pycache__','.pytest_cache','.ruff_cache'} for p in path.parts) or path.suffix == '.md' or path.name == '.DS_Store': continue
        if path.is_file(): actual.add(path.relative_to(runtime).as_posix())
        else: assert path.is_dir()
assert set(manifest) == actual
for name, digest in manifest.items():
    relative = pathlib.Path(name)
    path = runtime / relative
    assert not relative.is_absolute() and '..' not in relative.parts
    assert path.resolve().is_relative_to(runtime.resolve()) and not path.is_symlink()
    assert not any(p.is_symlink() for p in path.parents if p.is_relative_to(runtime))
    assert isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
assert manifest['uv.lock'] == record['dependency_lock_sha256']
if fresh_copy:
    runtime.chmod(0o700, follow_symlinks=False)
    for path in runtime.rglob('*'):
        assert not path.is_symlink()
        path.chmod(0o700 if path.is_dir() else 0o600, follow_symlinks=False)
receipt = runtime / 'release.json'
if receipt.exists(): assert read(receipt) == record
else:
    fd = os.open(receipt, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(record,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
run([str(root/'tools/uv'),'sync','--directory',str(runtime),'--locked','--no-dev','--python','3.13.11','--managed-python'], timeout_seconds=300.0)
# Confirm the installed managed runtime directly; no nested Docker controller.
verify_runtime(runtime, record)
versions = run(['dpkg-query','-W','docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin','docker-compose-plugin'])
(root/'tools/versions.txt').write_text(versions + run([str(root/'tools/uv'),'--version']) + run([str(runtime/'.venv/bin/python'),'--version']) + run([str(runtime/'.venv/bin/python'),'-c',"import importlib.metadata; print('httpx='+importlib.metadata.version('httpx'))"]))
(root/'tools/versions.txt').chmod(0o600)
print(str(runtime/'.venv/bin/python'))
PY
