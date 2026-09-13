from __future__ import annotations

import asyncio
import socket

import netguard
import pytest


def test_create_connection_is_blocked() -> None:
    with pytest.raises(netguard.NetworkBlocked):
        socket.create_connection(("example.com", 443))


def test_name_resolution_is_blocked() -> None:
    with pytest.raises(netguard.NetworkBlocked):
        socket.getaddrinfo("example.com", 443)


def test_raw_connect_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s,
        pytest.raises(netguard.NetworkBlocked),
    ):
        s.connect(("127.0.0.1", 9))


def test_loopback_socketpair_is_allowed() -> None:
    # The loopback implementation Windows uses. Recent CPython defines it on every
    # platform, so a regression shows up without waiting for the Windows job; older
    # 3.12 patch releases define it on Windows only.
    pair = getattr(socket, "_fallback_socketpair", socket.socketpair)
    a, b = pair()
    with a, b:
        a.sendall(b"x")
        assert b.recv(1) == b"x"


def test_asyncio_still_runs() -> None:
    # asyncio's self-pipe is a socketpair, which on Windows is a loopback connect.
    async def answer() -> int:
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(answer()) == 42
