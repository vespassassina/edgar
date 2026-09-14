"""Secret patterns, removed before text is stored for later [MEM-15].

Facts and the session-search index outlive the session, and a `/save` file travels,
so a key pasted into a prompt must not follow it there. The patterns are the
common shapes, not a guarantee: the rule that secrets come from the environment
(CFG-6) is what keeps them out of prompts in the first place.
"""

# redact(text):
#   for each pattern: replace every match with [redacted]
#   an assignment (token = …, password: …) keeps its name and loses its value

from __future__ import annotations

import re

MARK = "[redacted]"

PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),  # OpenAI, Anthropic, Stripe
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),  # AWS access key ids
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),  # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),  # JWTs
]
# `api_key = abc123`, `password: hunter2`, `TOKEN=…`: the name stays, the value goes.
ASSIGNED = re.compile(
    r"(?i)\b([\w-]*(?:api[_-]?key|token|secret|password|passwd)[\w-]*)"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)


def redact(text: str) -> str:
    for pattern in PATTERNS:
        text = pattern.sub(MARK, text)
    return ASSIGNED.sub(lambda m: f"{m[1]}{m[2]}{MARK}", text)
