"""An image survives a turn and a --resume [ADR-0052, CTX-14].

M20's "done when": the fake provider round-trips an `ImageBlock`. The picture is
spilled to the session's blobs, rides on the user message, reaches the provider,
and is still there after the JSONL record is replayed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from harness import new_session, runtime

from edgar.core.loop import run_turn
from edgar.core.session import Session
from edgar.providers.fake import FakeProvider
from edgar.storage.transcript import find, replay, start
from edgar.tools.spill import spill_image

# A 1x1 PNG, header-accurate: enough for the geometry reader to measure it.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


def _session(root: Path) -> Session:
    session = start(new_session(root))
    assert session.log is not None
    return session


def test_the_fake_provider_round_trips_an_image_through_a_turn(tmp_project: Path) -> None:
    session = _session(tmp_project)
    rt = runtime(FakeProvider(), None)  # type: ignore[arg-type]  # FakeProvider is a Provider
    shot = spill_image(PNG, blob_dir=tmp_project / ".edgar" / "blobs", name="photo")
    assert shot is not None
    result = asyncio.run(run_turn(session, "look at this", rt, images=[shot]))
    assert f"image/png 1x1 {shot.ref}" in result.text


def test_the_image_is_still_there_after_a_resume(tmp_project: Path) -> None:
    session = _session(tmp_project)
    assert session.log is not None
    rt = runtime(FakeProvider(), None)  # type: ignore[arg-type]  # FakeProvider is a Provider
    rt.bus.subscribe(session.log.event)
    shot = spill_image(PNG, blob_dir=tmp_project / ".edgar" / "blobs", name="photo")
    assert shot is not None
    asyncio.run(run_turn(session, "look at this", rt, images=[shot]))

    path = find(tmp_project, session.id)
    resumed, turns = replay(path)
    assert turns == 1
    assert [i for m in resumed.transcript for i in m.images] == [shot]
    # The bytes never entered the record: only the reference did [ADR-0052].
    record = path.read_text(encoding="utf-8")
    assert "base64" not in record and "PNG" not in record
