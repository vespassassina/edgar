# Testing strategy

Rationale in [ADR-0009](adr/0009-testing-strategy.md). This document is how to
actually write and run the tests.

Testing an agent harness is hard for one reason: **nondeterminism**. Model output
varies, providers change under you, and calls cost money. The strategy is to make
as much of the system deterministic as possible, then test the irreducible
nondeterminism separately and less often.

---

## Layout

```
tests/
├── conftest.py              shared fixtures
├── unit/                    one module, no I/O
├── contract/                every provider passes identically
├── property/                invariants over generated inputs
├── integration/             several modules, fake provider, tmp filesystem
├── cassettes/               recorded HTTP exchanges
├── e2e/                     subprocess the real CLI
├── evals/                   outcome-scored tasks, on demand
├── support/                 on the test path, not a package:
│                            netguard.py + sitecustomize.py (socket guard), importgraph.py
│                            (static import graph), budget.py (size budgets, `just loc`),
│                            harness.py (Recorder, runtime(), scripted(), run_turn_sync())
└── fixtures/
    ├── projects/            sample .edgar/ trees
    ├── skills/
    └── agents/
```

## What runs when

| Suite | Trigger | Budget | Network | Cost |
|---|---|---|---|---|
| unit + property | every PR | 15 s | none | 0 |
| contract (fake + cassettes) | every PR | 20 s | none | 0 |
| integration | every PR | 20 s | none | 0 |
| e2e | every PR | 5 s | none | 0 |
| live smoke | scheduled | 5 min | yes | cents |
| evals | manual | 20 min | yes | dollars |

PR total target ≤ 60 s [NFR-2]. If it creeps past 90 s, that is a bug in the tests.

From M12 on, a second PR job deletes the v2 packages (`learning/`, `controller/`,
`schedule/`, `providers/escalation.py`) and runs the v1 suite, which must stay
green [NFR-12].

---

## Layer 1 — The fake provider

The highest-leverage piece of infrastructure in the repo. Built in milestone 1,
before any real provider exists.

Given a script, it replays it. Without one, the `fake/test` model follows three
fixed rules so the CLI can be driven end to end with no real model: `read PATH`
and `ls [PATH]` become tool calls, tool results are answered with their text, and
anything else is echoed as `fake/test heard: …`.

```python
# providers/fake.py
class FakeProvider:
    """Scripted responses. No network. Deterministic."""

    def __init__(self, script: list[ScriptedResponse]): ...

@dataclass
class ScriptedResponse:
    text: str = ""
    thinking: str | None = None
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    usage: Usage = DEFAULT_USAGE
    raises: Exception | None = None
    delay_s: float = 0.0          # exercise cancellation
    stream_chunks: int = 1        # exercise partial-stream handling
```

```python
def test_loop_executes_tool_and_continues(fake_provider, tmp_project):
    fake_provider.script = [
        ScriptedResponse(tool_calls=[tool_use("read", {"path": "a.txt"})]),
        ScriptedResponse(text="The file says hello."),
    ]
    result = run_turn_sync(session, "what's in a.txt?")
    assert "hello" in result.text
    assert fake_provider.call_count == 2
```

Everything testable this way should be: the loop, tool dispatch, permissions,
compaction, subagents, budget, controller, session persistence.

**Rule:** a test that does not specifically exercise provider translation should
use the fake provider.

---

## Layer 2 — Provider contract suite

One parametrised suite that **every adapter must pass identically**. This is what
prevents "works on OpenAI, breaks on Ollama", the specific risk created by the
shared adapter in ADR-0002.

```python
# tests/contract/test_provider_contract.py
PROVIDERS = ["fake", "openai", "azure", "openrouter", "ollama", "anthropic", "compat"]

@pytest.mark.parametrize("provider", PROVIDERS)
class TestProviderContract:
    def test_streams_text_deltas(self, provider): ...
    def test_returns_single_tool_call(self, provider): ...
    def test_returns_parallel_tool_calls(self, provider): ...
    def test_round_trips_tool_result(self, provider): ...
    def test_preserves_own_thinking_blocks(self, provider): ...
    def test_drops_foreign_thinking_blocks(self, provider): ...          # [PRV-13]
    def test_repairs_fenced_tool_call(self, provider): ...               # [PRV-16]
    def test_accepts_tool_turn_after_family_switch(self, provider): ...  # reasoning off
    def test_reports_usage(self, provider): ...
    def test_maps_auth_error_to_ProviderError(self, provider): ...
    def test_retries_429_then_succeeds(self, provider): ...
    def test_cancellation_stops_stream_promptly(self, provider): ...
    def test_declares_capabilities_truthfully(self, provider): ...
    def test_normalises_to_canonical_messages(self, provider): ...
```

