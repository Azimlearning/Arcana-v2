# Plan: genui-obsidianmark2, the compiled vault (links, concept pages, claims, a notes view, a learner layer, lint)

> Follows G1 (`2026-10-07-g1-atomic-graph-experiment.md`, "Mark 1"). Execution doc: `refdocs/execution/2026-10-07-m2-obsidianmark2-vault.md`. ADR: D-35.
> A plan says **what and why**. The execution doc says **how and in what order**.
> Status: **Approved by Azim 2026-10-07** ("im okay with doing a to g the cost i can manage ... pls proceed make sure everything is on track"). Directions A to G below are all in scope. **Each paid step still needs Azim's confirmation of its amount first**, and the monthly cap ($10, about $2.44 left) is his to raise.

## Why this exists

Mark 1 (the atomic builder g1-3, TraversalView, the variant tool) was measured on a 3-paper slice (285 passages, 19 questions): retrieval about equal to the frozen baseline from a graph a third of the size; its edges mostly sensible where the baseline's are often noise; but **thin**. 73 percent of its nodes had no edge, 39 percent of passages carried a relation, only 221 of about 916 proposed relations survived, the frozen resolver recognised fewer of a question's words (0.389 against 0.546), and one registered clause failed by 0.0056.

Three free measurements on the saved Mark 1 data (2026-10-07, no model call, `refdocs/evidence/20261007-m2-brainstorm-probes.md`) say where the losses are:

| Probe | Result |
|---|---|
| Concept labels the model proposed that occur in their chunk | 83 percent (29 concepts, 4 saved replies) |
| Proposed relations with both labels in one sentence | 36 percent (11 relations): this, not copying, is the real limit of a one-sentence rule |
| A deterministic sentence co-mention layer over the same 744 nodes | 674 links against 173 asserted; passages with at least one link 184 of 285; nodes with no link of any kind 41 percent against 73 percent |

So the next step is **not** a better copying prompt. It is to treat the graph as a **vault**: layers of notes, each tied to a source sentence, some asserted by a model and some found by the server for free.

## What's already covered (no work needed)

- The atomic builder g1-3, its drop accounting and its checks (`api/ingestion/atomic.py`), kept as the reference. The free-form builder and the pinned graph stay frozen (D-20, D-34).
- The variant tool (`eval/graph_variant.py`: slice, rebuild, compare, choose, audit), the structure metrics (`eval/graph_quality.py`), the stores, the ledger and cap, `TraversalView`.
- The Mark 1 slice and its results: the baseline and atomic g1-3 data directories, 19 answerable questions, the registered Mark 1 gate and its failed clause (kept as history, not reinterpreted).

## The idea: four layers

