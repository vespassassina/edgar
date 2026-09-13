"""The error taxonomy (BLUEPRINT §17). Each error maps to an exit code [CLI-10].

Tool-level failures never raise: they return to the model as an error result.
These are for failures the harness itself cannot proceed through.
"""

from __future__ import annotations


class EdgarError(Exception):
    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        # Always say what to do next: a tool that prints "error: 401" has failed at its job.
        self.hint = hint


class ContextOverflow(EdgarError):
    exit_code = 1  # [CTX-12]


class UsageError(EdgarError):
    exit_code = 2


class ConfigError(EdgarError):
    exit_code = 3  # includes an untrusted project [PERM-13]


class ProviderError(EdgarError):
    exit_code = 4


class PermissionDenied(EdgarError):
    exit_code = 5


class BudgetExceeded(EdgarError):
    exit_code = 6


class Cancelled(EdgarError):
    exit_code = 7


class ToolFailure(EdgarError):
    exit_code = 8


class VerificationFailed(EdgarError):
    exit_code = 9  # [VER-5]