`compat` is a user-defined provider [PRV-12] pointed at a small local fixture
server that speaks the OpenAI-compatible protocol, so the config-only path is held
to the same contract.

Non-fake providers run against cassettes on PRs and against the live API on the
scheduled job. Same test bodies, different transport.

**The suite is public.** From v1 it ships as `edgar.testing.contract` [PRV-14], so
a provider plugin in another package runs exactly these tests:

```python
# in a plugin's own test suite
from edgar.testing.contract import ProviderContract

class TestGemini(ProviderContract):
    provider = "gemini"
```

**Definition of done for a new provider: the contract suite passes.** That is a
checkable, meaningful bar, and it is what makes "add a provider in under an hour"
a real claim rather than a hope.

---

## Layer 3 — Cassettes

Recorded exchanges replayed offline. They catch what a hand-written fake cannot,
because a fake encodes what you *believe* the API does.

```
tests/cassettes/
├── openai/tool_call_single.json
├── anthropic/thinking_with_tools.json
├── ollama/no_tool_support.json
└── azure/deployment_routing.json
```

```bash
just record-cassettes            # hits live APIs, requires keys
just record-cassettes --only openai
```

**Secrets are scrubbed on record**, not on commit. Auth headers, keys, org ids and
account identifiers are replaced with placeholders by the recorder, and a test
asserts no cassette contains anything matching a secret pattern.

**Cassettes go stale silently.** That is precisely why layer 5 exists.

---

## Layer 4 — Property tests

The architecture deliberately maximises pure functions so this layer can be
substantial. Using Hypothesis.

### Compaction pairing invariant — the most important test in the repo

The invariant is the one providers actually enforce [CTX-4, ADR-0016]: results
must be in the message **immediately after** their calls, one-to-one. Checking only
that each result appears somewhere later accepts transcripts that get a 400.

```python
@given(transcript=transcripts(), at=st.floats(0.3, 0.9), to=st.floats(0.1, 0.3))
def test_compaction_preserves_pairing(transcript, at, to):
    out = compact(transcript, compact_at=at, compact_to=to, summariser=fake_summariser)
    assert_pairing_invariant(out)

def assert_pairing_invariant(msgs):
    for i, m in enumerate(msgs):
        calls = [b.id for b in m.content if isinstance(b, ToolUseBlock)]
        results = [b.tool_use_id for b in m.content if isinstance(b, ToolResultBlock)]
        if m.role == "tool":
            prev = msgs[i - 1] if i else None
            prev_calls = [b.id for b in prev.content if isinstance(b, ToolUseBlock)] if prev else []
            assert prev is not None and prev.role == "assistant", "tool message without calls before it"
            assert sorted(results) == sorted(prev_calls), "results do not match the calls one-to-one"
        elif calls:
            assert m.role == "assistant", "tool call outside an assistant message"
            assert i + 1 < len(msgs) and msgs[i + 1].role == "tool", "calls not followed by results"
```

A violation here produces a 400 from every provider and a session the user cannot
recover. It is worth generating thousands of cases. The same assertion runs on
every transcript the fake-provider tests produce, and on the output of
cancellation (CLI-12).

### Input during a turn

Steers arrive at arbitrary moments, so arrival timing is generated too
[CLI-13, CLI-24, ADR-0028]:

```python
@given(script=turn_scripts(), arrivals=steer_arrivals())   # arrival = before/during any event
def test_steer_lands_between_units_whenever_it_arrives(script, arrivals):
    transcript = run_turn_with_steers(script, arrivals)
    assert_pairing_invariant(transcript)
    assert steer_texts(transcript) == [a.text for a in arrivals if a.before_turn_end]

def test_steer_after_final_answer_continues_the_turn_before_verify(fake_provider):
    events = run_with_steer_after_final_text(fake_provider)
    assert event_names(events).index("SteerApplied") < event_names(events).index("VerifyStarted")

@given(transcript=transcripts_ending_mid_unit())
def test_aside_snapshot_never_ends_with_unanswered_calls(transcript):
    request = aside.build_request(transcript, "what does this regex do?")
    assert_pairing_invariant(request.messages)
    assert request.tools == []

def test_aside_leaves_the_transcript_unchanged(fake_provider, tmp_session):
    before = list(tmp_session.transcript)
    aside.ask(tmp_session, "quick question")
    assert tmp_session.transcript == before and last_record(tmp_session)["type"] == "aside"
```

