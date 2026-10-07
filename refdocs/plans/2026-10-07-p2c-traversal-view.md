# Plan: P2c Traversal view (what the search followed, for each prompt)

> A follow-on to P2 and P2b, from Azim's message on 2026-10-07 (the first of two parts; the second is `2026-10-07-g1-atomic-graph-experiment.md`). Execution doc: `refdocs/execution/2026-10-07-p2c-traversal-view.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.
> Status: **Approved by Azim 2026-10-07** ("proceed with both"). ADR D-33 accepted with it. Building starts at task T1.

## Why this exists

Azim, 2026-10-07: "I want to upgrade the graph on the top right ... based on how Obsidian is used, and how when information is ingested the docs are broken down into small nodes with relations ... also show the node traversal based on each prompt."

The top-right graph (`GraphView`) draws **what the documents say connects**: edges whose quote names both concepts. It does not show **what the search did**: which concepts the question resolved to, which neighbours the graph signal expanded, which passages that reached, and in what order. That is the part that makes a graph answer inspectable, and it is the part that tells us whether the graph helps or only decorates. This plan builds it with no change to ingestion or to retrieval scoring. The ingestion side of the idea (atomic notes) is the second plan.

## What's already covered (no work needed)

- The graph signal (`api/retrieval/graph.py`) already resolves the question to nodes (deterministic, logged), expands one hop and ranks the chunks that evidence them. It does not record the path it took.
- The Graph agent already resolves the same entities (`resolve_query_entities`), expands neighbourhoods and returns `seeds`, edges and per-edge provenance. `GraphView`, `ConceptMap` and `ComparisonGrid` already render parts of it.
- The Composer, the catalog `Spec` (precondition, fences, check, mutation suite), the layout regions (P2b) and the trace's `ComponentDecision` list exist.
- `TurnTrace` already records which entities resolved (the resolution report) for each turn.

## Scope

**In:**

1. **A traversal record, as a pure function.** `trace_graph_signal(query, graph, docs)` in a new module returns the seeds (node, label, exact or approximate), the one-hop edges followed from each seed (with the chunk each edge was extracted from), and the chunks reached with how (mentions the seed, an edge from it, or only a neighbour) and in the graph signal's own rank order. It reads the same stores and uses the same helpers as `GraphRetriever`; **the retriever is not edited**. A parity test asserts that its chunk scores and order equal `GraphRetriever`'s for every benchmark question (and for synthetic graphs), so the two cannot drift apart. That keeps D-20's frozen scoring untouched.
2. **A new catalog component, `TraversalView`** (D-33), with a written precondition: the graph signal resolved at least one query entity and followed at least one edge to at least one stored chunk. Its payload is data only: seeds, nodes, steps (an edge and its hop), reached passages (a citation each, with a stored chunk's verbatim quote) and the citations. Its validator checks every claim against the stores (the nodes and edges exist, each edge's chunk exists, each reached passage is a stored chunk that the graph reaches that way). This is **provenance**, not "the text states the relation": the view is labelled as what the search followed, and `GraphView` stays the place for what the documents say.
3. **The web component**, through the registry: seeds on the left, the neighbours they reach to the right, edges as lines in hop order, the reached passages as a ranked list with how each was reached, selection by click or keyboard, the five states, text only.
4. **Composer, layout and trace**: admitted by evidence with a closed refusal reason list; placed in the studio's graph area under `GraphView`; the trace panel names it. Saved views may include it (a pattern of `TraversalView` re-runs the traversal on the evidence of the day, no model call).
5. A real-browser run, independent reviews, the usual docs.

**Out (stated so they are not built by accident):**

