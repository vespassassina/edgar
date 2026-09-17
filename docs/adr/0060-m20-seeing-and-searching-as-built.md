# ADR-0060 — M20, seeing and searching as built

**Status:** Accepted · 2026-09-17 · Completes M20; implements
[ADR-0052](0052-media-input-in-v2.md)'s six decisions about media input; follows
[ADR-0059](0059-m19-working-state-as-built.md) and extends its `@path` path

## Context

M20 adds three capabilities that look like one milestone only because they
arrive together: images through the whole harness, web search, and git. The
second and third cost **zero lines in `src/`** — both are files under
`examples/`, because the extension formats froze at 1.0 and a capability that
fits them should need no code. Everything below is therefore about images.

Images are expensive because `ImageBlock` is a new member of the frozen message
vocabulary, and a frozen vocabulary is the one place where a field added on spec
has to be carried by every adapter, every test and every stored session forever.
Two files in this milestone are the ones that break things silently:
`core/message.py` (the vocabulary) and `context/compact.py` (invariant 1, the
pairing invariant). The rule applied throughout was to take the more
conservative option on both — the one least likely to break an invariant or
force a second migration — and to write down why.

`just loc` reads **8,592 of 9,500** after M20: 218 lines of code added against
the ~200 estimated, all of it in items 1–7.

**Three decisions below are flagged for extra human review before merge:** the
`ImageBlock` field list (1), the compaction-elision approach (2), and the
spill-reuse-versus-new-helper choice (3).

## Options and decisions

### 1. The `ImageBlock` field list — FLAGGED FOR EXTRA SCRUTINY

`ImageBlock` is frozen and slotted like every other block, and carries exactly
four fields:

| Field | Why it is here |
|---|---|
| `ref` | the blob path; what serialisation reads to produce base64 |
| `media_type` | goes on the wire in both provider shapes |
| `width` | `image_tokens()` prices by geometry |
| `height` | same |

The test for inclusion was deliberately narrow: **does serialisation or token
counting actually read it?** Nothing else qualified, so nothing else is here.

Rejected, each with a plausible case: `filename` or `source_path` (the blob is
the file; a name is a display concern, and the elision stub already prints the
ref); `bytes`/`data` (ADR-0052 decision 2 — images spill, never base64 in the
JSONL; a transcript with base64 in it is ungreppable and large); `caption` or
`alt` (nothing produces one — the model writes descriptions into ordinary
text); `sha256` (no caller; deduplication is not a feature anyone asked for);
`created_at` (the event stream already timestamps); `origin` (`ThinkingBlock`
has one because foreign reasoning must be dropped on serialisation — an image
has no equivalent rule, and adding the field would imply one exists).

The conservative direction here is **fewer fields**, and it is asymmetric:
adding a field later is additive and costs one migration-free release, whereas
removing one from a frozen vocabulary means rewriting stored sessions. A field
with no caller cannot be validated by any test, so it drifts.

The one addition beyond the block itself is `Message.images`, a property that
gathers pictures from a message's own blocks *and* its tool results, so
counting, eliding and serialising each read one thing instead of walking blocks
themselves.

### 2. How compaction elides an image — FLAGGED FOR EXTRA SCRUTINY

(A) Extend `_stub()`, the per-block helper `elide()` already maps over every
block before the cut point. (B) Add a separate, clearly-named `_elide_images()`
pass. **Decided: A, extend `_stub()`.**

B reads better in isolation and is the option a reviewer would reach for. It is
also the one that puts a *second* function in the file that knows where a turn
may be cut, and the entire value of invariant 1 is that exactly one function
knows that. Compaction holds the pairing invariant by construction — it only
ever removes, stubs or summarises whole units — and that proof is a property of
`elide()` being the single cut point. A second pass would either have to re-derive
the cut (two copies of the rule, which disagree eventually) or run over the
result of the first (safe today, and one refactor away from not being).

An old picture becomes `[elided: image image/png 1024x768 · blobs/shot.png]`.
The reference survives, so a human can attach it again and the model can
`read` it; the bytes were never in the transcript anyway, only in the blobs, so
nothing is lost that is not still on disk.

Two properties were verified rather than assumed:

- **Whole units.** A tool result carrying images is stubbed *with* them — the
  text is replaced and `images` is set to `()` in the same `replace()` — so a
  stub never drags its screenshots along, and no unit is trimmed internally.
- **Idempotence.** An `ImageBlock` becomes a `TextBlock` that maps to itself on
  a second pass, and an already-stubbed result returns early on the
  `startswith(ELIDED)` check. The existing property test, which now puts an
  `ImageBlock` on every other tool result, runs elision twice and asserts the
  pairing survives both.

### 3. Reusing the spill helper, or adding one — FLAGGED FOR EXTRA SCRUTINY

