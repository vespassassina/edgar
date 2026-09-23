"""Caveats, tickets and pure authorization [CAP-2, CAP-5, CAP-9, ADR-0039]."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgar.broker.authorize import authorize
from edgar.broker.caveats import parse_scope
from edgar.broker.ticket import Ticket, attenuate, verify_chain
from edgar.core.errors import ConfigError
from edgar.permissions.matcher import Subject

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
ROOT = Path("/tmp/edgar-test-broker").resolve()


def test_parse_scope_reads_each_kind() -> None:
    caveats = parse_scope(["tools=read,grep", "paths=reports/q3.md", "calls=20"], now=NOW)
    by_kind = {c.kind: c.value for c in caveats}
    assert by_kind == {"tools": "read,grep", "paths": "reports/q3.md", "calls": "20"}


def test_parse_scope_resolves_until_to_an_absolute_instant() -> None:
    (caveat,) = parse_scope(["until=10m"], now=NOW)
    assert caveat.value == "2026-09-23T12:10:00+00:00"


def test_parse_scope_widens_a_repeated_list_key() -> None:
    (caveat,) = parse_scope(["tools=read", "tools=grep"], now=NOW)
    assert caveat.value == "read,grep"


def test_parse_scope_replaces_a_repeated_calls_or_until() -> None:
    (caveat,) = parse_scope(["calls=20", "calls=5"], now=NOW)
    assert caveat.value == "5"


@pytest.mark.parametrize("bad", ["nokey", "color=red", "until=soon"])
def test_parse_scope_rejects_nonsense(bad: str) -> None:
    with pytest.raises(ConfigError):
        parse_scope([bad], now=NOW)


def test_no_caveats_refuses_nothing() -> None:
    ticket = Ticket(intent_id="i1")
    subject = Subject(text=str(ROOT / "x.md"), path=ROOT / "x.md")
    assert (
        authorize(
            ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
        )
        is None
    )


def test_paths_caveat_allows_a_matching_path() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=reports/q3.md"], now=NOW))
    subject = Subject(text=str(ROOT / "reports/q3.md"), path=ROOT / "reports/q3.md")
    assert (
        authorize(
            ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
        )
        is None
    )


def test_paths_caveat_refuses_a_different_path() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=reports/q3.md"], now=NOW))
    subject = Subject(
        text=str(ROOT / "reports/2024-salaries.md"), path=ROOT / "reports/2024-salaries.md"
    )
    refusal = authorize(
        ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
    )
    assert refusal is not None and refusal.caveat == "paths"


def test_hosts_caveat_refuses_an_unlisted_host() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["hosts=api.github.com"], now=NOW))
    subject = Subject(text="https://evil.example/steal")
    refusal = authorize(
        ticket, tool="fetch", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
    )
    assert refusal is not None and refusal.caveat == "hosts"


def test_a_paths_caveat_refuses_shell_even_though_shell_has_no_path() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=reports/q3.md"], now=NOW))
    subject = Subject(text="cat reports/q3.md", command="cat reports/q3.md")
    refusal = authorize(
        ticket, tool="shell", read_only=False, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
    )
    assert refusal is not None and refusal.caveat == "paths"


def test_naming_shell_explicitly_in_tools_allows_it() -> None:
    ticket = Ticket(
        intent_id="i1", caveats=parse_scope(["paths=reports/q3.md", "tools=shell"], now=NOW)
    )
    subject = Subject(text="cat reports/q3.md", command="cat reports/q3.md")
    assert (
        authorize(
            ticket,
            tool="shell",
            read_only=False,
            subject=subject,
            cwd=ROOT,
            calls_so_far=0,
            now=NOW,
        )
        is None
    )


def test_a_read_only_command_tool_is_not_implicitly_refused() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=reports/q3.md"], now=NOW))
    subject = Subject(text="git status", command="git status")
    assert (
        authorize(
            ticket, tool="git", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=NOW
        )
        is None
    )


def test_calls_caveat_refuses_once_the_cap_is_reached() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["calls=2"], now=NOW))
    subject = Subject(text=str(ROOT / "x.md"), path=ROOT / "x.md")
    ok = authorize(
        ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=1, now=NOW
    )
    refused = authorize(
        ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=2, now=NOW
    )
    assert ok is None
    assert refused is not None and refused.caveat == "calls"


def test_until_caveat_refuses_after_it_expires() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["until=10m"], now=NOW))
    subject = Subject(text=str(ROOT / "x.md"), path=ROOT / "x.md")
    later = datetime(2026, 9, 23, 12, 11, 0, tzinfo=UTC)
    refusal = authorize(
        ticket, tool="read", read_only=True, subject=subject, cwd=ROOT, calls_so_far=0, now=later
    )
    assert refusal is not None and refusal.caveat == "until"


def test_attenuate_only_ever_widens_caveats() -> None:
    parent = Ticket(intent_id="i1", caveats=parse_scope(["tools=read,grep"], now=NOW))
    child = attenuate(
        parent, subject="task:explorer#2", extra=parse_scope(["paths=reports/"], now=NOW)
    )
    by_kind = {c.kind: c.value for c in child.caveats}
    assert by_kind["tools"] == "read,grep"
    assert by_kind["paths"] == "reports/"


def test_verify_chain_accepts_a_ticket_with_no_parent() -> None:
    assert verify_chain(Ticket(intent_id="i1")) is True


def test_verify_chain_accepts_honest_attenuation() -> None:
    parent = Ticket(intent_id="i1", caveats=parse_scope(["tools=read"], now=NOW))
    child = attenuate(parent, subject="task:x", extra=parse_scope(["paths=reports/"], now=NOW))
    assert verify_chain(child) is True


def test_verify_chain_rejects_a_forged_child_missing_a_parent_caveat() -> None:
    parent = Ticket(intent_id="i1", caveats=parse_scope(["tools=read", "paths=reports/"], now=NOW))
    forged = Ticket(intent_id="i1", caveats=parse_scope(["tools=read"], now=NOW), parent=parent)
    assert verify_chain(forged) is False