1. **Passages** (exists): source text, never changed.
2. **Mentions and links.** The server finds every concept mention in every passage (Obsidian's "unlinked mentions"). Links are of two strengths: **asserted** (a typed relation a model stated and the server checked against a sentence) and **co-mentioned** (two concepts in one sentence, found by the server, free and deterministic). Every link points to a sentence.
3. **Concept pages.** One page per concept across all papers, sitting **above** the nodes as a list of node ids (nodes are never merged, so the frozen resolver still works): aliases, defining sentences quoted exactly, backlinks, typed links, "appears in N papers".
4. **Claim notes.** A sentence that states a finding becomes its own note, linked to the concepts it names. Retrieval at the level of one proposition, and the raw material for quizzes and flashcards.

## The seven directions (all in scope)

| | What | Cost | Where it lands |
|---|---|---|---|
| **A** | Free links and pages: a deterministic `compile_vault(graph, docs)` over any graph | $0 | `api/vault/` (new), a `VaultStore` abstraction |
| **B** | Point at sentences, not copies: the prompt numbers the sentences; the model returns concepts, typed relations and claim sentence numbers; the **server** chooses and checks the sentence (relations may use a window of two adjacent sentences, declared). Builder `atomic2` (prompt `g2-1`) | about $0.7 to $1.1 for the slice (assumed from smaller output; measured at the rebuild) | `api/ingestion/atomic2.py` |
| **C** | Concept-first retrieval as a **new** arm: question to pages (lexical aliases, then a rank-based semantic step), then backlinks, then passages; asserted links count more than co-mentions; a spread discount for concepts found everywhere | $0 to build; query embeddings and page-label embeddings under $0.001 | `api/retrieval/vault.py` (new arm; the frozen graph retriever is untouched) |
| **D** | Claim notes, extracted in B's call as sentence numbers only | inside B | `Claim` in the vault; not in the graph, so the frozen graph signal is unaffected |
| **E** | The notes view: a page per concept, a backlinks list, a local graph, unlinked mentions, TraversalView paths over pages | $0 | schema, validator, catalog entry, web component, route |
| **F** | The learner layer: per-concept mastery from self-ratings and, when the Studio generators exist (P5), from quiz results; the graph colours by it | $0 | learner store, events route, mastery on the page |
| **G** | Compounding and lint: a new document recompiles the vault; a lint report (orphan pages, near-duplicate pages awaiting review, pages defined differently in different papers, hub pages). Contradiction **judging** needs a model and is out of scope (flagged, not built) | $0 | `api/vault/lint.py` |

**Build order (free first):** A, then C on the existing Mark 1 graph and a measurement (before any money is spent, so we know whether links and pages help); then B+D with a paid rebuild (Azim confirms the amount); then E, F, G. The tasks and their gates are in the execution doc.

## Out (stated so it is not built by accident)

- Editing any pinned store, question, gold annotation, scoring constant or result; the frozen graph retriever and `GRAPH_SCORING_VERSION` are not touched. Vault retrieval is an **additive arm** with its own version (`vault-1`).
- Merging nodes by judgement (kept: pages are a layer over nodes, with the merge list recorded).
- An LLM judge of contradictions between claims; a trained entity linker; user editing of notes; the Studio generators themselves (P5; the learner layer takes events from self-ratings until they exist); the phone layout.
- RAGAS (installed at the end of the project).

## How it is measured (fixed in D-35 before any run)

- **Same slice and questions as Mark 1** (3 papers, 285 passages, 19 answerable). It is a **declared second look**: the design was informed by Mark 1's aggregate results and the free probes, not by any single question; weights are set a priori; every further change after seeing a vault result is a new version and a counted look.
- **Arms** over each data directory: the frozen `graph`, `hybrid`, `flat` (control), plus `vault`, `hybrid_vault`, `vault_sem`, `hybrid_vault_sem`.
- **Primary:** Recall@10 and nDCG@10, paired, with improved/tied/worsened counts; descriptive only with 19 questions. Nothing a model scores is primary.
- **Registered gate (a Mark 2 gate, declared before any run, replacing Mark 1's top-1% clause for the vault):** page coverage, page connectivity, question-word recognition no worse than the baseline's, and no large retrieval drop against the frozen baseline. The Mark 1 top-1% share is still computed and reported.
- **Free ablations** on one build: co-mentions on or off, spread discount on or off, claims on or off.

## Cost estimate

| Step | Paid calls | Estimate |
|---|---|---|
| M2.1 to M2.3 (vault core, retriever, tool) | none; query embeddings are cached from the Mark 1 comparison where the text matches | $0 (at most $0.0001) |
| M2.4 rebuild the slice with `atomic2` (285 chunks) | extraction, Haiku tier | about $0.7 to $1.1 (assumed; the Mark 1 builder measured $0.0038 per chunk, $1.0879; `atomic2` returns no sentences for concepts, so output should fall); a ceiling is given to the tool and enforced per call |
| M2.5 page-label embeddings | embeddings | under $0.001 |
| M2.6 to M2.9 | none | $0 |
| Full 16 papers with `atomic2` (not planned here) | extraction | about $4 to $6; needs the cap raised or the 2026-11-01 reset |

The month total is $7.5557 of $10 ($2.4443 left). The rebuild fits inside it at the expected figure and is refused by the ledger past the cap.

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| Co-mention links are noisy (a sentence naming two concepts does not mean they are related) | Medium: lower precision of the graph arm | They carry a quarter of an asserted link's weight; sentences naming more than six concepts (lists, author lines) make no links; people and organisations make none; the blind audit samples both link kinds |
| "RAG" is in a quarter of the passages, so a page for it floods the ranking | High for retrieval | The spread discount is part of the registered arm (`vault-1`) and an ablation measures it |
| The 19-question slice cannot separate small differences | High for any claim | Reported as descriptive; the structural results and the audit carry the story; the full 16-paper run is the next look and is Azim's call on cost |
| Looking at the same questions twice (Mark 1 then Mark 2) | Medium: a forking-paths risk | Declared and counted in D-35 (a looks ledger); constants are fixed before the run |
| The notes view is a large UI task with new wire types | High | Schema first; the page is validated by re-deriving it from the vault, like TraversalView; all four states; `schema-guardian` reviews before shipping |
| Learner data is personal | Low in a single-user build | Stored locally; events only; no secrets; deletable |
| The builder `atomic2` loses concepts the model names but the server cannot find in any sentence | Medium | Counted per reason; the g1-3 results show about a third of proposed concepts are lost to the copy rule, which this removes |
