"""Fixed launcher-compatible transport to the private operator RPC socket."""

import argparse
import asyncio
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from .host_protocol import MAX_FRAME_BYTES, decode_frame, encode_frame
from .pool import LAUNCHER_TIMEOUT_SECONDS

_RESULTS = {
    "PASS",
    "FAIL_REQUEST",
    "FAIL_TARGET",
    "FAIL_INSUFFICIENT",
    "FAIL_SLOT",
    "FAIL_BOOTSTRAP",
    "FAIL_RUN_EXISTS",
    "FAIL_LEASE",
    "FAIL_DIRTY",
    "FAIL_INVARIANT",
    "FAIL_ERROR",
    "FAIL_RUN_UNKNOWN",
    "FAIL_ATTRIBUTION",
    "FAIL_STORAGE",
    "FAIL_VERIFY",
    "FAIL_LIMIT",
    "FAIL_LAUNCHER",
}


async def exchange(
    directory: Path, channel: str, request: dict[str, object]
) -> dict[str, object]:
    """Bound framing separately from the existing privileged execution reserve."""
    if not directory.is_absolute() or directory.is_symlink():
        raise ValueError
    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(directory / "rpc.sock", limit=MAX_FRAME_BYTES), 2
    )
    try:
        writer.write(
            encode_frame({"schema_version": 1, "channel": channel, "request": request})
        )
        await asyncio.wait_for(writer.drain(), 2)
        first = await asyncio.wait_for(reader.readexactly(1), LAUNCHER_TIMEOUT_SECONDS)
        raw = first + await asyncio.wait_for(reader.readline(), 2)
        reply = decode_frame(raw)
        if (
            set(reply) != {"result", "data"}
            or not isinstance(reply["result"], str)
            or reply["result"] not in _RESULTS
            or not isinstance(reply["data"], dict)
        ):
            raise ValueError
        return reply
    finally:
        writer.close()
        await writer.wait_closed()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel", choices=("pool", "fixture", "inspection"), required=True
    )
    parser.add_argument("--socket-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    reply: dict[str, object] = {"result": "FAIL_LAUNCHER", "data": {}}
    try:

        def expired(_signum: int, _frame: object) -> None:
            raise TimeoutError

        signal.signal(signal.SIGALRM, expired)
        signal.alarm(2)
        raw = sys.stdin.buffer.read(MAX_FRAME_BYTES + 1)
        signal.alarm(0)
        request = decode_frame(raw.rstrip(b"\n") + b"\n")
        reply = asyncio.run(exchange(args.socket_dir, args.channel, request))
    except (OSError, ValueError, TimeoutError, EOFError, asyncio.IncompleteReadError):
        pass
    finally:
        signal.alarm(0)
    sys.stdout.buffer.write(encode_frame(reply))
    return 0 if reply["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
