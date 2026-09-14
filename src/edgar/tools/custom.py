"""Command and HTTP tools, declared in TOML: a CLI or an API for the agent, without
MCP and without Python [TOOL-6, ADR-0018, ADR-0033].

A **command tool** is an argv template. Each validated argument is substituted
into whole argv elements and the program is started directly, never through a
shell, so `; rm -rf ~` in an argument is one odd argument, not a second command.

An **HTTP tool** is a request template whose scheme and host are fixed. Arguments
fill only path, query and body slots; `${env:NAME}` fills only the URL's base and
headers, from the environment, and every value it resolves is scrubbed from
what the tool returns.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from edgar.core.errors import ConfigError
from edgar.permissions.matcher import Subject
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.builtin.shell import run_argv

_SLOT = re.compile(r"\{(\w+)\}")
_ENV = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KEYS = {"name", "description", "input", "timeout_s", "read_only"}
_COMMAND, _HTTP = {"argv"}, {"method", "url", "headers", "body"}
SECRETS: set[str] = set()  # every value ${env:…} resolved, for scrub()


def expand(text: str) -> str:
    """`${env:NAME}` read from the environment, for an HTTP tool's headers and an MCP
    server's env and headers. Every value it resolves is remembered for scrub()."""

    def value(match: re.Match[str]) -> str:
        found = os.environ.get(match[1])
        if found is None:
            raise KeyError(f"environment variable {match[1]} is not set")
        if len(found) >= 4:
            SECRETS.add(found)
        return found

    return _ENV.sub(value, text)


def scrub(text: str) -> str:
    for secret in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    return text


def load(folders: Iterable[tuple[Path, str]]) -> list[CommandTool | HttpTool]:
    """Every `*.toml` in each folder; `origin` is "user" or "project"."""
    tools: list[CommandTool | HttpTool] = []
    for folder, origin in folders:
        for path in sorted(folder.glob("*.toml")) if folder.is_dir() else []:
            tools.append(_build(path, origin))
    return tools


def _build(path: Path, origin: str) -> CommandTool | HttpTool:
    def bad(problem: str) -> ConfigError:
        return ConfigError(f"{path}: {problem}", hint="see BLUEPRINT §6.4 for the format")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise bad(f"not valid TOML: {exc}") from None
    extra = set(data) - _KEYS - _COMMAND - _HTTP
    if extra:
        raise bad(f"unknown keys {', '.join(sorted(extra))}")
    if not _NAME.match(str(data.get("name", ""))) or not isinstance(data.get("description"), str):
        raise bad("needs a name ([A-Za-z0-9_-]) and a description")
    schema_in = data.get("input", {"type": "object", "properties": {}})
    if not isinstance(schema_in, dict) or schema_in.get("type") != "object":
        raise bad('[input] must be a JSON Schema with type = "object"')
    command = isinstance(data.get("argv"), list)
    if command == ("url" in data):
        raise bad("needs either argv (a command tool) or url (an HTTP tool)")
    read_only = bool(data.get("read_only", False))
    schema = ToolSchema(
        name=data["name"],
        description=data["description"],
        input_schema=schema_in,
        kind="command" if command else "http",
        origin=origin,
        category="shell" if command else "network",
        read_only=read_only,
        untrusted_output=not command,  # a response from the network [TOOL-13]
    )
    timeout = float(data.get("timeout_s", 60))
    if command:
        if not data["argv"] or not all(isinstance(a, str) for a in data["argv"]):
            raise bad("argv must be a non-empty list of strings")
        return CommandTool(schema, data["argv"], timeout)
    host = urlsplit(_ENV.sub("x", data["url"])).netloc
    if not urlsplit(data["url"]).scheme.startswith("http") or _SLOT.search(host):
        raise bad("url must be http(s) with a fixed host; arguments fill only path and query")
    headers = data.get("headers", {})
    if _SLOT.search(json.dumps(headers)):
        raise bad("headers take ${env:NAME}, never arguments")
    method = str(data.get("method", "GET")).upper()
    return HttpTool(schema, method, data["url"], headers, data.get("body"), timeout)


def _fill(template: str, args: dict[str, Any], encode: bool = False) -> str:
    def value(match: re.Match[str]) -> str:
        text = str(args.get(match[1], ""))
        return quote(text, safe="") if encode else text

    return _SLOT.sub(value, template)


class CommandTool:
    def __init__(self, schema: ToolSchema, argv: list[str], timeout_s: float) -> None:
        self.schema, self.argv, self.timeout_s = schema, argv, timeout_s

    def render(self, args: dict[str, Any]) -> list[str]:
        """Whole argv elements; an element naming an absent argument is dropped."""
        return [
            _fill(part, args)
            for part in self.argv
            if all(name in args for name in _SLOT.findall(part))
        ]

    def subject(self, args: dict[str, Any], cwd: Path) -> Subject:
        line = shlex.join(self.render(args))
        return Subject(line, command=line)

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        argv = self.render(args)
        program = Path(argv[0]).name
        try:
            code, out = await run_argv(argv, ctx.cwd)
        except FileNotFoundError:
            return ToolResult(f"{argv[0]} is not installed or not on PATH", "not_found")
        return ToolResult(f"exit {code}\n{out}", "nonzero_exit" if code else None, code, program)


class HttpTool:
    def __init__(
        self,
        schema: ToolSchema,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
        timeout_s: float,
    ) -> None:
        self.schema, self.method, self.url = schema, method, url
        self.headers, self.body, self.timeout_s = headers, body, timeout_s

    def subject(self, args: dict[str, Any], cwd: Path) -> Subject:
        return Subject(_fill(self.url, args, encode=True))  # ${env:…} left unresolved

    def _body(self, node: Any, args: dict[str, Any]) -> Any:
        if isinstance(node, str):
            whole = _SLOT.fullmatch(node)
            return args.get(whole[1]) if whole else _fill(node, args)
        if isinstance(node, dict):
            return {k: self._body(v, args) for k, v in node.items()}
        if isinstance(node, list):
            return [self._body(v, args) for v in node]
        return node

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        import httpx  # only runs that call an HTTP tool pay for it (NFR-1)

        try:
            url = _fill(expand(self.url), args, encode=True)  # env first: args never reach it
            headers = {k: expand(v) for k, v in self.headers.items()}
        except KeyError as missing:
            return ToolResult(f"environment variable {missing} is not set", "validation")
        if urlsplit(url).netloc != urlsplit(expand(self.url)).netloc:
            return ToolResult("an argument tried to change the host", "validation")
        body = self._body(self.body, args) if self.body is not None else None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.request(self.method, url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            return ToolResult(scrub(f"request failed: {exc}"), "provider_http")
        text = scrub(f"HTTP {response.status_code}\n{response.text[:2_000_000]}")
        return ToolResult(text, "provider_http" if response.status_code >= 400 else None)
