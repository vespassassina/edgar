"""The tool contract, MCP-shaped so MCP is a translation layer, not a second system [TOOL-1]."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from edgar.context.working import Working
from edgar.core.events import EventBus
from edgar.core.message import ErrorKind, ImageBlock
from edgar.permissions.matcher import Subject

if TYPE_CHECKING:
    from edgar.core.loop import Runtime
    from edgar.core.session import Session
    from edgar.extensions.hooks import Hook

Category = Literal["read", "write", "shell", "network", "memory", "agent"]

DEFAULT_TIMEOUT_S = 120.0  # [TOOL-3]


class Broker(Protocol):
    # v4's shape, not its import: `edgar.broker` is removable [NFR-12], so
    # this file never names it. `TicketGuard` matches this structurally.
    # A refusal is (caveat, reason); mypy's Protocol matching does not follow
    # a nested Protocol return type, so a plain tuple carries it instead.
    def check(
        self, *, tool: str, read_only: bool, subject: Subject, cwd: Path
    ) -> tuple[str, str] | None: ...
    def narrowed(
        self, *, subject: str, tools: tuple[str, ...], scope: tuple[str, ...]
    ) -> Broker: ...


@dataclass(frozen=True, slots=True)
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema
    kind: Literal["builtin", "command", "http", "mcp"]
    origin: str  # "builtin" | "project" | "user" | "ext:<name>" | "mcp:<server>"
    category: Category
    read_only: bool = False  # human assertion for command/http tools [TOOL-6]
    untrusted_output: bool = False  # fetch, http, mcp [TOOL-13]
    dangerous: bool = False  # default to ask even in auto mode


def builtin_schema(
    name: str,
    description: str,
    props: dict[str, Any],
    required: list[str],
    category: Category = "read",
    **flags: bool,
) -> ToolSchema:
    # Every built-in takes one JSON object with exactly the properties it names.
    shape: dict[str, Any] = {"type": "object", "properties": props, "required": required}
    shape["additionalProperties"] = False
    return ToolSchema(name, description, shape, "builtin", "builtin", category, **flags)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What a tool returns. The pipeline turns it into a ToolResultBlock."""

    text: str
    error: ErrorKind | None = None  # set when the tool itself reports failure
    exit_code: int | None = None  # for the ErrorRecord the harness computes [MEM-22]
    program: str | None = None
    image: ImageBlock | None = None  # a picture the call produced: `read` on a PNG


@dataclass(frozen=True, slots=True)
class ToolContext:
    cwd: Path
    bus: EventBus
    blob_dir: Path  # where spilled output goes [CTX-13]
    max_output_tokens: int
    timeout_s: float = DEFAULT_TIMEOUT_S
    mode: str = "ask"  # the calling session's mode, for a subagent to narrow [PERM-8]
    images: bool = False  # the model in use can see: `read` may answer with a picture
    depth: int = 0  # 0 is the main loop; the `task` tool checks it against the ceiling [SUB-6]
    chain: tuple[str, ...] = ()  # agent names already running in this call stack [SUB-10]
    budget_remaining: float | None = None  # what is left to inherit [SUB-7]
    hooks: tuple[Hook, ...] = ()  # `pre_tool` rules that may veto this call [EXT-6]
    working: Working | None = None  # the session's plan and todo list, for `todo` [CTX-18]
    network: bool = True  # what a sandbox is told about this call; set per call [PERM-15]
    broker: Broker | None = None  # v4, the ticket's own veto; None: no scope set [CAP-3]


def build_context(session: Session, rt: Runtime) -> ToolContext:
    """What every tool call in the turn gets, assembled once per turn."""
    cap = rt.budget.session_cost_cap
    remaining = None if cap is None else cap - (session.cost or 0.0)
    return ToolContext(
        cwd=session.cwd,
        bus=rt.bus,
        blob_dir=session.dir / "blobs",
        max_output_tokens=rt.max_output_tokens,
        mode=session.mode,
        images=rt.provider.capabilities.images,
        depth=session.depth,
        chain=session.agent_chain,
        budget_remaining=remaining,
        hooks=cast("tuple[Hook, ...]", rt.hooks),
        working=session.working,
        broker=rt.broker,
    )


class Tool(Protocol):
    @property
    def schema(self) -> ToolSchema: ...

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...
