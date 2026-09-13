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


def _refuse(target: object) -> NoReturn:
    raise NetworkBlocked(
        f"offline test tried to reach {target!r}; use the fake provider or a cassette"
    )


def _called_from_socketpair() -> bool:
    # On Windows, socket.socketpair() is built from a loopback connect, and asyncio
    # needs it for its self-pipe. That one call is allowed; nothing else is.
    frame = sys._getframe(2)
    return frame.f_code.co_name == "socketpair" and frame.f_globals.get("__name__") == "socket"


def _connect(self: socket.socket, address: Any) -> None:
    if self.family == getattr(socket, "AF_UNIX", None) or _called_from_socketpair():
        return _real_connect(self, address)
    _refuse(address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    if self.family == getattr(socket, "AF_UNIX", None) or _called_from_socketpair():
        return _real_connect_ex(self, address)
    _refuse(address)


def _create_connection(address: Any, *args: Any, **kwargs: Any) -> NoReturn:
    _refuse(address)


def _getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> NoReturn:
    _refuse(host)


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex

PATCHES: list[tuple[object, str, object]] = [
    (socket.socket, "connect", _connect),
    (socket.socket, "connect_ex", _connect_ex),
    (socket, "create_connection", _create_connection),
    (socket, "getaddrinfo", _getaddrinfo),
]


def install() -> None:
    for owner, name, replacement in PATCHES:
        setattr(owner, name, replacement)
