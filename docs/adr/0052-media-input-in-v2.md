# ADR-0052 — Media input belongs in v2, and only one new block

**Status:** Accepted · 2026-09-14 · Amends PRD §5.3 and §5.1; scope only, nothing
is built before v2

## Context

PRD §5.3 defers "image and multimodal input" past v2, and `ROADMAP.md` lists it
ninth in the past-v2 order. That was a defensible call while edgar was a terminal
program reading a repository: a developer at a keyboard describes what they see,
and text is the whole job.

Two things changed it. Models now read images, documents, slides and audio as a
matter of course, so a harness that cannot pass them through is refusing a
capability the user is already paying for. And a client that is not a terminal
([ADR-0051](0051-controlling-edgar-from-elsewhere.md)) makes it structural: a
project created from a phone is filled by upload, and a screenshot is the single
most natural thing a person sends from one.

Against that: `src/` is at 7,045 of v1's 8,000 lines of code with M9, M10 and M11
still to build, and ADR-0050 has just moved four `(Should)` items out of v1 to
make that arithmetic work. Media touches the message vocabulary, every provider
adapter, token counting and the transcript format — the four places where a
change is least free.

## Decisions

**1. v2, not v1.** Media input moves out of "deferred past v2" and into v2 scope.
It is not scheduled against a milestone here: M12 through M17 are the learning,
controller, synthesis, escalation, broker and scheduling milestones, and media
belongs to none of them. It is v2 scope awaiting a slot, and the slot is chosen
when v2 is planned. Nothing is built before then.

**2. One new block, and one only.** `core/message.py` gains `ImageBlock` —
frozen and slotted like the other four — and gains nothing else. Audio, video,
PDF, PPTX and spreadsheets do **not** become block types. The message vocabulary
is the thing every provider adapter, the compactor and the transcript agree on,
and a vocabulary that grows with every file format on earth is a vocabulary
nobody can hold in their head.

**3. Everything else converts at the boundary.** A document becomes text and
images before it reaches the loop: a tool extracts pages from a PDF, text and
slide images from a PPTX, a transcript from audio. That is what the tool
vocabulary is for, it means a new format is an extension rather than a core
change, and it keeps the conversion visible in the transcript as a tool call
instead of hidden inside the harness.

**4. Images spill like tool output does.** S0 already writes large tool output to
`.edgar/sessions/<id>/blobs/` and leaves a reference behind (ADR-0016). An image
goes the same way. Base64 inline would make transcripts megabytes each and end
the property that `tail -f` on a session JSONL is a readable thing to do.

**5. A provider that cannot take an image says so.** A row in `quirks.py` like
every other provider difference (ADR-0002), and a model without the capability
fails loudly. Dropping an image silently would let a user believe a decision was
made on evidence the model never saw. The precedent is `ThinkingBlock.origin`:
foreign reasoning is dropped on serialisation deliberately and visibly, never
rewritten.

**6. Token counting learns geometry.** Images cost tokens by dimensions, per
provider. Counting is one of the pure functions correctness rides on, and
compaction decides what to elide from it. If it cannot size an image, the context
budget is wrong for every session containing one.

## Consequences

- PRD §5.3 loses "image and multimodal input"; PRD §5.1's v2 list gains it, and
  `ROADMAP.md`'s past-v2 list loses item 9.
- v2's budget is 11,000 lines of code and already carries learning, the
  controller, synthesis, escalation, the broker and scheduling. Media is an
  estimated 150 to 250 lines across `core/message.py`, the two provider adapters,
  `quirks.py`, counting and spill. When v2 is planned, it competes for that
  budget like everything else; the budget does not move (ADR-0015).
- Nothing in `src/` changes now. A separate process is building M9 in this working
  copy, and this ADR deliberately touches no code.
