"""Forbid network connections in a test without breaking event loops on Windows."""

import socket
from collections.abc import Callable

import pytest


def forbid_connect(
    monkeypatch: pytest.MonkeyPatch, trip: Callable[..., object]
) -> None:
    """Route every socket connect to `trip`, except socketpair's own setup.

    Windows has no native socketpair: Python emulates it with a loopback
    connect, which asyncio uses for its internal wake-up channel. That is not
    network work, so socketpair runs with the real connect.
    """
    real_connect = socket.socket.connect
    real_socketpair = socket.socketpair

    def socketpair(
        *args: object, **kwargs: object
    ) -> tuple[socket.socket, socket.socket]:
        socket.socket.connect = real_connect
        try:
            return real_socketpair(*args, **kwargs)  # pyright: ignore[reportArgumentType]
        finally:
            socket.socket.connect = trip  # pyright: ignore[reportAttributeAccessIssue]

    monkeypatch.setattr(socket.socket, "connect", trip)
    monkeypatch.setattr(socket, "socketpair", socketpair)
