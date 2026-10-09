"""Bootstrap forwarding policy against real Linux OpenSSH, without host setup.

Run on a disposable Linux host with TAILTAG_TEST_OPENSSH=1 as root. The portable
suite skips when this explicit prerequisite is absent; no Docker daemon needed.
"""

import os
import pwd
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest


def test_bootstrap_allows_remote_unix_but_refuses_remote_and_local_tcp() -> None:
    if (
        os.environ.get("TAILTAG_TEST_OPENSSH") != "1"
        or sys.platform != "linux"
        or os.geteuid() != 0
        or not all(
            shutil.which(cmd)
            for cmd in ("bash", "ssh", "sshd", "ssh-keygen", "useradd", "userdel")
        )
        or not Path("/run/sshd").is_dir()
    ):
        pytest.skip("requires opted-in disposable Linux root host with OpenSSH")

    children: list[subprocess.Popen[bytes]] = []
    user = "ttssh" + uuid.uuid4().hex[:12]
    account_created = False
    with tempfile.TemporaryDirectory(prefix="tailtag-ssh-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        home = root / "home"
        home.mkdir()
        try:
            subprocess.run(
                [
                    "useradd",
                    "--home-dir",
                    str(home),
                    "--no-create-home",
                    "--shell",
                    "/bin/sh",
                    "--password",
                    "x",
                    user,
                ],
                check=True,
                capture_output=True,
                timeout=5,
            )
            account_created = True
            account = pwd.getpwnam(user)
            os.chown(home, account.pw_uid, account.pw_gid)
            home.chmod(0o700)
            key, host_key = root / "client", root / "host"
            for destination in (key, host_key):
                subprocess.run(
                    [
                        "ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(destination),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            authorized = home / "authorized_keys"
            authorized.write_bytes(key.with_suffix(".pub").read_bytes())
            authorized.chmod(0o644)

            # Execute the actual policy emitter. Replace only its privileged
            # output destination; never run package/swap/root bootstrap actions.
            bootstrap = (Path(__file__).parents[1] / "host/bootstrap.sh").read_text()
            destination = "/etc/ssh/sshd_config.d/90-tailtag.conf"
            (emitter,) = (
                line
                for line in bootstrap.splitlines()
                if line.endswith("> " + destination)
            )
            policy = root / "policy.conf"
            subprocess.run(
                [
                    "bash",
                    "-c",
                    'user="$1"; '
                    + emitter.removesuffix(destination)
                    + shlex.quote(str(policy)),
                    "policy",
                    user,
                ],
                check=True,
                capture_output=True,
                timeout=5,
            )
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            config = root / "sshd.conf"
            config.write_text(
                f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n"
                f"PidFile {root / 'sshd.pid'}\nAuthorizedKeysFile {authorized}\n"
                "PasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\n"
                f"AllowUsers {user}\nInclude {policy}\n"
            )
            sshd = shutil.which("sshd")
            assert sshd is not None
            subprocess.run(
                [sshd, "-t", "-f", str(config)],
                check=True,
                capture_output=True,
                timeout=5,
            )
            with (
                (root / "sshd.log").open("wb") as daemon_log,
                (root / "ssh.log").open("wb") as client_log,
            ):
                daemon = subprocess.Popen(
                    [sshd, "-D", "-e", "-f", str(config)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=daemon_log,
                    start_new_session=True,
                )
                children.append(daemon)
                deadline = time.monotonic() + 5
                while True:
                    assert daemon.poll() is None, (root / "sshd.log").read_text()
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        assert time.monotonic() < deadline, "test sshd did not start"
                        time.sleep(0.02)
                ssh = [
                    "ssh",
                    "-F",
                    "/dev/null",
                    "-p",
                    str(port),
                    "-i",
                    str(key),
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "ConnectTimeout=2",
                    "-o",
                    "ExitOnForwardFailure=yes",
                ]
                remote = home / "relay.sock"
                with socket.socket(socket.AF_UNIX) as target:
                    target.bind(str(root / "target.sock"))
                    target.listen()
                    target.settimeout(3)
                    tunnel = subprocess.Popen(
                        ssh
                        + [
                            "-N",
                            "-R",
                            f"{remote}:{root / 'target.sock'}",
                            f"{user}@127.0.0.1",
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=client_log,
                        start_new_session=True,
                    )
                    children.append(tunnel)
                    deadline = time.monotonic() + 5
                    while not remote.exists():
                        assert tunnel.poll() is None, (root / "ssh.log").read_text() + (
                            root / "sshd.log"
                        ).read_text()
                        assert time.monotonic() < deadline, (
                            "remote Unix forwarding was not established"
                        )
                        time.sleep(0.02)
                    assert stat.S_IMODE(remote.stat().st_mode) == 0o600
                    with socket.socket(socket.AF_UNIX) as forwarded:
                        forwarded.settimeout(3)
                        forwarded.connect(str(remote))
                        forwarded.sendall(b"tailtag-relay-request")
                        connection, _ = target.accept()
                        with connection:
                            connection.settimeout(3)
                            assert connection.recv(1024) == b"tailtag-relay-request"
                            connection.sendall(b"tailtag-relay-response")
                        assert forwarded.recv(1024) == b"tailtag-relay-response"

                # A live endpoint prevents absence of a destination from passing
                # the negative checks. -W uses local forwarding's direct-tcpip.
                with socket.socket() as forbidden:
                    forbidden.bind(("127.0.0.1", 0))
                    forbidden.listen()
                    address = f"127.0.0.1:{forbidden.getsockname()[1]}"
                    for forwarding in (["-N", "-R", f"0:{address}"], ["-W", address]):
                        rejected = subprocess.run(
                            ssh + forwarding + [f"{user}@127.0.0.1"],
                            input=b"forbidden-tcp",
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                        assert rejected.returncode != 0, "TCP forwarding was accepted"
                        assert rejected.stdout == b""
                        diagnostic = rejected.stderr.decode()
                        assert (
                            "remote port forwarding failed" in diagnostic
                            if "-R" in forwarding
                            else "administratively prohibited" in diagnostic
                        ), diagnostic
                    forbidden.settimeout(0.2)
                    with pytest.raises(TimeoutError):
                        forbidden.accept()
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
            if account_created:
                subprocess.run(
                    ["userdel", user], check=True, capture_output=True, timeout=5
                )