The Anthropic contract test adds a steer after a tool message and checks the
request is accepted with tool results and text merged into one user message.

### Compaction stages

```python
@given(transcript=transcripts())
def test_compaction_is_idempotent(transcript):
    once = compact(transcript, compact_at=0.7, compact_to=0.5, summariser=fake_summariser)
    twice = compact(once, compact_at=0.7, compact_to=0.5, summariser=fake_summariser)
    assert twice == once                                  # [CTX-8]

@given(transcript=tool_heavy_transcripts())
def test_elision_needs_no_model_call(transcript):
    counting = CountingSummariser()
    compact(transcript, compact_at=0.7, compact_to=0.5, summariser=counting)
    assert counting.calls == 0 or tokens_after_s1(transcript) > 0.5   # S2 only when S1 is not enough

@given(transcript=transcripts())
def test_compaction_never_touches_the_unit_in_progress(transcript):
    out = compact(transcript, compact_at=0.7, compact_to=0.5, summariser=fake_summariser)
    assert last_unit(out) == last_unit(transcript)

def test_oversized_pinned_content_raises_overflow():
    t = transcript_with_pinned_tokens(window_fraction=1.3)
    with pytest.raises(ContextOverflow) as e:
        compact(t, compact_at=0.7, compact_to=0.5, summariser=fake_summariser)
    assert "keep_last_turns" in e.value.hint              # [CTX-12]

def test_spill_keeps_full_output(tmp_session):
    result = run_tool_with_output(tmp_session, size_chars=200_000)
    assert result.truncated and Path(result.blob).read_text() == FULL_OUTPUT   # [CTX-13]
```

### Others

```python

@given(schedules=schedules(), state=run_states(), now=datetimes())
def test_due_calculation_is_pure_and_stable(schedules, state, now):
    a = compute_due(schedules, state, now)
    b = compute_due(schedules, state, now)
    assert a == b

@given(path=hostile_paths())     # .., symlinks, UNC, 8.3 names, unicode
def test_no_path_escapes_root(path, tmp_root):
    d = decide(WRITE, {"path": path}, mode="auto", rules=default_rules(), cwd=tmp_root,
               interactive=False, tainted=False, control_paths=frozenset())
    if isinstance(d, Allow):
        assert resolve(tmp_root, path).is_relative_to(tmp_root.resolve())

@given(path=control_file_paths(), mode=st.sampled_from(["read-only", "ask", "auto"]),
       rules=any_rules(), interactive=st.booleans(), tainted=st.booleans())
def test_control_files_are_never_auto_allowed(path, mode, rules, interactive, tainted, tmp_root):
    d = decide(WRITE, {"path": path}, mode=mode, rules=rules, cwd=tmp_root,
               interactive=interactive, tainted=tainted, control_paths=control_set(tmp_root))
    assert not isinstance(d, Allow)                        # [PERM-12]
    if not interactive:
        assert isinstance(d, Deny)

@given(cmd=shell_commands(), rules=config_rules_without_explicit_shell_allow())
def test_tainted_auto_never_allows_shell_by_default(cmd, rules, tmp_root):
    d = decide(SHELL, {"command": cmd}, mode="auto", rules=rules, cwd=tmp_root,
               interactive=True, tainted=True, control_paths=frozenset())
    assert not isinstance(d, Allow)                        # [PERM-11]

@given(segments=st.lists(shell_segments(), min_size=1), sep=st.sampled_from([";", "&&", "||", "|", "\n"]))
def test_any_denied_segment_denies_the_command(segments, sep, tmp_root):
    cmd = f" {sep} ".join(segments + ["rm -rf /tmp/x"])
    d = decide(SHELL, {"command": cmd}, mode="auto", rules=rules_denying("rm -rf *"),
               cwd=tmp_root, interactive=False, tainted=False, control_paths=frozenset())
    assert isinstance(d, Deny)                             # [PERM-14]

@given(actions=automated_action_sequences())
def test_no_automated_action_widens_policy(actions):
    start = policy_snapshot(default_session())
    end = policy_snapshot(apply_all(default_session(), actions))
    assert end <= start                                    # humans widen, machines tighten [PERM-8]

@given(value=st.text(), tool=http_tool_templates())
def test_http_tool_arguments_cannot_change_host(value, tool):
    request = render_request(tool, {name: value for name in tool.slots})
    assert request.url.host == tool.template_host          # [TOOL-6]

@given(ctx=routing_contexts(), rules=route_rules())
def test_routing_is_deterministic(ctx, rules):
    assert select_model(ctx, rules, DEFAULTS) == select_model(ctx, rules, DEFAULTS)

@given(chain=escalation_chains(), start=st.integers(0, 4), steps=st.integers(1, 6))
def test_escalation_never_moves_down(chain, start, steps):
    positions = walk_escalation(chain, start, steps)
    assert positions == sorted(positions), "escalation moved down the chain"

@given(model=models(), targets=fallback_targets())
def test_fallback_never_reduces_capabilities(model, targets):
    for t in resolve_fallback(model, targets):
        assert capabilities(t) >= capabilities(model)

@given(text=text_with_secrets())
def test_redaction_removes_all_known_patterns(text):
    assert not any(p.search(redact(text)) for p in SECRET_PATTERNS)

@given(value=st.text(), argv=command_tool_templates())
def test_command_tool_arguments_are_single_argv_elements(value, argv):
    rendered = render_argv(argv, {name: value for name in argv.slots})
    assert rendered.count(value) == len(argv.slots)        # never split, never shell-parsed [TOOL-6]
```

