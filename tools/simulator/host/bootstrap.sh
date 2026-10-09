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
import hashlib, json, os, pathlib, re, shutil, subprocess, sys
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
def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, cwd=str(runtime) if 'runtime' in globals() and 'tailtag_simulator.host_release' in args else str(root)).stdout
record = read(metadata)
assert set(record) == {'schema_version','simulator_sha','dependency_lock_sha256','image_id','platform','archive_sha256'}
assert type(record['schema_version']) is int and record['schema_version'] == 1
assert record['platform'] == 'linux/amd64'
for key, pattern in [('simulator_sha',r'[0-9a-f]{40}'),('dependency_lock_sha256',r'[0-9a-f]{64}'),('archive_sha256',r'[0-9a-f]{64}'),('image_id',r'sha256:[0-9a-f]{64}')]:
    assert isinstance(record[key], str) and re.fullmatch(pattern, record[key])
assert not archive.is_symlink()
with archive.open('rb') as stream:
    assert hashlib.file_digest(stream,'sha256').hexdigest() == record['archive_sha256']
loaded = run(['docker','load','--input',str(archive)])
assert 'Loaded image ID: '+record['image_id'] in loaded.splitlines()
image = record['image_id']
inspection = json.loads(run(['docker','image','inspect',image]), object_pairs_hook=pairs)
assert len(inspection) == 1 and inspection[0]['Id'] == image
assert inspection[0]['Os'] == 'linux' and inspection[0]['Architecture'] == 'amd64'
source = json.loads(run(['docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--log-driver=none','--entrypoint','python',image,'-m','tailtag_simulator.provenance','inspect']), object_pairs_hook=pairs)
assert set(source) == {'simulator_sha','provenance','reason','runtime'}
assert source['provenance'] == 'clean' and source['reason'] is None
assert source['simulator_sha'] == {'value':record['simulator_sha'],'reason':None}
assert source['runtime']['dependency_lock_sha256'] == {'value':record['dependency_lock_sha256'],'reason':None}
assert source['runtime']['python']['reason'] is None and re.fullmatch(r'3\.13\.[0-9]+',source['runtime']['python']['value'])
runtime = root / 'releases' / record['simulator_sha']
if not runtime.exists():
    runtime.mkdir(mode=0o700)
    container = run(['docker','create',image]).strip()
    assert re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}',container)
    try: run(['docker','cp',container+':/app/.',str(runtime)])
    finally: run(['docker','rm',container])
    copied_venv = runtime / '.venv'
    if copied_venv.is_symlink(): copied_venv.unlink()
    elif copied_venv.exists(): shutil.rmtree(copied_venv)
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
for path in runtime.rglob('*'):
    if path.is_relative_to(runtime/'.venv'): continue
    assert not path.is_symlink()
    path.chmod(0o700 if path.is_dir() else 0o600)
receipt = runtime / 'release.json'
if receipt.exists(): assert read(receipt) == record
else:
    fd = os.open(receipt, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(record,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
run([str(root/'tools/uv'),'sync','--directory',str(runtime),'--locked','--no-dev','--python','3.13.11','--managed-python'])
# Subsequent operation uses the single production release-verification path.
os.chdir(runtime)
run([str(runtime/'.venv/bin/python'),'-m','tailtag_simulator.host_release','install-runtime','--archive',str(archive),'--metadata',str(metadata),'--root',str(root)])
versions = subprocess.run(['dpkg-query','-W','docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin','docker-compose-plugin'],check=True,capture_output=True,text=True).stdout
(root/'tools/versions.txt').write_text(versions + run([str(root/'tools/uv'),'--version']) + run([str(runtime/'.venv/bin/python'),'--version']) + run([str(runtime/'.venv/bin/python'),'-c',"import importlib.metadata; print('httpx='+importlib.metadata.version('httpx'))"]))
(root/'tools/versions.txt').chmod(0o600)
print(str(runtime/'.venv/bin/python'))
PY
