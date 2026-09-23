"""The receipt: append-only, hash-chained, HMAC-signed [ADR-0039]."""

from __future__ import annotations

from pathlib import Path

from edgar.broker.receipt import Receipts, append, key_path, load_or_create_key, verify
from edgar.broker.ticket import Ticket
from edgar.core.events import (
    PermissionResolved,
    PromptSteered,
    PromptTyped,
    ScopeRefused,
    TurnStarted,
)


def test_load_or_create_key_makes_one_32_byte_key_readable_by_the_user_only(
    tmp_path: Path,
) -> None:
    key = load_or_create_key(tmp_path)
    assert len(key) == 32
    path = key_path(tmp_path)
    assert path.exists()
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_load_or_create_key_returns_the_same_key_on_a_second_call(tmp_path: Path) -> None:
    first = load_or_create_key(tmp_path)
    second = load_or_create_key(tmp_path)
    assert first == second


def test_append_then_verify_holds_for_an_honest_chain(tmp_path: Path) -> None:
    path, key = tmp_path / "receipt.jsonl", b"x" * 32
    prev = append(path, key, "0" * 64, "intent", {"text": "do the thing"})
    append(path, key, prev, "permission", {"tool": "read", "decision": "allow"})
    assert verify(path, key) is None


def test_verify_catches_a_tampered_line(tmp_path: Path) -> None:
    path, key = tmp_path / "receipt.jsonl", b"x" * 32
    prev = append(path, key, "0" * 64, "intent", {"text": "do the thing"})
    append(path, key, prev, "permission", {"tool": "read", "decision": "allow"})
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("do the thing", "do something else")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    broken = verify(path, key)
    assert broken is not None and broken.line == 1


def test_verify_catches_a_dropped_line(tmp_path: Path) -> None:
    path, key = tmp_path / "receipt.jsonl", b"x" * 32
    prev = append(path, key, "0" * 64, "intent", {"text": "one"})
    append(path, key, prev, "permission", {"tool": "read", "decision": "allow"})
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[1] + "\n", encoding="utf-8")  # keep only the second line
    broken = verify(path, key)
    assert broken is not None and broken.line == 1


def test_verify_catches_a_key_that_does_not_match(tmp_path: Path) -> None:
    path = tmp_path / "receipt.jsonl"
    append(path, b"x" * 32, "0" * 64, "intent", {"text": "one"})
    broken = verify(path, b"y" * 32)
    assert broken is not None and "signature" in broken.reason


def test_receipts_records_a_depth_0_intent(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts(PromptTyped(text="do the thing"))
    assert verify(receipts.path, receipts.key) is None
    lines = receipts.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and '"kind":"intent"' in lines[0]


def test_receipts_ignores_a_steer_and_a_deeper_typed_line(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts(PromptSteered(text="a correction"))
    receipts(PromptTyped(text="subagent's own line", depth=1))
    assert not receipts.path.exists()


def test_receipts_records_a_delegation_at_depth_1(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts(TurnStarted(turn_id="t1", model="fake/test", agent_id="helper", depth=1))
    lines = receipts.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and '"kind":"delegate"' in lines[0]


def test_receipts_ignores_a_main_turn_start(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts(TurnStarted(turn_id="t1", model="fake/test"))
    assert not receipts.path.exists()


def test_receipts_records_a_refusal_and_a_permission_decision(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts(ScopeRefused(id="c1", tool="read", caveat="paths", reason="outside scope"))
    receipts(PermissionResolved(id="c1", decision="allow", source="mode", tool="read"))
    lines = receipts.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"kind":"refuse"' in lines[0] and '"kind":"permission"' in lines[1]
    assert verify(receipts.path, receipts.key) is None


def test_record_ticket_writes_its_subject_and_caveats(tmp_path: Path) -> None:
    receipts = Receipts(path=tmp_path / "receipt.jsonl", key=b"x" * 32)
    receipts.record_ticket(Ticket(intent_id="i1", subject="main"))
    lines = receipts.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and '"kind":"ticket"' in lines[0]