### The learning boundary

These are the tests that keep ADR-0017's claim true. The trajectory generator mixes
typed prompts, piped stdin, `@file` attachments, tool results that say "remember
…", MCP errors with injected text, and model calls to `remember`.

```python
@given(trajectory=trajectories())
def test_only_humans_and_error_templates_create_active_facts(trajectory):
    store = run_learning(trajectory)                       # v1 memory + v2 learner
    for fact in store.active():
        assert fact.provenance in {"user", "user-prompt", "user-feedback", "error-template"}

@given(trajectory=trajectories())
def test_learner_input_contains_no_untrusted_text(trajectory):
    seen = capture_learner_input(trajectory)
    assert all(not b.attached for b in seen.text_blocks)   # no stdin, no @files [CLI-3]
    assert not any(untrusted in seen.text for untrusted in trajectory.untrusted_strings)

@given(trajectory=trajectories())
def test_synthesiser_sees_no_tool_output_or_error_text(trajectory):
    outline = build_outline(trajectory)
    assert not any(s in outline.render() for s in trajectory.tool_output_strings)
    assert not any(s in outline.render() for s in trajectory.error_text_strings)   # [SKL-9]
```

### Tier isolation

```python
V2 = ("edgar.controller", "edgar.learning", "edgar.schedule", "edgar.providers.escalation")

def test_core_and_v1_never_import_v2():
    for module in static_import_graph("src/edgar"):
        if not module.name.startswith(V2):
            assert not any(dep.startswith(V2) for dep in module.imports), module.name   # [NFR-12]

CORE = ("edgar.core", "edgar.context", "edgar.permissions", "edgar.tools.execute")
ADAPTERS = ("edgar.providers.openai_compat", "edgar.providers.anthropic", "edgar.tools.mcp",
            "edgar.sandbox.none", "edgar.sandbox.bwrap", "edgar.sandbox.seatbelt",
            "edgar.sandbox.container", "edgar.memory.recall")    # sandbox.base is the port

def test_core_imports_no_adapter():
    for module in static_import_graph("src/edgar"):
        if module.name.startswith(CORE):
            assert not any(dep.startswith(ADAPTERS) for dep in module.imports), module.name  # [EXT-11]
```

Both rules also run against small planted source trees that break them, so a green
result on a nearly empty `src/` still proves the check works.

### Size budgets

