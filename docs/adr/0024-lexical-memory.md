# ADR-0024 — Memory stays lexical: no embeddings or graph in core, a retriever port for those who want them

**Status:** Accepted · 2026-09-13 · Reaffirms ADR-0007

## Context

The question: would internal embeddings or a graph make a better memory?

ADR-0007 chose SQLite FTS5 over embeddings for visibility and startup time. The
field review (docs/research/hn-2026-09.md) tested that choice against what people
report from using memory systems:

- **Coding agents need exact recall.** The useful lookups are an error string, a
  function name, a CLI flag. One session-search author chose exact-token search
  over semantic search for exactly this reason
- **The leading harnesses use grep, not embeddings,** and models are trained so
  heavily on grep that they distrust other search results and re-read files anyway
- **Auto-extracted, embedding-consolidated facts degrade.** Users of mem0 and
  ChatGPT memory describe databases filling with wrong or irrelevant entries.
  A memory database author found cosine similarity merging unrelated facts that
  share sentence structure. Contradictions depend on context an embedding does not
  hold
- **Embeddings have real costs here:** an embedding model is hundreds of
  megabytes, or a network call to an embedding API that some providers do not
  offer at all, and results are nondeterministic, which breaks property tests
- **Where embeddings help:** synonyms and mixed languages over large document
  collections
- **The "graph" that users liked** (Beads) is a dependency graph of tasks, not a
  semantic knowledge graph. Explicit structure helped; inferred semantics did not

## Options

**A. Embeddings in core.** Better fuzzy recall. Costs a model or a network call,
nondeterminism, startup, and a mechanism the reader cannot see.

**B. A knowledge graph in core.** Entity and relation extraction by a model.
Costs a model call per write, extraction errors that compound, and a schema that
grows without bound.

**C. Lexical core, explicit structure, a retriever port.** FTS5 for recall, simple
explicit links for structure, and an interface through which an extension can add
vector or graph retrieval.

## Decision

Option C.

**Recall is lexical and deterministic.** FTS5 with two indexes: `porter` stemming
for words and `trigram` for identifiers, paths and error fragments. The `recall`
tool takes a list of terms, so the model can do the synonym work itself
(`["espresso", "coffee", "caffeine"]`); this puts expansion where the semantic
knowledge already is, in the model, at no extra cost. BM25 ranking, with scope
match and recency as tie-breakers.

**Structure is explicit, not inferred.** Facts carry scope, tags and a `supersedes`
link (ADR-0007). That is a small graph a human can read. edgar does not extract
entities or relations with a model.

**The retriever is a port** (ADR-0022):

```python
class Retriever(Protocol):
    name: str
    def search(self, terms: list[str], *, scope: str, kinds: set[Literal["facts", "sessions"]],
               limit: int) -> list[Hit]: ...
    def index(self, item: Indexable) -> None: ...
```

The built-in adapter is `fts5`. A package can register another through the
`edgar.retrievers` entry point, for example sqlite-vec embeddings or a graph store,
and select it with `memory.retriever`. Core and v1 never load an embedding model.
Third-party retrievers are loaded lazily, and a retriever that calls a network API
names its host in config, as every other host must (ADR-0023).

The learning boundary is unchanged by the choice of retriever: a retriever finds
things, it never creates active facts (ADR-0017).

## Consequences

- **Recall is fast, deterministic and testable,** and the reader can see why a
  fact surfaced: the matching terms
- **Synonym recall depends on the model writing good queries,** which current
  models do well. This is a trade, recorded here
- **People with large document collections are not stuck:** the port is there
- **Load-bearing:** the `recall` tool accepts several terms. A single-string query
  would push the expansion problem back onto the index

## Rejected alternatives

**A (embeddings in core)** is rejected on size, determinism, hidden network calls
and teaching value. **What would change the answer:** an embedding model small
enough to ship in the wheel and fast enough to stay off the startup path, together
with evidence that it beats multi-term FTS on real coding sessions.

**B (knowledge graph in core)** is rejected because extraction errors compound and
the review found no evidence of benefit for coding agents. Revisit if a retriever
plugin shows it on the eval set.