The brief said to reuse the existing spill helper unless it is
tool-output-specific, and to extract the shared part if it is. It is.
**Decided: a new `spill_image()` beside `spill()`, sharing the file write, not
the policy.**

The two have genuinely different rules:

| | `spill()` (M5) | `spill_image()` |
|---|---|---|
| When | conditionally, when output is too big | always, for any recognised image |
| What survives | a head and a tail, so the model still sees some | the whole file — half a PNG is not a smaller PNG |
| Returns | text plus a blob path | an `ImageBlock`, or `None` if it is not an image |

Making `spill()` take a `whole=True` flag would have put both policies in one
body and forced the new parameter through every existing caller; the shared part
is one file write, which is what the two now share. This is the smallest of the
three flagged decisions and the easiest to revisit later, since neither function
is part of the frozen vocabulary.

`spill_image()` also carries the geometry reading: PNG, JPEG, GIF and WebP each
announce themselves in their first bytes and carry their dimensions a fixed
distance in, so `SIGNATURES` is about fifteen lines and edgar takes **no image
dependency** (no Pillow). A header that cannot be parsed still yields an image,
with `width` and `height` of 0 — see decision 4.

### 4. What an unmeasurable image costs

`image_tokens()` prices by geometry, never by bytes, because every provider
resizes before it looks: a 4 MB photograph and a 40 KB screenshot of the same
dimensions cost the same. Two rules cover every provider edgar speaks to —
Anthropic shrinks to a 1568px longest side and charges area over 750; the Chat
Completions family shrinks to fit 2048, then the short side to 768, and charges
a base plus a price per 512px tile.

When the header could not be read, the size is 0 and the function charges **one
tile's worth** rather than guessing. This is wrong, but wrong by a bounded amount
in a known direction, which is what an estimate that gates compaction needs. The
function stays pure — no I/O, no clock, no config — so it is property-testable,
which is the reason to trust a number this load-bearing.

### 5. Where a blind model is refused

Two paths, because there are two ways an image arrives.

- An **attachment** is refused where the model is chosen — `check_images()` in
  `providers/routing.py`, called from both CLIs before the turn — mirroring
  ROUTE-6 and `check_capabilities()`. Nothing is sent and nothing is spent.
- A picture a **tool** produces mid-turn cannot be refused that way, since the
  model is already chosen. `ToolContext.images` carries the capability, and
  `read` on an image answers a blind model with a sentence saying what the file
  is and that it cannot look. That is **not** an error result: the call worked,
  and the model decides what to do next.

### 6. Keeping `images` a separate channel through the loop

`core/loop.py` was at exactly 200/200 lines of code, its hard cap. The cheaper
option by one line was widening `attached` to `Sequence[str | ImageBlock]`.
**Decided: a separate `images` parameter**, paid for with two module-level type
aliases (`Texts`, `Shots`) that keep both signatures on one line, and three
narration docstrings converted to `#` comments, which the house style prefers
anyway and which the budget does not count.

`attached` means piped stdin or an `@file:` context (CLI-3) and is the input the
learning boundary treats a particular way. Overloading it to also mean pictures
would have made a documented term mean two things to save one line. `loop.py`
ends at exactly 200/200.

## Consequences

- One new block in the frozen vocabulary; no new module anywhere in `src/`.
- `providers/http.py` gained a shared `encoded()` so both real adapters base64
  from one place, raising `ProviderError` when the blob is gone rather than
  sending an empty image. The base64 exists for one request and is never stored.
- The OpenAI shape cannot put an image inside a `tool_result`, so
  `openai_compat.py` follows the tool results with one extra user message
  carrying them. Anthropic nests them. Different bytes, same conversation.
- `ToolFinished` gained one optional field, `image`, carrying the reference, so
  `--events` can locate the picture on disk while the bytes never enter the
  event stream.
- **No new cassettes were recorded.** The contract suite's image cases reuse the
  existing `text` and `round_trip` scenarios and assert on the request body,
  because serialising an image is entirely outbound and no provider returns one.
  No paid or live API was called in this milestone.
- Web search and git added **0 lines to `src/`**: eleven files under
  `examples/`, two Cookbook recipes and rows in `examples/README.md`.
- `just loc` reads 8,592 of 9,500, with M21 and M22 to come.

## Alternatives not taken

**Images out of the model.** Nothing here generates or edits pictures; `ADR-0052`
scoped this to input and that has not changed.

**A built-in `web_search` tool.** It would have needed a default host, which
PRV-15 forbids, or a mandatory choice at startup. A TOML file with three
documented variants and no default is both smaller and more honest about who
sees your queries.

**A built-in git integration, or a `git-add` tool.** git is a CLI and edgar
already describes CLIs declaratively. Staging is deliberately absent: it is the
moment a human decides what goes in a commit. Push, merge and tag are absent for
the same reason.