`tests/unit/test_size_budget.py` fails the build when `src/` passes the budget of
the tier being built (`TARGET_TIER` in `tests/support/budget.py`), when `core/`
passes 2,000, or when `core/loop.py` passes 200 physical lines [NFR-4]. A line of
code is a non-blank line that is not only a comment; docstrings count. At v2 the
code outside the v2 packages is also held to the v1 budget. `just loc` prints the
same numbers as a report, and CI prints it on every run.

### No hidden behaviour

The rules in ADR-0023, each held by a test rather than by review.

```python
def test_prefix_is_byte_stable_between_compactions(fake_provider, long_session_script):
    requests = run_session(fake_provider, long_session_script)          # 60 turns, tools, a todo update
    for a, b in pairwise(requests):
        if not b.after_compaction:
            assert b.prefix_bytes == a.prefix_bytes                     # [CTX-17]

def test_prompt_budget():
    assert approx_tokens(load_prompt("system")) <= 1_500                # [NFR-13]
    assert approx_tokens(schemas(core_builtins())) <= 2_500

@given(config=configs())
def test_no_request_reaches_an_unconfigured_host(config, recording_transport):
    run_session_with(config, transport=recording_transport)
    assert recording_transport.hosts <= reachable_hosts(config)         # [PRV-15]

@given(config=configs_with_only_a_local_model())
def test_auxiliary_roles_never_pick_a_model_the_user_did_not_name(config):
    for role in ("compactor", "controller", "condenser"):
        assert select_model(ctx(role=role), config.routes, config.defaults).model in config.named_models
```

### Tool-call repair

```python
@given(call=valid_tool_calls(), damage=st.sampled_from(SYNTACTIC_DAMAGE))   # fences, trailing text, bare JSON
def test_repair_recovers_syntactic_damage(call, damage):
    assert repair(damage(render(call)), tools=KNOWN) == call            # [PRV-16]

@given(text=st.text())
def test_repair_never_invents_a_call(text):
    out = repair(text, tools=KNOWN)
    assert out is None or render(out) in normalise(text)                # only what was there
```

---

## Layer 5 — Scheduled live smoke

```yaml
# .github/workflows/live-smoke.yml
on:
  schedule: [{ cron: "0 6 * * *" }]
  workflow_dispatch:
jobs:
  smoke:
    strategy:
      fail-fast: false
      matrix:
        provider: [openai, azure, openrouter, anthropic]
    steps:
      - run: pytest tests/contract -k ${{ matrix.provider }} --live
      - if: failure()
        uses: ./.github/actions/open-drift-issue
```

`fail-fast: false` so one provider's outage does not mask another's real drift.
Ollama runs in the same job against a locally pulled small model.

**Never runs on PRs**, including from forks. Secrets stay out of untrusted builds.

---

## Layer 6 — Evals

Not a gate. Slow, flaky, expensive, and blocking on them would erode trust in the
whole suite.

```yaml
# tests/evals/find_bug.yaml
name: locate the retry bug
fixture: projects/retry_bug
prompt: "find the bug in the retry logic and explain it"
mode: read-only
assertions:
  - kind: mentions_file
    value: "src/client.py"
  - kind: mentions_any
    value: ["429", "rate limit", "backoff"]
  - kind: max_turns
    value: 8
  - kind: max_cost
    value: 0.10
```

```bash
just eval                  # all, default model
just eval --model ollama/qwen3
just eval --compare        # two models side by side
```

Their job is catching regressions unit tests structurally cannot: a change that
makes the system prompt worse breaks nothing and passes everything.

Three measurements the field review asked for, reported per model and per release
alongside pass rates:

- **Skill invocation rate** — in tasks where a skill applies, how often it was
  loaded, with and without `when` triggers (SKL-17). One published eval found an
  agent never invoked the relevant skill in over half the cases
- **Small-model completion** — the task set run against one local model under
  32k context, with the `compact` profile and tool-call repair on and off
  (PRV-16, PRV-17)
- **Tokens before the first answer** — prompt plus schemas at turn one, against
  NFR-13

Every release publishes the eval table, and any change to a shipped prompt is
listed next to its effect.

---

## Cross-platform testing

CI matrix is `{ubuntu, macos, windows} × {3.12, 3.13}`. **No platform skips in
core** [NFR-6]. If a test cannot run on Windows, the code is wrong, not the test.

Specific hazards to cover:

