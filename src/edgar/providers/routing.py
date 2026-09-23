# Which model runs this? A pure function over config [ROUTE-1..4, ADR-0013].
#
# Core binds roles statically: each auxiliary role uses its own [model] key, or
# the main model when it has none. Declarative [[route]] rules join in v1, with
# the same first-match-wins shape as permissions.decide() — one pattern to
# learn rather than two [ROUTE-2]. Capability validation [ROUTE-6] is a separate
# step the caller takes after resolving the selected model's provider, not part
# of this function: keeping select_model() free of I/O is what makes it a zero-
# cost, exhaustively testable pure function [ROUTE-3, ROUTE-4].

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from edgar.config.schema import Mode, ModelSection
from edgar.core.errors import ConfigError

Role = Literal["main", "subagent", "compactor", "controller", "condenser"]


@dataclass(frozen=True, slots=True)
class RoutingContext:
    role: Role = "main"
    agent: str | None = None
    agent_model: str | None = None  # a subagent's frontmatter `model:` (Core)
    mode: Mode = "ask"
    tools_required: bool = False
    prompt_tokens: int = 0
    budget_remaining_fraction: float = 1.0
    tags: frozenset[str] = field(default_factory=frozenset)
    schedule: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    # One [[route]] rule [ROUTE-2]. Every condition left as None (or an
    # empty tags) matches anything; the rule matches when every set condition does.

    name: str
    model: str
    role: Role | None = None
    agent: str | None = None
    mode: Mode | None = None
    tools_required: bool | None = None
    prompt_tokens_lt: int | None = None
    prompt_tokens_gt: int | None = None
    budget_remaining_lt: float | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    schedule: str | None = None


@dataclass(frozen=True, slots=True)
class Selection:
    model: str
    rule: str  # matched rule's name, "agent", "role" or "default"
    reason: str  # rendered by `edgar route explain` [ROUTE-9]


def select_model(
    ctx: RoutingContext, models: ModelSection, rules: tuple[Route, ...] = ()
) -> Selection:
    # 1. A subagent that names its own model always wins: the most specific
    #    choice, made by whoever wrote the agent file.
    if ctx.role == "subagent" and ctx.agent_model:
        return Selection(ctx.agent_model, "agent", f"agent {ctx.agent} names its model")
    # 2. First matching declarative rule [ROUTE-2].
    for rule in rules:
        if matches(rule, ctx):
            return Selection(rule.model, rule.name, f"[[route]] {rule.name!r} matched")
    # 3. The role's own static binding, Core's mechanism [ROUTE-1].
    own = getattr(models, ctx.role, None) if ctx.role not in ("main", "subagent") else None
    if own:
        return Selection(own, "role", f"[model] {ctx.role}")
    # 4. The global default, or a hard error if nobody configured one.
    if models.default is None:
        raise ConfigError(
            "no model configured",
            hint="pass --model provider/model, or set [model] default in .edgar/config.toml",
        )
    why = "" if ctx.role == "main" else f"; {ctx.role} has no model of its own"
    return Selection(models.default, "default", f"[model] default{why}")


def matches(rule: Route, ctx: RoutingContext) -> bool:
    # True when every condition this rule sets holds. Public because
    # `edgar route explain` shows the verdict rule by rule [ROUTE-9].
    return (
        (rule.role is None or rule.role == ctx.role)
        and (rule.agent is None or rule.agent == ctx.agent)
        and (rule.mode is None or rule.mode == ctx.mode)
        and (rule.tools_required is None or rule.tools_required == ctx.tools_required)
        and (rule.prompt_tokens_lt is None or ctx.prompt_tokens < rule.prompt_tokens_lt)
        and (rule.prompt_tokens_gt is None or ctx.prompt_tokens > rule.prompt_tokens_gt)
        and (
            rule.budget_remaining_lt is None
            or ctx.budget_remaining_fraction < rule.budget_remaining_lt
        )
        and (not rule.tags or bool(rule.tags & ctx.tags))
        and (rule.schedule is None or rule.schedule == ctx.schedule)
    )


def check_capabilities(selection: Selection, *, tools_required: bool, has_tools: bool) -> None:
    # A hard error at selection, never a confusing mid-stream failure [ROUTE-6].
    if tools_required and not has_tools:
        raise ConfigError(
            f"routing picked {selection.model!r} ({selection.rule}) for a task that "
            "needs tools, but that model has no tool support",
            hint="add a [[route]] rule that points tool-requiring work elsewhere, "
            "or configure a model with tool support",
        )


def check_images(model: str, *, has_images: bool) -> None:
    # The same rule as tool support, for pictures: the model in use either takes an
    # image or the prompt does not run. Never a silent drop [ROUTE-6, ADR-0052].
    if not has_images:
        raise ConfigError(
            f"{model!r} cannot take images, and this prompt attaches one",
            hint="choose a model that sees images, or leave the image out; a "
            "server that does take them says images = true in [providers.NAME]",
        )


def routes_from_config(later: dict[str, Any]) -> tuple[Route, ...]:
    # [[route]] arrives in Config.later["route"] as a list of raw tables
    # (config/schema.py's LATER); this is where v1 finally reads it.
    raw = later.get("route", [])
    if not isinstance(raw, list):
        raise ConfigError('[[route]] must be an array of tables, written "[[route]]"')
    return tuple(_route(i, entry) for i, entry in enumerate(raw))


def _route(index: int, entry: Any) -> Route:
    if not isinstance(entry, dict):
        raise ConfigError(f"[[route]] rule {index}: must be a table")
    name = entry.get("name", f"route-{index}")
    model = entry.get("model")
    if not isinstance(name, str) or not isinstance(model, str) or not model:
        raise ConfigError(f'[[route]] rule {index}: needs model = "provider/model"')
    # Every other key is a Route field of the same name, so a misspelt condition
    # fails loudly here instead of silently matching everything.
    try:
        return Route(**{**entry, "name": name, "tags": frozenset(entry.get("tags", []))})
    except TypeError as exc:
        raise ConfigError(f"[[route]] {name!r}: {exc}") from None
