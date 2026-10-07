# Execution: P2c Traversal view

> Plan: `refdocs/plans/2026-10-07-p2c-traversal-view.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07; ADR D-33 accepted.** Task T1 is next.

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, read `refdocs/STATUS.md`, `refdocs/guides/catalog.md` (the recipe), D-20 (frozen graph scoring), D-27 to D-32.
- Fakes first. The whole phase needs no key and spends nothing. The real stores in `data/eval-live-live` are read only.
- **The retriever is not edited.** `api/retrieval/graph.py`, `entities.py` and the protocol stamp are frozen (D-20); `uv run pytest eval/tests/test_frozen_assets.py` runs in every verify.
- **Every wire change follows preflight question 5, in order:** schema first, `pnpm codegen` then `pnpm codegen:check`, the server validator, the web registry, a registration suite with planted defects.
- Read the current docs for anything new in React or Tailwind (context7) before writing against it.

---

### Task T1: The traversal as a pure function, with a parity test

**Files:** `api/retrieval/traversal.py` (new), `api/retrieval/test_traversal.py` (new).

1. Read `api/retrieval/graph.py`, `entities.py`, `api/stores/graph_store.py` and `api/agents/graph_agent.py` in full.
2. `trace_graph_signal(query, graph, docs) -> GraphTraversal` (a frozen dataclass): `seeds` (node id, label, match, weight), `steps` (src, dst, relation, chunk id, hop 1, seed id), `reached` (chunk id, score, via, rank). It resolves with `resolve_query_entities` and expands with `graph.expand(..., hops=1)` exactly as the retriever does, and ranks chunks by the retriever's own key (score, edge support, document order). It imports the retriever's constants rather than copying them.
3. A parity test: for every question of the frozen set run on the pinned live stores if present (skipped with a stated reason if not) and on synthetic graphs (including ties, an approximate entity, two entities sharing a neighbour, a chunk missing from the doc store), the traversal's reached chunks, scores and order equal `GraphRetriever.retrieve`'s.
4. Decide, with the real graph, how a hub is capped (steps are chosen by the reached chunk's rank, strongest first) and say how many were left out.

**Verify:** `uv run pytest api/retrieval -q` and `uv run pytest eval/tests/test_frozen_assets.py -q` pass; the parity test passes on the real stores; `git diff` shows no change under `api/retrieval/graph.py`, `entities.py` or the protocol files.

**Reality (T1 done 2026-10-07):** `api/retrieval/traversal.py`: `trace_graph_signal(query, graph, docs, top_k)` returns the seeds, every edge followed (one hop, per seed), and the chunks reached in the retriever's rank with how each was reached (`mentions`, `edge` or `neighbour`, the strongest across seeds, plus which seeds reach it); it imports the retriever's constants and replicates its scoring and tie-break, and `GraphRetriever`, `entities.py` and the protocol files are untouched. `api/retrieval/test_traversal.py` (9 tests): handmade graphs by hand (edge vs mentions, scores adding across seeds, two hops not followed, an approximate match, a chunk missing from the doc store, `top_k`, nothing resolved, no mutation, repeatability) and the parity test **on the pinned live stores for all 20 frozen questions** (it ran, not skipped): chunks, scores, order and the resolution report equal the retriever's. `steps_for_display(traversal, limit)` was changed during the task: it returns only the steps whose chunk is one of the reached passages (best rank first) and counts the rest, never padding with edges that led nowhere. **What the real traversals look like (measured on the 20 questions, the numbers that set the caps):** 4 to 10 seeds per question; 16 to 755 edges followed (nodes touched 17 to 470); the top-ten reached chunks are almost all `mentions` (a seed's own chunk), the neighbour hop reaches a top-ten chunk on only 6 of the first 14 questions seen and then in 1 to 6 places; and several seeds are generic words the question resolves to (corpus, text, concepts, Findings, Retrieval, RAG, OpenAI). So the view must show seeds with their match kind, show only the edges that led to returned passages, and say how many it left out; the junk seeds are a finding about entity resolution, shown honestly. Verified: `uv run pytest api/retrieval` 71 passed; `eval/tests/test_frozen_assets.py` 7 passed; ruff and pyright clean; `git status` shows only the two new files under `api/retrieval/`.

### Task T2: The wire type, the template and its validator (schema first)

**Files:** `packages/schema/src/{blocks,payloads}.ts`, `api/genui/generated.py` (generated), `api/genui/catalog.py`, `api/genui/validate.py`, `api/genui/builders.py`, `refdocs/guides/catalog.md`, tests.

1. Write the types in the schema (`TraversalView` in the `UIBlock` union, `TraversalViewData`, `TraversalSeed`, `TraversalStep`, `ReachedPassage`); `pnpm codegen`; `pnpm codegen:check`. Spike the shape first in a scratch copy if codegen needs to learn anything.
2. Write the section in `catalog.md` first (precondition, supplier, caps, invariants, placement), then the `Spec` with fences (seeds 6, nodes 40, steps 60, reached 10) and a check.
3. `validate_block` rules, each checked against the stores: every seed and node is a stored node, every step is a stored edge whose chunk exists, every reached passage is a stored chunk that the graph reaches by the stated `via` and whose citation has a verbatim quote, ranks are 1..n unique, caps, every citation cited. Unknown or extra fields refused (strict models).
4. Registration suite with planted defects (a fake node, an edge that is not stored, a chunk reached a different way, a rank gap, an over-cap list, a quote that is not verbatim): each must be refused, and every cap is guarded.

**Verify:** `uv run pytest api -q` passes with a tamper test for each claim, the completeness test (schema union, builders, catalog, web registry agree) and the registration suite; `pnpm codegen:check` exits 0.

### Task T3: Graph agent, Composer, trace, layout

**Files:** `api/agents/graph_agent.py`, `api/agents/compose.py`, `api/genui/catalog.py`, `api/genui/layout.py` (data only), trace types in the schema, tests.

1. The Graph agent's payload carries the traversal (a plain dict, from T1); no new tool is needed.
2. The Composer admits `TraversalView` by its precondition; closed refusal reasons (no graph result, nothing resolved, no edge followed) in the trace's reason list; no model call (a test).
3. Placement hint: studio, main region, priority 25 (under `GraphView`). Saved views: `TraversalView` is a reusable template whose slot is the entity labels; apply re-runs the traversal on the evidence of the day and refuses with a reason when it no longer holds.
4. Run the 20 study questions (`eval/bound.py` gains the component) and record the admission rate and the refusal reasons.

**Verify:** tests for admitted and refused cases, the saved-view apply and refusal, no provider call (`FakeProvider.calls == []`); the study result is written to `eval/results/` with the commit and hashes.

### Task T4: The web component

**Files:** `web/components/genui/TraversalView.tsx`, `traversalLayout.ts`, tests, `registry.tsx`.

1. Layout by hop: seeds in a left column, the concepts they reach in a right column, edges between them, deterministic positions (as `graphLayout.ts`). The reached passages as a ranked list beside or below, each with how it was reached in words ("mentions the seed", "an edge from the seed", "a neighbour's passage") and its source link.
2. Select a node or a passage by click, Enter or Space: highlight what connects to it and show its quote. Five states, text only, no markup from stored strings, anchors built with `safeId`. A line of text says what the view is ("what the search followed for your question, not what the documents state").
3. Say how many steps were left out by the caps.

**Verify:** component tests for all five states, keyboard operation, the left-out count, hostile labels rendered as text; `pnpm -r typecheck`, `lint` and `test` pass.

### Task T5: A real browser, reviews and wrap-up

1. Playwright at 1440 by 900 on the real stores (read only) with the fake model for answers: three real benchmark questions, a saved view of a traversal applied after a reload; captures in `refdocs/evidence/p2c-*.png`. State what a real traversal looks like on this graph (how many seeds, how many steps, how many left out, how much junk).
2. `schema-guardian`, `retrieval-auditor` and `cost-auditor` (read only), `test-runner` equivalent twice; fix blocking findings with tests.
3. Update STATUS, CHANGELOG, DECISIONS (D-33), the PRD row, `file_structure.md`, `catalog.md`, both indexes and the plan's definition of done item by item. Run `/session-end`.

**Verify:** every box in the plan's definition of done is ticked with a note or marked partly met or unmet; `git status` clean after the commit; nothing pushed.

---

## Task order at a glance

`T1` traversal function and parity → `T2` wire type, template, validator → `T3` Graph agent, Composer, trace, layout → `T4` web component → `T5` browser, reviews, wrap-up.
