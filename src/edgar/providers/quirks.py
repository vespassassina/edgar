"""How providers differ, as data [PRV-3, ADR-0002, ADR-0020].

`openai_compat.py` reads these fields and never a provider's name, so a new server
is a row here or a `[providers.NAME]` block in config, not a branch in code. The
defaults are the conservative ones: a user-defined server states only what it
knows [PRV-12].
"""

# Where a provider's credential comes from, checked by `connect` before any request:
#
#   a key in the environment variable api_key_env         -> sent as the row says
#   otherwise, if the user's config names api_key_command  -> run it, send its output
#       as a bearer token, and run it again once that token is ten minutes old
#   otherwise, if the row needs a key                      -> stop, naming the variable
#
# The command is how clouds that sign in with an identity instead of a key work:
# `az account get-access-token`, `gcloud auth print-access-token`, or AWS's Bedrock
# token generator. Their own CLIs do the sign-in, the MFA and the refresh; edgar
# only runs what the user named, like a command tool: no shell, and no SDK [PRV-20].

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from edgar.config.schema import ProviderSection
from edgar.core.errors import ConfigError


@dataclass(frozen=True, slots=True)
class Quirks:
    base_url: str | None  # None: the user must configure it (Azure)
    api_key_env: str | None = None  # None: no key sent
    api_key_command: list[str] | None = None  # prints a short-lived token [PRV-20]
    base_url_env: str | None = None  # where else base_url may come from
    auth_style: Literal["bearer", "api-key", "none"] = "bearer"
    api_version: str | None = None  # Azure: ?api-version=, and the model is the deployment
    native_tools: bool = True  # False: tools are described in text, calls parsed by repair.py
    parallel_tools: bool = False
    stream_usage: bool = False  # ask for usage in the final stream chunk
    max_context: int = 32_768
    max_output: int = 4_096
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] | None = None
    cost_source: Literal["table", "response", "free"] = "table"
    reasoning: bool = False  # the server streams reasoning text back
    thinking_budget: int | None = None  # Anthropic: request extended thinking


QUIRKS: dict[str, Quirks] = {
    "openai": Quirks(
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        parallel_tools=True,
        stream_usage=True,
        max_context=128_000,
        max_output=16_384,
    ),
    "azure": Quirks(
        None,
        "AZURE_OPENAI_API_KEY",
        base_url_env="AZURE_OPENAI_ENDPOINT",
        auth_style="api-key",
        api_version="2024-10-21",
        parallel_tools=True,
        stream_usage=True,
        max_context=128_000,
        max_output=16_384,
    ),
    "openrouter": Quirks(
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        parallel_tools=True,
        stream_usage=True,
        max_context=128_000,
        max_output=16_384,
        cost_source="response",
        reasoning=True,
    ),
    # Ollama's own context window is set on the server (OLLAMA_CONTEXT_LENGTH) and it
    # truncates silently past it, so say here what the server really has.
    "ollama": Quirks(
        "http://localhost:11434/v1",
        auth_style="none",
        stream_usage=True,
        max_context=8_192,
        cost_source="free",
        reasoning=True,
    ),
    # Its own adapter and wire format; only the fields above that it reads matter.
    "anthropic": Quirks(
        "https://api.anthropic.com",
        "ANTHROPIC_API_KEY",
        parallel_tools=True,
        max_context=200_000,
        max_output=16_384,
        reasoning=True,
    ),
}

_NOT_QUIRKS = {"kind", "prompt_profile"}


def quirks_for(name: str, block: ProviderSection | None) -> Quirks:
    """The built-in row for `name`, with the config block's keys laid over it. A new
    name starts from the conservative defaults, or Anthropic's row for kind anthropic."""
    base = QUIRKS.get(name)
    if base is None:
        if block is None or block.base_url is None:
            raise ConfigError(
                f"[providers.{name}] needs base_url",
                hint=f'for example: [providers.{name}] kind = "openai-compatible", '
                'base_url = "http://localhost:1234/v1"',
            )
        auth: Literal["bearer", "none"] = "bearer" if block.api_key_env else "none"
        base = Quirks(block.base_url, auth_style=auth, reasoning=True)
        if block.kind == "anthropic":
            base = QUIRKS["anthropic"]
    if block is None:
        return base
    stated = {
        f.name: getattr(block, f.name)
        for f in dataclasses.fields(block)
        if f.name not in _NOT_QUIRKS and getattr(block, f.name) is not None
    }
    return dataclasses.replace(base, **stated)


SIGN_IN = "sign in with the cloud's own CLI first: az login, gcloud auth login, aws sso login"


@dataclass
class Minted:
    argv: list[str]  # the user's command, e.g. ["gcloud", "auth", "print-access-token"]
    value: str = field(default="", repr=False)  # the token: never in a repr or a log
    at: float = -1e9  # when it last ran, by the monotonic clock

    def token(self) -> str:
        if time.monotonic() - self.at < 600:  # fresh enough: a cloud token lasts an hour
            return self.value
        # 1. Run it directly, never through a shell; `which` finds az.cmd on Windows.
        argv = [shutil.which(self.argv[0]) or self.argv[0], *self.argv[1:]]
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:  # missing, or hung: a failure too
            done = subprocess.CompletedProcess(argv, 1, "", str(exc))
        # 2. It must succeed and print the token, which is its whole output.
        if done.returncode or not done.stdout.strip():
            why = (done.stderr.strip().splitlines() or ["it printed nothing"])[-1]
            raise ConfigError(f"api_key_command {self.argv[0]!r} failed: {why}", hint=SIGN_IN)
        self.value, self.at = done.stdout.strip(), time.monotonic()
        return self.value


type Key = str | Minted | None  # a key as set, or a command's token


def connect(name: str, quirks: Quirks, env: Mapping[str, str]) -> tuple[Quirks, Key]:
    """The endpoint and the key, checked before any request, so a missing key costs
    no network call. Keys live in the environment, never in config [CFG-6]."""
    if quirks.base_url is None:
        # Azure has one host per resource, and edgar never guesses a host [PRV-15].
        url = env.get(quirks.base_url_env or "")
        if not url:
            raise ConfigError(
                f"{name}: no endpoint configured",
                hint=f"set base_url in [providers.{name}], or {quirks.base_url_env}",  # Azure's
            )
        quirks = dataclasses.replace(quirks, base_url=url)
    key: Key = env.get(quirks.api_key_env) if quirks.api_key_env else None
    if not key and quirks.api_key_command:
        # No key set: mint a token now, so a lapsed sign-in fails before any request,
        # and send it as a bearer token, the way every cloud takes one.
        key = Minted(quirks.api_key_command)
        key.token()
        quirks = dataclasses.replace(quirks, auth_style="bearer")
    if quirks.api_key_env and not key and quirks.auth_style != "none":
        raise ConfigError(
            f"{name}: the API key variable {quirks.api_key_env} is not set",
            hint=f"export {quirks.api_key_env}=…, or set api_key_command in ~/.edgar/config.toml",
        )
    return quirks, key
