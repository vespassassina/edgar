"""The `skill` tool: the model asks for a skill by name and gets its body [SKL-4, SKL-5]."""

# The prompt lists every skill's name and description (context/builder.py); this is
# the second half of that progressive disclosure. The body is read from disk when
# asked for, not at startup, so a skill edited mid-session is read as it now is.
#
# The flow:
#
#   the model calls skill(name)
#   no such skill?     -> an error that lists the names there are
#   otherwise          -> read its SKILL.md, drop the frontmatter, and return the body
#                         under a line naming the skill's folder, so paths the body
#                         mentions (scripts, templates) can be found [SKL-5]
#
# Scripts a skill bundles run through the `shell` tool, under the same permission
# checks as any other command; loading a skill runs nothing.

from __future__ import annotations

from typing import Any

from edgar.skills.discovery import Skill, split
from edgar.tools.base import ToolContext, ToolResult, builtin_schema


class SkillTool:
    def __init__(self, skills: dict[str, Skill]) -> None:
        self.skills = skills
        self.schema = builtin_schema(
            "skill",
            "Load a skill's instructions by name, from the skills listed in the system "
            "prompt. Load one when its description fits the task.",
            {"name": {"type": "string", "enum": sorted(skills)}},
            ["name"],
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        skill = self.skills.get(args["name"])
        if skill is None:
            listed = ", ".join(sorted(self.skills))
            return ToolResult(f"no skill {args['name']!r}; there are: {listed}", error="not_found")
        try:
            _, body = split(skill.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return ToolResult(f"skill {skill.name!r} cannot be read: {exc}", error="validation")
        where = f"from {skill.path.parent}; paths in it are relative to that folder"
        return ToolResult(f"Skill {skill.name}, {where}.\n\n{body.strip()}")
