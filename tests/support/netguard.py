"""The offline suite's socket guard.

Installed in-process by the autouse ``no_network`` fixture and in e2e child
processes by ``sitecustomize.py``. Production code has no test switch; the guard
lives entirely here.
"""

from __future__ import annotations

import socket
import sys
from typing import Any, NoReturn


class NetworkBlocked(RuntimeError):
    pass


# Loopback addresses a test opened on purpose: the fixture server for a
# user-defined provider [PRV-12]. Only an exact (host, port) is let through, so a
# stray call to a local Ollama on its default port still fails.
ALLOWED: set[tuple[str, int]] = set()


def allow(host: str, port: int) -> None:
    ALLOWED.add((host, port))


def disallow(host: str, port: int) -> None:
    ALLOWED.discard((host, port))


def _allowed(address: Any) -> bool:
    return isinstance(address, tuple) and len(address) >= 2 and (address[0], address[1]) in ALLOWED


def _refuse(target: object) -> NoReturn:
    raise NetworkBlocked(
        f"offline test tried to reach {target!r}; use the fake provider or a cassette"
    )


def _called_from_socketpair() -> bool:
    # On Windows, socket.socketpair() is built from a loopback connect, and asyncio
    # needs it for its self-pipe. That one call is allowed; nothing else is.
    # On Windows the implementation is named _fallback_socketpair.
    frame = sys._getframe(2)
    return frame.f_code.co_name in {"socketpair", "_fallback_socketpair"} and (
        frame.f_globals.get("__name__") == "socket"
    )


def _connect(self: socket.socket, address: Any) -> None:
    unix = self.family == getattr(socket, "AF_UNIX", None)
    if unix or _called_from_socketpair() or _allowed(address):
        return _real_connect(self, address)
    _refuse(address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    unix = self.family == getattr(socket, "AF_UNIX", None)
    if unix or _called_from_socketpair() or _allowed(address):
        return _real_connect_ex(self, address)
    _refuse(address)


def _create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    if _allowed(address):
        return _real_create_connection(address, *args, **kwargs)
    _refuse(address)


def _getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
    if _allowed((host, int(port or 0))):
        return _real_getaddrinfo(host, port, *args, **kwargs)
    _refuse(host)


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection
_real_getaddrinfo = socket.getaddrinfo

PATCHES: list[tuple[object, str, object]] = [
    (socket.socket, "connect", _connect),
    (socket.socket, "connect_ex", _connect_ex),
    (socket, "create_connection", _create_connection),
    (socket, "getaddrinfo", _getaddrinfo),
]


def install(allowed: str = "") -> None:
    """`allowed` is "host:port,host:port", from EDGAR_TEST_NET_ALLOW in a child."""
    for item in filter(None, allowed.split(",")):
        host, _, port = item.rpartition(":")
        allow(host, int(port))
    for owner, name, replacement in PATCHES:
        setattr(owner, name, replacement)
