from __future__ import annotations

# Kept in step with pyproject.toml by tests/unit/test_version.py. Reading it from
# importlib.metadata instead would cost startup time on every run (NFR-1).
__version__ = "0.0.1"
