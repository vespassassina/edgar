"""`edgar skills distill NAME`: turn a skill's observations into a better body [SKL-14]."""

# The same work the gate does on its own after `skills.distill_after` bad turns,
# asked for by hand. One command, read top to bottom:
#
#   1. find the skill            discovery, the same index a session uses
#   2. read its observations     learning/observations.py, the machine-owned lines
#   3. nothing recorded          say so and stop: there is nothing to distill
#   4. one model call, no tools  the current body and those lines, and nothing else
#   5. parse()                   the controller's own whitelist; only propose_skill
#   6. apply()                   and the controller's own SKL-10/11 decision
#
# Steps 5 and 6 are why this needs the controller package. It would be easy to
# write a proposal file here instead, and that is exactly the duplication worth
# refusing: "propose or write, and under which conditions" is one decision, and it
# lives in controller/apply.py. A project with v3's controller deleted gets a
# sentence saying so rather than a second, drifting copy of the rule.

from __future__ import annotations

import asyncio
from pathlib import Path

from edgar.config.load import load
from edgar.core.message import Message
from edgar.learning.observations import PATCH_BRIEF, notes, outline
from edgar.skills.discovery import discover


def command(name: str, cwd: Path, home: Path) -> int:
    """One skill, distilled. Exit 0 when something was written or proposed."""
    # 1. The skill has to exist, and it is looked up in the index rather than on
    #    disk so `distill` and a session always mean the same skill by one name.
    skill = discover(cwd, home).skills.get(name)
    if skill is None:
        print(f"no skill named {name}")
        return 1
    recorded = notes(cwd, name)
    if not recorded:
        print(f"{name} has no observations yet; nothing to distill")
        return 0
    body = skill.path.read_text(encoding="utf-8")
    return asyncio.run(_distill(name, outline(name, body, recorded), cwd, home))


async def _distill(name: str, asked: str, cwd: Path, home: Path) -> int:
    # 2. The controller owns the decision, and may have been deleted [NFR-12].
    try:
        from edgar.controller.apply import Site, apply
        from edgar.controller.proposals import ProposeSkill, parse, targets
        from edgar.controller.store import Controls
    except ModuleNotFoundError:  # pragma: no cover - the tier was removed
        print("skills distill needs the controller package")
        return 1
    from edgar.core.events import EventBus
    from edgar.permissions.policy import Policy
    from edgar.providers.registry import resolve
    from edgar.providers.routing import RoutingContext, routes_from_config, select_model

    # 3. One call, no tools, on a bus of its own: the same shape the gate uses, so
    #    there is one answer to "what does edgar send a model here" [CTRL-3].
    config = load(cwd, home=home)
    rules = routes_from_config(config.later)
    ctx = RoutingContext(role="controller", mode=config.permissions.mode)
    provider, model = resolve(select_model(ctx, config.model, rules).model, config)
    prompt = [Message.user(f"{PATCH_BRIEF}\n\n---\n\n{asked}")]
    answer = await provider.stream(prompt, [], model=model, bus=EventBus(), reasoning=False)
    proposal = parse(answer.message.text, models=targets(config.model, rules))
    if not isinstance(proposal, ProposeSkill):
        print(f"the model proposed no patch for {name}")
        return 1
    # 4. And the write, under whatever SKL-10 and SKL-11 allow today.
    site = Site(
        Controls(cwd / ".edgar" / "controller.db"),
        cwd,
        Policy(mode=config.permissions.mode, cwd=cwd, home=home),
        config.controller.dry_run,
        home=home,
        synthesis=config.skills.synthesis,
        verified=True,  # a person typed the command: that is the review [SKL-11]
        trigger="distilled",
    )
    print(apply(proposal, site).message)
    return 0