| Hazard | Test |
|---|---|
| Path separators | Property test with `\` and `/` inputs on all platforms |
| Line endings | Assert JSONL uses `\n` even on Windows |
| Shell selection | `shell.program = "auto"` picks Git Bash, then `pwsh`, then Windows PowerShell on Windows, and a POSIX shell elsewhere; the tool description names it |
| Command tools | argv passed with `create_subprocess_exec`, never through a shell, on every platform |
| Sandbox backends | Core tests use a fake sandbox everywhere; `bwrap` tests on Linux, `seatbelt` on macOS, `container` wherever Docker or Podman is present. Backend tests are adapter tests, not core tests, so NFR-6 holds |
| VT mode | Status bar degrades to plain lines when VT is unavailable |
| SQLite locking | Concurrent subagent writes under WAL |
| Signals | Ctrl-C via `CTRL_C_EVENT` on Windows, `SIGINT` elsewhere |
| Long paths | Windows >260 char paths |
| Case sensitivity | Tool name collisions on case-insensitive filesystems |

---

## Startup budget test

Enforces [NFR-1] and [ADR-0012]. Two tests, and the second is the one that holds.

```python
def test_cli_import_pulls_no_heavy_modules():
    code = (
        "import sys, edgar.cli.main;"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "{'httpx','rich','prompt_toolkit','jsonschema','yaml','keyring'}"
        " or m.startswith('edgar.providers.')];"
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "[]", f"heavy imports at CLI import: {out.stdout}"

@pytest.mark.timing
def test_trivial_run_starts_fast(tmp_project):
    t = time_subprocess(["edgar", "-p", "hi", "--mode", "read-only",
                         "--model", "fake/test"])
    assert t < 0.5   # generous on shared CI; the import test is the real gate
```

---

## Coverage

| Package | Target | Why |
|---|---|---|
| `core/` | 95% branch | The loop. Bugs here are everywhere. |
| `permissions/` | 100% branch | Security boundary. Pure function, no excuse. |
| `context/` | 95% branch | Compaction bugs corrupt sessions. |
| `tools/` | 90% branch | |
| `providers/` | 85% branch | Contract suite matters more than line coverage. |
| `providers/routing.py` | 100% branch | Pure function, small condition set, decides what you pay. |
| `memory/`, `agents/`, `extensions/` | 90% branch | |
| `learning/`, `controller/`, `schedule/` | 90% branch | v2; the boundary tests above matter more than the number |
| `cli/` | 60% | Terminal rendering has poor return on test effort. |

Overall gate ≥ 90% on the first four [NFR-8]. Coverage is a floor, not a goal:
100% coverage of the permission matrix means nothing if the hostile-path property
test is missing.

---

## Fixtures

```python
@pytest.fixture
def tmp_project(tmp_path) -> Path:
    """A complete .edgar/ tree: config, agents, skills, empty db."""

@pytest.fixture
def fake_provider() -> FakeProvider: ...

@pytest.fixture
def recorded_events() -> list[Event]:
    """Subscriber capturing the event stream for assertion."""

@pytest.fixture
def frozen_clock(): ...

@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly on any socket call. Applied to the whole offline suite."""

@pytest.fixture
def subprocess_env(tmp_path) -> dict[str, str]:
    """Environment for e2e subprocesses: puts tests/support/ on PYTHONPATH so its
    sitecustomize.py installs the same socket guard inside the child process."""
```

`no_network` is applied to every offline suite: unit, property, contract,
integration and e2e. A monkeypatch does not cross a process boundary, so e2e tests
start the CLI with `subprocess_env`, whose `sitecustomize.py` patches `socket` in
the child. The guard lives entirely in test support; production code has no test
switch. A test that accidentally reaches the network fails immediately rather than
passing slowly and expensively.

---

## Testing the event stream

Often the clearest way to assert loop behaviour, because a test can state the
expected sequence literally:

```python
def test_denied_tool_reports_to_model(fake_provider, recorded_events):
    ...
    assert event_names(recorded_events) == [
        "TurnStarted", "RequestStarted", "ToolProposed",
        "PermissionRequested", "PermissionResolved",   # denied
        "RequestStarted", "TurnFinished",
    ]
```

---

## Commands

```bash
just test              # offline suite, what CI runs on PRs
just test-unit
just test-property
just test-contract
just test-live         # needs keys
just eval
just cov
just check             # ruff + mypy --strict + test
```
