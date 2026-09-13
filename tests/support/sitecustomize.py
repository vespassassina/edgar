"""Runs at interpreter start in e2e child processes, via PYTHONPATH.

A monkeypatch does not cross a process boundary, so the ``subprocess_env`` fixture
puts this directory on the child's path and the same guard is installed there.
"""

from __future__ import annotations

import netguard

netguard.install()
