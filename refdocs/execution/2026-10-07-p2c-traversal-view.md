# Execution: P2c Traversal view

> Plan: `refdocs/plans/2026-10-07-p2c-traversal-view.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Done 2026-10-07** (T1 to T5). Approved by Azim 2026-10-07; ADR D-33 accepted.

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
2. Write the section in `catalog.md` first (precondition, supplier, caps, invariants, placement), then the `Spec` with fences (seeds 10, nodes 40, steps 60, reached 10) and a check.
3. `validate_block` rules, each checked against the stores: every seed and node is a stored node, every step is a stored edge whose chunk exists, every reached passage is a stored chunk that the graph reaches by the stated `via` and whose citation has a verbatim quote, ranks are 1..n unique, caps, every citation cited. Unknown or extra fields refused (strict models).
4. Registration suite with planted defects (a fake node, an edge that is not stored, a chunk reached a different way, a rank gap, an over-cap list, a quote that is not verbatim): each must be refused, and every cap is guarded.

**Verify:** `uv run pytest api -q` passes with a tamper test for each claim, the completeness test (schema union, builders, catalog, web registry agree) and the registration suite; `pnpm codegen:check` exits 0.

**Reality (T2 done 2026-10-07):** Schema first: `TraversalView` in the `UIBlock` union and `TraversalViewData` (`seeds`, `nodes`, `steps`, `reached`, `citations`, `stepsLeftOut`), `TraversalSeed`, `TraversalStep`, `ReachedPassage`, `SeedMatch`, `ReachedVia`, and three closed refusal reasons added to `DecisionReason` (`nothing_resolved`, `no_edge_followed`, `too_many_seeds`); codegen fresh. The `catalog.md` section was written first. **The validator re-derives the block:** `validate_block(raw, docs, graph=None)` now takes the graph store (a TraversalView without one is refused); it re-runs `traverse(seeds, graph, docs)` from the block's seeds and requires exactly the block's passages (chunk, `via`, `rank`, reaching seeds), steps (the edges that led to returned passages, best rank first, within the caps) and `stepsLeftOut`, plus the plain rules (stored nodes with stored labels, unique ids, caps, citations stored and verbatim, every step citing a listed passage). To make that possible `traversal.py` was refactored into `trace_graph_signal` (resolve) and `traverse(seeds, ...)` (a function of seeds and stores); the parity test still passes on all 20 live questions. `steps_for_display` gained a node cap. **Decisions the build made:** (1) the count and node-set mismatches have their own paths (`data.steps.(count)`, `data.reached.(count)`, `data.nodes.(set)`) so a cap loosened until a defect slips through is not masked by the re-derivation rejecting the same block at the cap's own path (the loosened-cap test caught this on `steps`); (2) the label-length cap is guarded by a stored node whose label is over the cap (in the fixture graph); (3) the template **is reusable** (the repo's test says graph-supplied templates are): a new `Slot.source` says the slot's labels are the traversal's seeds, so a saved view re-runs the traversal from those labels. The registration suite plants 33 defects, each cap guarded, and a `fixture_graph()` joins `fixture_store()` (another small instance of the concrete-store-in-a-fixture issue noted in P2 D3). A bug found by the tests: fakes in older tests lacked `ordinal`, which the ranking tie-break needs; they were given one (the code was not weakened). Verified: `uv run pytest` 829 passed, ruff and pyright clean, `codegen:check` OK.

**Reality (T3 done 2026-10-07):** The Graph agent's payload carries `traversal` (seeds with match, the displayed steps, `steps_total`, `left_out`, the passages reached); the Composer admits by `_check_traversal_view` and builds the block (`_traversal_data`: one citation per passage with a verbatim quote preferring a span that holds a reaching seed's label, each step citing the passage its edge came from); no provider call (a test); placement hint studio, priority 25; the trace panel has words for the three new reasons; saved views list `TraversalView` as "Search path". `eval/traversal_admission.py` (free, no model or network, 3 tests) measured **admission on the 20 frozen questions: 20 of 20**, with 3 to 10 seeds per question (41 of 111 approximate), 16 to 755 edges followed, 5 to 54 steps shown, and **87 percent of the graph signal's top-ten passages mention a seed and 13 percent come through a neighbour**; the zero for "an edge alone" is structural, and edge support breaks ties among equal scores (see `refdocs/evidence/20261007T012421Z-traversal-admission.md`, reworded after the retrieval auditor's review). Headline: most of what the graph signal returns is chunks that mention a resolved concept, so the quality of resolution and of the nodes matters most.

**Reality (T4 done 2026-10-07):** `TraversalView.tsx` and `traversalLayout.ts`: a two-column diagram (seeds left, reached concepts right; deterministic, tested at 10 seeds and 40 nodes), a steps list, the passages reached in rank order with how each was reached in words, a details area for the selected concept or passage, the count of steps left out, and a line saying it shows the route and not what the documents state. Five states; click, Enter and Space; text only; anchors through `safeId`. The registry, `toErrorBlock`, the trace panel, the saved-view names and the fixtures know the new type. Verified: web 245 passed, typecheck and lint clean, build exit 0.

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

**Reality (T5 done 2026-10-07):** Browser run at 1440 by 900 with the API in fake mode on a scratch directory and two real papers uploaded; three captures in `refdocs/evidence/p2c-*.png` (01 the Adaptive dashboard with the graph, 02 the search path scrolled into view: seeds in amber on the left, reached concepts on the right, the steps list, 03 the passages reached in rank order, each saying how it was reached, with its quote). **What it showed:** the view renders in the studio's graph area under the graph and above the saved shelf; with the fake extractor's junk entities ("Gen", "Section II", "Upon") it is a faithful picture of a poor graph, which is the point; the studio's graph area is now crowded (GraphView, TraversalView and ConceptMap stack in one scroll region), an argument for the notes view and for tabs, recorded as a gap. **Not shown:** the view on the real 16-paper graph in a browser (that needs live query embeddings, a few thousandths of a cent, and was not run; the real traversals were measured by the free admission study instead). The first attempt to start the API with live embeddings was denied by the permission system and not retried. **Reviews** (named agent types, read only): `schema-guardian`: no blocking finding; fixed with tests: a saved search path with 9 or 10 seeds could never be applied (the apply check read only the question's first 8 entities; `resolved_labels` now reads both lists), the validator turns a failed re-derivation into a refusal, the internal dataclasses were renamed `SeedNode` and `FollowedEdge` so they cannot be confused with the wire models, `seed_weight` imports the resolver's constant; the guide's stale lines were corrected. `retrieval-auditor`: the retriever and every pin are unchanged and the traversal reproduces it; **one blocking finding about reporting: "the graph signal is mostly entity linking" overreached** (the zero for an edge alone is structural; edge support breaks ties among equal scores and changed 15.5 percent of slots in the auditor's recomputation): reworded in the evidence record, the changelog and here. `cost-auditor`: no paid call, ledger unchanged (1,759 rows, $6.172354); per-turn compute measured (about 0.2 to 0.35 s, bounded); and findings about G1's cost estimate, now in the G1 plan (a one-paper pilot first). **Verified:** `uv run pytest` 830 passed twice, then 833 after the review fixes; ruff, pyright, `codegen:check`, typecheck, lint clean; web 245 passed; build exit 0 (before the review fixes, which touched no web code); frozen assets 7 passed.

---

## Task order at a glance

`T1` traversal function and parity → `T2` wire type, template, validator → `T3` Graph agent, Composer, trace, layout → `T4` web component → `T5` browser, reviews, wrap-up.