- Any change to ingestion, extraction, the graph, the retrievers' scoring or the benchmark (all frozen, D-20, D-24). Atomic notes and a better graph are the second plan.
- Multi-hop traversal (the graph signal expands one hop; the view shows exactly that, and says so). The Graph agent's path (`find_path`) is already a `ConceptMap`.
- A whole-corpus "graph view" of every note (Obsidian's graph pane). It is a different component and needs the atomic notes to be worth building; it is listed as a possible follow-on in the second plan.
- Animation of the traversal over time.
- Phone layout.

## Approach

**Why a new component and not more fields on `GraphView`.** `GraphView` guarantees every edge's quote names both concepts (it is the strict, grounded view, with an admission rate of 16 of 20 on the study). A traversal contains edges that fail that test (bare co-mentions) because the search follows them anyway. Mixing the two would either weaken `GraphView`'s guarantee or hide the edges that most need to be seen. Two components with two preconditions keeps each claim honest.

**Provenance, not a second source of truth.** Nothing in the block can say more than the stores do: a seed is a stored node, a step is a stored edge with a stored chunk, a reached passage is a stored chunk whose score the retriever's own rules reproduce. The validator recomputes them. The block carries no model-written text.

**The retriever is untouched.** The traversal is a second, read-only walk over the same graph with the same constants; the parity test is the guarantee that it describes what the retriever does. `GRAPH_SCORING_VERSION` does not change.

**Wire shape (proposal, confirmed by a spike in T1):** `TraversalViewData { seeds: TraversalSeed[]; nodes: GraphNode[]; steps: TraversalStep[]; reached: ReachedPassage[]; citations: Citation[] }` with `TraversalSeed { nodeId, match: "exact" | "approximate" }`, `TraversalStep { source, target, relation, hop }` (hop is 1 today), `ReachedPassage { citationId, via: "mentions" | "edge" | "neighbour", rank }`. Caps in the template's fences: seeds 6, nodes 40, steps 60, reached 10.

## Cost estimate

No paid call is added: the traversal reads local stores, the Composer is deterministic, and the browser run uses the fake model on two real papers (or the existing live stores read-only with the fake model for answers). Expected spend for the phase: $0.

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| The traversal drifts from the retriever's real behaviour | High: the view would mislead | Parity test over every benchmark question and synthetic graphs; the retriever is not edited; a retrieval-auditor review |
| The view is noisy on a graph of 11,173 nodes (a hub entity expands to hundreds of edges) | Medium: unreadable, and over the caps | Fences cap steps and nodes; edges are chosen by the chunk's rank in the graph signal, strongest first; the view says how many it left out |
| Co-mention edges look like facts | Medium | The view's heading and a line of text say it shows what the search followed; relation words are shown as stored; `GraphView` stays the grounded view |
| Real traversals show a poor graph (many seeds resolve to junk) | Low as a risk, high as a finding | That is the point: it is evidence for the second plan; recorded as measured |
| A new component needs a precondition retrieval can satisfy (constraint 7) | Low | Stated above and measured on the 20-question study in T3 |

## Definition of done

- [ ] `trace_graph_signal` exists; its chunk scores and order equal `GraphRetriever`'s on every question of the frozen set and on synthetic graphs (a test); `GraphRetriever` and the protocol stamp are unchanged (`eval/tests/test_frozen_assets.py` green).
- [ ] `packages/schema` defines `TraversalView` and its data; `pnpm codegen:check` exits 0; `catalog.md` documents its precondition, supplier, caps, invariants and placement; the completeness test passes.
- [ ] The validator checks every claim against the stores (a tamper test for each: a node, an edge, a chunk, a hop, a rank, a `via` that the stores do not support); the registration suite refuses a template with a planted hole.
- [ ] The Composer admits it by its precondition with a closed refusal reason, makes no model call, and the trace panel names it (tests); the admission rate on the 20 study questions is measured and reported.
- [ ] The web component renders all five states, is keyboard operable and text-only (tests), and appears under the graph in the studio (a browser capture on real papers).
- [ ] A saved `TraversalView` pattern re-runs the traversal on apply and refuses with a reason when its evidence is gone (a test).
- [ ] `schema-guardian`, `retrieval-auditor` and `cost-auditor` have reviewed it; the full suite, lint, types, codegen check and build are green; STATUS, CHANGELOG, ADR D-33, the file structure guide and the indexes are current.
