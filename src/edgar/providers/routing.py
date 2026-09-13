"""Which model runs this? A pure function over config [ROUTE-1, ADR-0013].

Core binds roles statically: each auxiliary role uses its own `[model]` key, or
the main model when it has none. Never a model the user did not name, so no
prompt goes somewhere nobody chose [PRV-15]. Declarative `[[route]]` rules join
in v1 with the same first-match shape as `permissions.decide()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from edgar.config.schema import ModelSection
from edgar.core.errors import ConfigError

Role = Literal["main", "subagent", "compactor", "controller", "condenser"]


@dataclass(frozen=True, slots=True)
class RoutingContext:
    role: Role = "main"
    agent: str | None = None
    agent_model: str | None = None  # a subagent's frontmatter `model:` (v1)


@dataclass(frozen=True, slots=True)
class Selection:
    model: str
    rule: str  # "agent", "role", "default" or "user" (/model) [CLI-28]
    reason: str


def select_model(ctx: RoutingContext, models: ModelSection) -> Selection:
    if ctx.role == "subagent" and ctx.agent_model:
        return Selection(ctx.agent_model, "agent", f"agent {ctx.agent} names its model")
    own = getattr(models, ctx.role, None) if ctx.role not in ("main", "subagent") else None
    if own:
        return Selection(own, "role", f"[model] {ctx.role}")
    if models.default is None:
        raise ConfigError(
            "no model configured",
            hint="pass --model provider/model, or set [model] default in .edgar/config.toml",
        )
    if ctx.role == "main":
        return Selection(models.default, "default", "[model] default")
    return Selection(
        models.default, "default", f"[model] default; {ctx.role} has no model of its own"
    )
