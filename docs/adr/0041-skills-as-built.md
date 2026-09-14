# ADR-0041 — Skills as built: one module and a tool, humans before machines, skill verify to v1

**Status:** Accepted · 2026-09-14 · Refines ADR-0014 (verification sources) and BLUEPRINT §6.6; amends PRD §5.1 (what Core keeps)

## Context

M6 built skills: `SKILL.md` folders found at startup, one line per skill in the
prompt, and a `skill` tool that loads a body when the model asks. It also built
`edgar skills list|validate` and `edgar tools list|describe`. M6 started with
about 175 lines of code of Core budget. Building it settled five things the spec
left open or got slightly wrong.

## Options and decisions

**1. Where the body is loaded.** The Blueprint sketched `skills/loader.py` beside
`skills/discovery.py` and `tools/builtin/skill.py`. A loader module would hold one
function that the tool alone calls. **Decided:** the tool is the loader.
`tools/builtin/skill.py` reads the file and drops the frontmatter with
`discovery.split`, which saves a module's overhead and a hop for the reader.

**2. Which skill wins a name.** SKL-3 says "project wins, hand-authored wins over
learned", which leaves one case open: a skill learned in the project against one a
human wrote at user scope. **Decided:** anything a human wrote beats anything
learned, whatever its scope. The order, lowest first, is user learned, project
learned, user, project. A machine-written skill must never shadow a human's
instructions (ADR-0017's boundary, applied to names). Every replacement is a
startup warning, as for tools (TOOL-9).

**3. A skill's `verify` command.** VER-1 lists a loaded skill's frontmatter as a
verification source, and PRD §5.1 put all sources in Core. Doing that properly
means a shell command, taken from a file the model chose to load mid-turn,
becomes the gate's check. VER-4 decides the verify command before the turn
starts, so a run that would need a prompt fails early. A skill loaded mid-turn
breaks that: the command would have to be authorised in the middle of the turn,
and in `-p` nobody is there to answer. (A) Build it anyway, asking mid-turn:
about 30 lines of code, plus a permission path the loop does not have today.
(B) Authorise every skill's command at startup: this asks about checks that may
never run. (C) Move it to v1, next to deterministic activation (SKL-17), which has
the same question of what a skill may cause without the model's say-so.
**Decided: C.** In Core the `verify` field is accepted and ignored, which is
exactly what other harnesses do with it. `--verify` and `verify.command` still
work.

**4. Scopes with nothing in them yet.** SKL-3 also lists bundled skills and
enabled extensions' `skills/`. edgar ships no bundled skill, and extensions arrive
in M10. **Decided:** discovery reads the four scopes that can hold a skill today.
The bundled scope arrives with the first skill worth bundling, and extension
scopes arrive with M10.

**5. Trust and presence.** A skill is instructions, like `AGENTS.md`, so a
project's skills load without `edgar trust`. A script a skill bundles still runs
only through the `shell` tool and its permission check. `.edgar/skills/**` is
already a control file (PERM-12), so the model cannot rewrite a skill without
asking. **Decided:** there is no trust gate for skills, and the `skill` tool is
registered only when at least one skill exists, so a project without skills pays
no schema tokens and never imports PyYAML (NFR-1).

Smaller choices: `name` must be lowercase letters, digits and hyphens and match
its folder, as Claude's format requires, so a skill written for one harness works
in the other. A broken `SKILL.md` is skipped with its reason as a startup warning,
never fatal, and `edgar skills validate` exits 1 for it. `edgar tools list` shows
what a session here would get: a project's tools appear only once it is trusted.

## Consequences

- Core stands at 4,966 of 5,000 lines of code after M6, which leaves 34.
  PyYAML joins the runtime dependencies, imported only once a `SKILL.md` exists.
- PRD §5.1 now maps SKL-1's `verify` field and VER-1's skill source to v1.
- The tour's stop 19 is built, as a sixth Core stage: "The know-how".
- `examples/` holds a command tool, an HTTP tool and a skill, each tested as it
  ships, so the docs' recipes cannot drift from what loads.

## Rejected alternatives

**3A** is the one worth revisiting. If v1's activation work gives the loop a way
to authorise something mid-turn, a skill's verify command should use the same
path.
