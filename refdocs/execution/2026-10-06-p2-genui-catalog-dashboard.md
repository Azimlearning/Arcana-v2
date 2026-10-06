# Execution: P2 GenUI catalog + adaptive dashboard (level 1 and level 2)

> Plan: `refdocs/plans/2026-10-06-p2-genui-catalog-dashboard.md`. Tasks run in order within each track. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: approved by Azim 2026-10-06 with ADRs D-27 to D-30 already recorded. Nothing here has been run.

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, read `refdocs/STATUS.md`.
- **Fakes first.** Tracks A to C run on fakes (`ARCANA_LLM_MODE=fake`, `ARCANA_EMBED_MODE=fake`) and need no keys. Track D uses the real ingested stores in `data/eval-live-live` (read-only) and a few cents of real calls; the keys are already in Azim's `.env`.
- **Every wire change follows preflight question 5, in this order, every time:** (1) `packages/schema` first, (2) `pnpm codegen` then `pnpm codegen:check`, (3) the server validator handles it and fails closed, (4) a registry entry and a component with all four states, (5) the component's structural precondition written down in `refdocs/guides/catalog.md` and satisfiable by retrieval. Tasks B1 to B5 and C1 spell this out; do not skip a step because the types compile.
- Do not touch retrieval, the protocol stamp, the extraction prompt, the gold, the questions, the manifest or the ingested stores. `uv run pytest eval/tests/test_frozen_assets.py` runs in every verify as a tripwire.
- No paid call is added by this phase. Any task that appears to need one stops and goes back to the plan.
- v1 is at `../Arcana/` (read only). Port with provenance headers (the shell frame only, task C2). Synapse is not on this machine: nothing is ported from it.
- Never build the second of anything until the first is green end to end: components are built one at a time (B1 to B5) and the layout comes after the second component exists.

---

## Track A: foundations (no new components yet)

### Task A1: Read the docs, write the catalog and the agent map

**Files:** `refdocs/guides/catalog.md` (new), `refdocs/guides/agents.md` (new), a scratch copy of the schema package outside the repo (the spike). The decisions themselves (D-27 to D-30) are already in `refdocs/changelog/DECISIONS.md` and the PRD §7.

1. **Read the actual sources before writing a type.** Read `packages/schema/codegen/to_python.ts` end to end (which TypeScript shapes it supports: unions of 5 or more variants, nested arrays, nullable fields, optional fields, string-literal unions, the `@int` tag, any limit it states). Read the current Pydantic docs on discriminated unions with `Annotated[... | ..., Field(discriminator=...)]` and `TypeAdapter`. Read the current React 19 docs for the `inert` attribute and the current Tailwind v4 docs for theme tokens (v1 used Tailwind v3 token classes such as `bg-paper`; v2's `globals.css` is CSS-first). Use context7 or the official sites, not memory.
2. **Spike, in a scratch directory, not the repo.** Copy `packages/schema` to a temporary folder, add a throwaway 5-variant union with a nested array and a nullable field, run its codegen into a scratch output, and import the result: `TypeAdapter(UIBlock).validate_python` must select the right variant and reject an unknown field and a wrong type. Delete the scratch copy afterwards. Record what worked and what did not in the execution doc.
3. **Write `refdocs/guides/catalog.md`** before any schema type (constraint 7). One section per component in the plan's table (`CitedSummary`, `SourceList`, `GraphView`, `ComparisonGrid`, `ConceptMap`, `InsightCard` marked stretch): structural precondition, supplied by, caps, content invariants the validator enforces, which states it renders and what each shows, its **placement hint** (preferred panel and priority), and why it is or is not admissible with flat retrieval. Add the "not admitted, and why" table from D-29, and a **"How to add a component" recipe**: the ordered steps (catalog entry with precondition and placement hint; schema type; codegen; validator rules; builder; Composer admission is automatic from the catalog; web component with four states; admission and tamper tests; a row here), written so task C1's toy-component test can follow it literally.
4. **Write `refdocs/guides/agents.md`**: a table mapping each of v1's agents (Orchestrator; Research, Graph, Learning, Writing, Socratic Tutor, Discovery, Methodology, Debate, Annotation, Comparator, Contradiction, Cross-document, Literature, Timeline; UI, Citation, Visual, Document, Audio; Fact Checker, Memory, Study Planner, Web Search) to its v2 home under D-30 (a core agent and tool group, or a stated drop), the rule for when something may become an agent, and which tools exist today versus which arrive in which phase. Read v1's tiers in `../Arcana/docs/arcana_prd.md` (sections TIER 1 to TIER 4) and `../Arcana/api/agents/` while writing it.

**Verify:** `catalog.md` exists with a section for each of the six components, each naming a precondition, a supplier, caps, invariants and a placement hint, and a recipe section; `grep -c "^## " refdocs/guides/catalog.md` is at least 7. `agents.md` has a row for every v1 agent listed above (a test-free check: `grep -c "^|" refdocs/guides/agents.md` is at least 25 plus the header). The ADR ids D-27 to D-30 exist in `DECISIONS.md` and in the PRD §7 table (`grep -c "^| D-2[7-9]\|^| D-30" refdocs/arcana-v2-PRD.md` is 4). The spike's result is written down (it produced valid Python and a correct variant selection, or it names exactly what failed and the task list is amended before B1). `git status` shows no new files under `packages/schema` or `api`.

### Task A2: Shared evidence helpers (a refactor with no behaviour change)

**Files:** `api/genui/evidence.py` (new), `api/agents/research.py`, `api/agents/test_research.py`, `api/genui/test_evidence.py` (new).

1. Move `best_excerpt`, `verified_quote` and the whitespace normaliser out of `research.py` into `api/genui/evidence.py` (a neutral module; neither the Composer nor an agent should import the other to get them). Re-import them in `research.py`.
2. Add `excerpt_containing(chunk_text, labels) -> str | None`: a sentence of the whitespace-normalised chunk, at most 240 characters, that contains **every** label (case-insensitive, normalised), or `None`. It must return a verbatim span so it always passes the validator's quote rule. A quote that is too short to be evidence (under 20 characters unless the chunk is shorter) is not returned.
3. Add `label_in_quote(quote, label) -> bool` using the same normalisation, for the validator's relational rule.

**Verify:** `uv run pytest api/agents api/genui -q` passes with the same number of existing tests plus the new ones; `uv run pytest api/genui/test_evidence.py -q` covers: a sentence with both labels is returned, one label only returns `None`, a label split across a line break still matches after normalisation, a result is always a substring of the normalised chunk, a too-short span is refused. `uv run ruff check api eval scripts` and `uv run pyright api eval` are clean.

### Task A3: The catalog spine and a multi-block Composer

**Files:** `api/genui/catalog.py` (new), `api/agents/compose.py`, `api/agents/state.py`, `api/agents/graph.py`, `api/agents/test_catalog.py` (new), `api/agents/test_agents.py`.

1. In `catalog.py` define `ComposerEvidence` (a frozen dataclass built from `TurnContext`: the research answer after the Fact Checker, the Graph agent's payload, the document list, the intent; no store handles, so every check is a pure function of data) and `Spec` (name, precondition statement, supplied_by, caps, a **placement hint** `(preferred panel, priority)`, `check(evidence) -> Result`, where `Result` carries `satisfied` and a list of short reason codes). Register `CitedSummary` only.
2. Refactor `compose.py` so the Composer returns a `Composition` (blocks plus a record per component: offered or refused, reasons) built by walking the catalog. Behaviour for the existing single-block turn must not change: the same block, the same error and empty handling, the same fail-closed fallbacks.
3. `run_turn` streams the loading block, then every block of the composition, then `done`. Keep the stream's upsert-by-id semantics. Keep the check that only `compose.py` imports `api.genui.builders`.
4. Add a completeness test that compares four sets: the `UIBlock` variant tags in `api/genui/generated.py`, the catalog's registered names, the keys of the builders dispatch, and the section titles in `refdocs/guides/catalog.md`. At this point they are `{CitedSummary}` each (the doc has six sections; the test compares only components marked built, see B1 to B5, and the test is updated as each is added).

**Verify:** `uv run pytest -q` passes (the full suite, expected 524 plus the new tests), including `api/test_api.py` end to end and `api/agents/test_agents.py`; a new test asserts a turn produces exactly one `CitedSummary` and one record `admitted`; a new test asserts the Composer issues zero provider calls (`FakeProvider.calls` is unchanged by composition, counted around the compose step); `uv run pytest eval/tests/test_frozen_assets.py -q` passes.

---

## Track B: the components, one at a time

Each task below is the full preflight-5 sequence for one component. The pattern is fixed by B1; B2 to B5 repeat it. After B1, run `schema-guardian` once on the pattern before building the next component.

### Task B1: `SourceList` (the simplest, to prove the pattern)

**Files:** `packages/schema/src/payloads.ts`, `packages/schema/src/blocks.ts`, `api/genui/generated.py` (generated), `api/genui/validate.py`, `api/genui/builders.py`, `api/genui/catalog.py`, `api/agents/compose.py`, `web/components/genui/SourceList.tsx`, `web/components/genui/registry.tsx`, tests beside each, `refdocs/guides/catalog.md`.

1. **Schema first.** `SourceListData { documents: SourceItem[] }`, `SourceItem { docId, title, /** @int */ chunkCount }`; add the variant to the `UIBlock` union. No free-text field beyond the stored title.
2. `pnpm codegen`, then `pnpm codegen:check` must pass. Confirm the union is now a discriminated union in `generated.py` and that existing `CitedSummary` tests still pass.
3. **Validator (fail closed).** For a non-placeholder block: at least one document, at most 50, ids unique, each `docId` exists and is `ready`, `title` and `chunkCount` equal the stored values. Placeholder statuses (`empty`, `loading`, `error`) carry no documents.
4. **Precondition** in the catalog: at least one ready document. Builder in `builders.py`. Composer admits it when satisfied and records the refusal ("no ready document") when not.
5. **Web.** A component with all four states (`loading`, `empty` = no documents, `partial` not emitted, `error`), registered in the typed registry. Document titles render as text, never as HTML.
6. Update the catalog doc row and the completeness test's set.

**Verify:** `pnpm codegen:check` exits 0; `uv run pytest api/genui api/agents -q` passes with new tests: a corpus with documents yields a `SourceList` block; an empty corpus yields no `SourceList` and a recorded refusal; tamper tests (a document id that does not exist, a title or chunk count that differs from the store, 51 documents, a duplicate id) are each rejected by `validate_block` with the field path named; `pnpm --filter web test`, `pnpm -r typecheck` and `pnpm -r lint` pass, including a registry test that removing the `SourceList` entry is a type error (`tsc` fails on a deliberately broken copy, then revert). Run `schema-guardian`.

### Task B2: `GraphView`

**Files:** `packages/schema/src/payloads.ts`, `blocks.ts`, `api/agents/graph_agent.py` and its tests, `api/genui/{validate,builders,catalog}.py`, `api/agents/compose.py`, `web/components/genui/GraphView.tsx`, `web/components/genui/graphLayout.ts`, registry, tests, `catalog.md`.

1. **Read first.** Re-read `api/agents/graph_agent.py` and `api/stores/graph_store.py`: what the neighbourhood payload holds today (ids, edges with chunk ids, no labels and no quotes).
2. **Graph agent.** Extend the `neighborhood` payload with node labels and, per edge, the quote: `excerpt_containing(chunk text, [src label, dst label])`. An edge with no such quote is dropped from the payload (and counted in a `dropped` field so the refusal is explainable). Tests on the handmade graph in `test_graph_agent.py`.
3. **Schema first.** `GraphViewData { nodes: GraphNode[], edges: GraphEdge[], citations: Citation[] }` with `GraphNode { id, label }` and `GraphEdge { source, target, relation, citationId }`. Reuse `Citation`.
4. **Validator.** Caps (30 nodes, 40 edges); node ids unique; every edge endpoint is a node; every node touches at least one edge; every edge cites a citation of this block; every citation passes the existing chunk and quote rules; **each cited quote contains the labels of both endpoints** (`label_in_quote`); no orphan citation.
5. **Precondition:** at least 2 nodes and 1 edge after grounding. Builder, catalog entry, Composer admission with a recorded reason when refused (for example "fewer than one grounded edge").
6. **Web.** `graphLayout.ts`: a deterministic radial layout (seeded by node order, no randomness, pure function, unit-tested for determinism and for no overlapping nodes at the caps). `GraphView.tsx` draws an SVG node-link diagram and, beside it, a text list of every relation (`source, relation, target`, each with its source link). **It is interactive (D-29):** selecting a node (click, Enter or Space) highlights its incident edges and shows each one's relation, quote and source link in a details area; every node and edge is keyboard focusable in a stated order; a selected state survives a re-render. All four states. No new dependency.
7. Update `catalog.md` and the completeness set.

**Verify:** `pnpm codegen:check` exits 0; `uv run pytest api -q` and `pnpm --filter web test` pass; tests assert: a handmade graph with grounded edges yields a block that validates; an edge whose quote lacks one endpoint label is dropped and, if too few remain, the component is not offered; tamper tests (an edge to a missing node, an edge whose chunk does not exist, a quote that is not a verbatim span, a quote that lacks a label, an orphan node, 31 nodes) are each rejected with the field path; the layout function returns identical output for identical input; the SVG has an accessible name and the text list contains every relation; a component test selects a node by click and by keyboard and asserts the incident edges' quotes appear and the selection is exposed to assistive technology. Read-only spot check on the live graph: run the Graph agent's neighbourhood on three benchmark questions' entities and print how many edges survive the label rule (expected: most, given 70 percent of edges pass; record the numbers). `uv run pytest eval/tests/test_frozen_assets.py -q` passes. Run `schema-guardian`.

### Task B3: `ComparisonGrid` and the `align_documents` tool

**Files:** `api/agents/graph_agent.py`, `api/agents/test_graph_agent.py`, `packages/schema/src/payloads.ts`, `blocks.ts`, `api/genui/{validate,builders,catalog}.py`, `api/agents/compose.py`, `web/components/genui/ComparisonGrid.tsx`, registry, tests, `catalog.md`.

1. **Graph agent tool.** `align_documents(entities, ctx)`: for the question's resolved entities plus their neighbours that occur in two or more documents (`Node.doc_ids`), build the entity-by-document alignment: for each (entity, document) a stored chunk of that document in the node's `chunk_ids` whose normalised text contains the entity's label, with the quote from `excerpt_containing`. Caps: 6 documents, 8 entities. Order: resolved entities first, then by number of documents, then label. Deterministic; handmade two-document graph in tests. The agent stays a producer of payloads; nothing here builds a block.
2. **Schema first.** `ComparisonGridData { dimensions: GridDimension[], rows: GridRow[], citations: Citation[] }`; `GridDimension { id, label }`; `GridRow { docId, docTitle, cells: GridCell[] }`; `GridCell { dimensionId, citationId }`. A dimension with no evidence in a row simply has no cell: there is no text cell and no placeholder string.
3. **Validator.** Caps; dimension and row ids unique; each cell's dimension exists; each cell's citation exists and its chunk belongs to **the row's document**; its quote contains the dimension's label; every dimension has cells in at least 2 rows; every row has at least 1 cell; no orphan citation.
4. **Precondition:** at least 2 documents and 2 dimensions remain after grounding and alignment. Builder, catalog entry, Composer admission with recorded reasons.
5. **Web.** A table with documents as rows and entities as columns; a cell shows its cited quote (truncated, expandable) with the source link, an empty cell is rendered as an explicit "no evidence in this paper" mark (text, not colour alone). All four states.

**Verify:** `pnpm codegen:check`, `uv run pytest api -q`, `pnpm --filter web test`, `pnpm -r typecheck` all pass; tests assert: a two-document graph with two shared entities yields a valid grid; one shared entity, or one document, yields no grid and a recorded refusal; the grid never contains a cell the evidence does not support (a property test over random handmade graphs: every cell's citation is in the row's document and its quote contains the label); tamper tests (a cell citing another document's chunk, a quote without the label, a dimension supported in only one row, a row with no cells) are each rejected. Run `schema-guardian`.

### Task B4: `ConceptMap`

**Files:** `packages/schema/src/payloads.ts`, `blocks.ts`, `api/genui/{validate,builders,catalog}.py`, `api/agents/compose.py`, `web/components/genui/ConceptMap.tsx`, registry, tests, `catalog.md`.

1. **Schema first.** `ConceptMapData { steps: PathStep[], citations: Citation[] }`, `PathStep { from, relation, to, citationId }` with `from` and `to` being node labels. The path is the ordered list of steps.
2. **Validator.** Caps (6 steps); steps contiguous (`steps[i].to == steps[i+1].from`); no repeated node; each step cites a citation of this block whose quote contains both labels; no orphan citation.
3. **Precondition:** a path of at least 2 grounded hops between two entities, built from the Graph agent's `find_path` payload (each edge's quote from the same rule as B2); a 1-hop path is a `GraphView` case and does not admit a `ConceptMap`.
4. **Web.** A vertical chain: concept, relation, concept, with each step's quote and source link; an SVG is optional and not required (the list is the accessible form and may be the only form). All four states.

**Verify:** `pnpm codegen:check`, `uv run pytest api -q`, `pnpm --filter web test` pass; tests: a handmade graph with a 3-hop path yields a map; a 1-hop path does not; an ungrounded middle hop breaks the path and the component is refused with a recorded reason; tamper tests (non-contiguous steps, a repeated node, a quote without a label, a step citing a missing chunk) are rejected. Run `schema-guardian`.

### Task B5 (stretch): `InsightCard`

Only if A1 to B4, C1 to C3 and D1 are green and Azim agrees the phase has room; otherwise record it as deferred in the changelog and the catalog.

**Files:** as B4, plus the Graph agent.

1. Reuse the B4 path machinery. Precondition: a path of at least 2 hops whose two endpoint entities have chunks **only in different documents** (checked from `Node.doc_ids`: the two sets are disjoint). The block names the two documents and carries the path steps and citations; no sentence of free text beyond labels, relations and quotes.
2. Schema first, validator (all B4 rules plus: the endpoint documents are the ones named, and the endpoints' doc sets are disjoint as evidenced by the cited chunks' documents), builder, catalog, Composer, web, all four states.

**Verify:** the B4 verify list adapted: a path across two papers yields a card; a path inside one paper does not; tamper tests (a named document that no cited chunk belongs to). Run `schema-guardian`.

---

## Track C: level 2, the dashboard

### Task C1: `LayoutSpec` built to grow, the stream event, and removing placement from `BlockMeta`

**Files:** `packages/schema/src/layout.ts` (new), `blocks.ts`, `api.ts`, `index.ts`, `api/genui/generated.py` (generated), `api/genui/layout.py` (new), `api/genui/catalog.py`, `api/genui/validate.py`, `api/genui/builders.py`, `api/genui/test_validate.py`, `api/genui/test_layout.py` (new), `api/agents/compose.py`, `api/agents/graph.py`, `web/lib/store.ts` and `store.test.ts`, `web/app/Workspace.tsx`.

1. **Schema first, as one commit with every site that used the old fields.** `layout.ts`: `LayoutMode = "basic" | "research" | "exploration"`, `LayoutOrigin = "prebuilt" | "adaptive"`, `PanelId = "sources" | "chat" | "studio"`, `PanelSpec { id: PanelId, /** @int */ width }`, `Placement { blockId, panel: PanelId, /** @int */ order }`, `LayoutSpec { /** @int */ version, origin, mode, panels: PanelSpec[], placements: Placement[] }`, and `LayoutEvent { type: "layout", layout: LayoutSpec }` added to `StreamEvent`. Remove `panel` and `order` from `BlockMeta` (D-27). Update the sites found by search: `builders.py`, `validate.py` (the order rule), `test_validate.py`, `Workspace.tsx`, `store.test.ts`.
2. `pnpm codegen`, `pnpm codegen:check`.
3. **Validator for `LayoutSpec` (fail closed):** `version` is the supported one; panels have unique ids and integer widths in 0 to 100 summing to 100; the chat panel is present and at least 25; a panel of width 0 has no placements; placements reference distinct block ids, with unique orders within a panel and a known panel id; the spec references only blocks the turn actually produced (the Composer checks this before emitting).
4. **`layout.py`:** `compose_layout(admitted, intent) -> LayoutSpec` (the `adaptive` origin) and `prebuilt_layout() -> LayoutSpec` (the `prebuilt` origin: sources, chat and an empty studio panel, every block stacked in chat in arrival order). `compose_layout` contains **no component names**: it reads each admitted component's placement hint from the catalog (preferred panel, priority) and applies the generic rules (a panel with no placements has width 0 except chat; `exploration` when the intent is `relate` and a graph-hinted component was admitted). The width table lives in the module and in `catalog.md`.
5. **Composer and stream.** The Composer builds the adaptive layout last and validates it; if it fails validation it is **not** emitted (the client keeps the prebuilt layout) and the failure is recorded; the turn never fails because of layout. `run_turn` yields the `LayoutEvent` after the blocks and before `done`.
6. **The extensibility test (D-27, D-29):** in a test, register a toy component through the recipe in `catalog.md` (a catalog `Spec` with a placement hint, a trivial builder and a precondition over a test field of the evidence). Assert it is admitted, validated, placed in its preferred panel, and appears in the layout **with no edit to `layout.py`, `layout.ts` or the shell**; remove it and assert the layout is unchanged. A source scan test asserts `layout.py` mentions no catalog component name.
7. **Boundary test:** only `compose.py` imports `api.genui.layout`.

**Verify:** `pnpm codegen:check` exits 0; `uv run pytest -q` passes the whole suite; tests assert: every combination of the optional components yields a valid adaptive spec (widths sum to 100, chat at least 25, a hidden panel has no placements, every placement refers to a block in the composition); the prebuilt layout is valid; the toy-component test passes; a deliberately invalid spec is rejected by the validator and the turn still ends with its blocks and `done`. `pnpm --filter web test` and `pnpm -r typecheck` pass after the store changes. Run `schema-guardian`; record the `BlockMeta` removal in the changelog.

### Task C2: The workspace endpoint (the prebuilt version before any question)

**Files:** `packages/schema/src/api.ts`, `api/genui/generated.py` (generated), `api/routes/workspace.py` (new), `api/main.py`, `api/agents/compose.py` (a `compose_workspace` entry point), `api/test_api.py`, `web/lib/api.ts`, tests.

1. **Schema first.** `WorkspaceResponse { layout: LayoutSpec, blocks: UIBlock[] }`. `pnpm codegen`, `pnpm codegen:check`.
2. `GET /workspace` returns the prebuilt layout and a validated `SourceList` block built by the Composer (the only block builder, so a `compose_workspace` entry point lives in `compose.py`); with no documents it returns the prebuilt layout and an `empty` `SourceList`. No model call. The response is validated before it is sent and fails closed to the error envelope.
3. `fetchWorkspace` in `web/lib/api.ts` with a structural check as for `fetchTrace`.

**Verify:** `pnpm codegen:check` exits 0; `uv run pytest api -q` passes with tests: an empty corpus gives the prebuilt layout and an empty source list; after an ingest the source list names the document with the stored title and chunk count; a damaged stored document fails closed; the response contains no model call (ledger unchanged); `pnpm --filter web test` covers the client check (an unreadable body is an error state, never a half-rendered workspace).

### Task C3: The web shell: Basic first, Adaptive on top

**Files:** `web/components/shell/Shell.tsx` (new, ported), `web/components/shell/Panel.tsx`, `web/components/shell/LayoutSwitch.tsx`, `web/lib/store.ts`, `web/lib/stream.ts`, `web/app/Workspace.tsx`, `web/lib/layout.ts` (the fixed fallback and the shape check), tests, the provenance header in `Shell.tsx`.

1. **Read first.** Re-read v1's `web/components/shell/Shell.tsx` in full and v2's `Workspace.tsx`. Re-read the React 19 `inert` docs and the Tailwind v4 notes taken in A1 (v1 uses Tailwind v3 classes and a client-side `MODE_LAYOUT` map; neither is copied).
2. **Port the frame** with a provenance header (`Azimlearning/Arcana`, `web/components/shell/Shell.tsx`, commit `9a3d67f`): panels whose grow values come from the layout's `panels`, collapsed panels `aria-hidden` and `inert`. Drop `PanelResizer`, `ModeIndicator`, the notebook id and v1's tokens. The upload box and the question form stay.
3. **Store.** Keep blocks by id; add `layouts: { prebuilt, adaptive | null }`, `layoutChoice: "basic" | "adaptive"` and `pinned: boolean`. On load the client calls `GET /workspace` and applies its layout and block; if that fails it uses the fixed fallback in `web/lib/layout.ts` (a constant equal to the server's prebuilt layout, checked by a test against a committed JSON fixture that the server test also reads, so the two cannot drift). `startTurn` clears turn blocks and the adaptive layout, not the prebuilt one. A `LayoutEvent` passes the client shape check (known `version`, ids and widths sane) or is ignored. When a valid adaptive layout arrives and the user has not pinned Basic, `layoutChoice` becomes `adaptive`.
4. **The switch.** A header control `Basic | Adaptive`; choosing Basic sets `pinned`; choosing Adaptive clears it; Adaptive is disabled with a hint until one exists.
5. **Rendering rules (all tested):** each panel renders its placed blocks in `order` through the registry; a placement for a block the client does not have is ignored; a block with no placement renders in the chat panel in arrival order; with the prebuilt layout every turn block is stacked in the chat panel; an invalid or unknown-version adaptive layout is ignored; the loading block still appears first and is replaced in place.

**Verify:** `pnpm --filter web test` passes with new tests covering: the workspace opens on Basic with the source list before any question, layout before blocks, blocks before layout, a layout naming an absent block, an unplaced block, an invalid layout, an unknown version, the switch and pinning (auto-apply on the first answer, no auto-apply when pinned), a hidden panel is `inert` and `aria-hidden`, widths applied as flex-grow values, order within a panel; the fixture equality test; `pnpm -r typecheck`, `pnpm -r lint` and `pnpm --filter web build` exit 0; the existing `Workspace.test.tsx` tests still pass unchanged or with documented edits.

### Task C4: The composition record on the wire and in the trace panel

**Files:** `packages/schema/src/trace.ts`, `api/genui/generated.py` (generated), `api/agents/state.py`, `api/routes/chat.py`, `api/routes/trace.py`, `api/test_api.py`, `web/components/TracePanel.tsx`, `web/lib/api.ts`, tests.

1. **Schema first.** `ComponentDecision { component, offered: boolean, reasons: string[] }` (reasons are short codes such as `no_ready_document`, `fewer_than_two_shared_entities`, `quote_missing_label`, `block_failed_validation`; never an exception message or any text from a document) and `composition: ComponentDecision[]` on `TurnTrace`. `pnpm codegen`, `pnpm codegen:check`.
2. Record the Composer's decisions on the context, persist them with the trace (same table; the stored JSON is re-validated on the way out as today), serve them from `GET /turns/{id}/trace`.
3. **Web.** The trace panel lists, under the hops, "Offered" and "Not offered, and why", with the reason codes mapped to plain sentences (a typed map over the closed code list, exhaustive at compile time).

**Verify:** `pnpm codegen:check` exits 0; `uv run pytest api -q` passes with tests that a turn's trace includes a decision for every catalog component, a refused component carries a reason, and the trace contains no question text or document text (a body search as in the P1 trace test); `pnpm --filter web test` covers the panel's new section and an unknown reason code falling back to a generic sentence. Run `schema-guardian` on the whole P2 wire change (C1, C2 and C4 together, and a final look at B1 to B5).

---

## Track D: evidence

### Task D1: A real browser, end to end

**Files:** `refdocs/evidence/` (screenshots), execution doc.

1. Try the Playwright browser tool first (it timed out on connection on 2026-10-06 and worked earlier the same day); if it will not connect, install a local browser with `pnpm exec playwright install chromium` (check free disk first, 7.3 GB were free) and drive it from a small script kept outside the repo.
2. **Fakes, two real papers.** Start the API and web with a scratch data directory and capture first the **prebuilt Basic layout with the source list before any question**. Then ingest two real corpus papers (the RAG survey and HybridRAG are known to work) with the fake LLM and fake embedder, ask a cross-document comparison question and a relationship question. Capture: the Adaptive dashboard from a `LayoutSpec` (sources panel with `SourceList`, chat panel with the cited summary and the comparison grid, studio panel with the graph), the relationship layout, and the switch back to Basic (pinned).
3. **Fallback.** Remove the layout event (a scratch launcher that drops it, outside the repo) and capture the default layout with the same blocks.
4. **Real model.** Against `data/eval-live-live` with the live providers, run 3 to 5 questions (including the unanswerable control `q-single-01`: expect only an empty `CitedSummary` and an empty-ish composition, no invented component). Read the ledger before and after: the composition step has no entry; total about $0.05.
5. **The graph must work on real data.** For at least three real benchmark questions on `data/eval-live-live`, capture `GraphView` drawn from the real extracted neighbourhood, select a node by click and by keyboard, and capture the details area showing the incident edges' grounded quotes and source links. Inspect, and write down honestly, what the grid and graph look like on real data (whether generic entities dominate, whether the 30-node cap truncates, whether the radial layout is legible).

**Verify:** screenshots are saved under `refdocs/evidence/p2-*.png` and listed in the changelog; the browser run shows the prebuilt Basic layout with a source list before any question, the three panels populated from the adaptive layout, the layout change for the relationship question, the switch to Basic and back, the fallback layout when the event is removed, a real graph drawn and a node selection showing its edges' quotes on real data, and the trace panel's "Offered / Not offered" section; the ledger delta for the composition step is `$0.0000` and no new purpose appears in the ledger; the control question yields no relational component.

### Task D2: The admission-rate study (the first measurement of the bound)

**Files:** `eval/bound.py` (new), `eval/tests/test_bound.py` (new), `eval/results/<run>-bound.json`, `refdocs/evidence/<run>-bound.md`, `eval/README.md`.

**Protocol, fixed here before any run (constraint 9). It may change only by a declared amendment before the run, never after seeing results.**
- **Question set:** the frozen 20 in `eval/questions.yaml` (`q-single-01` included; its expected admission of relational components is none).
- **Stores:** `data/eval-live-live`, the one-shot ingestion; refuse to run unless the graph, vectors and chunk hashes equal `eval/frozen.py`-adjacent expected values supplied with `--expect-*-sha256` (same discipline as the benchmark runner).
- **Layers:** `flat` = the dense and BM25 retrievers fused, with no graph tools; `hybrid` = all three signals plus the Graph agent's tools (`neighborhood`, `find_path`, `align_documents`) run on the question exactly as in a real turn.
- **Evidence gathering:** retrieval and the Graph agent's deterministic tools only. **No Research agent, no Fact Checker, no model call.** Query embeddings are the only paid calls, cached across layers.
- **Admission:** the catalog's own `check` functions with the caps and thresholds already in `catalog.md` at the commit the run records. No threshold is tuned after the results are seen.
- **Outputs, per question and layer:** which components are admitted, and the reason code for each refusal; **per layer:** admission count and rate per component, and the set `X(layer)` realised on at least one question. Also report the entity-resolution hit rate per question (the paper's stated ceiling on the graph signal) beside admission.
- **Reported as measured**, including components that are rarely or never admitted. It is an admission rate over 20 questions on one ingestion. It is **not** a quality score, **not** a proof of the paper's claim (`X(flat) ⊂ X(hybrid)` holds by the definition of the preconditions here; the measurement is how often the extra components are available), and not a statement about questions unlike the 20.
- **Run conditions:** clean committed tree (the run records the commit and refuses a dirty tree, as the benchmark runner does), store hashes recorded.

1. Write `eval/bound.py` and its tests first (fixture graph and fixture documents; admission counts hand-computed for a tiny case; a refused component carries a reason; the study refuses mismatched store hashes and a dirty tree; flat never admits a graph component).
2. Run it once on the frozen stores. Commit the results JSON and a short human-readable record.

**Verify:** `uv run pytest eval/tests/test_bound.py -q` passes; `uv run python eval/bound.py --expect-graph-sha256 <hash> --expect-vectors-sha256 <hash> --expect-chunks-sha256 <hash>` exits 0 and writes the results JSON with 20 questions by 2 layers, the commit, a `dirty: false` flag, the store hashes and the per-component admission counts; `flat` admits only `CitedSummary` and `SourceList` on every question; the ledger delta is under $0.001 and contains only `embed` entries; the results and the record state the limits listed above.

### Task D3: Independent reviews

1. `schema-guardian` on the complete P2 wire change: schema first, codegen fresh, registry complete, every variant fail-closed, the preconditions documented and enforced, `BlockMeta` removal consistent on both sides, no path for anything but data to reach the client.
2. `test-runner` on the full suite: `uv run pytest` twice (order independence), `uv run ruff check api eval scripts`, `uv run pyright api eval`, `pnpm codegen:check`, `pnpm -r typecheck`, `pnpm -r lint`, `pnpm -r test`, `pnpm --filter web build`.
3. `cost-auditor`, read-only, to confirm the phase added no paid call and no unledgered path (the Composer, the layout and the Graph agent tool make no provider call).

**Verify:** the three reports are in the changelog; no blocking finding remains; every finding fixed has a test; the full suite is green on two consecutive runs.

### Task D4: Wrap-up

1. Update `refdocs/STATUS.md` (phase row, what works and what was measured, the verification ledger with the real commands and results), `refdocs/changelog/CHANGELOG.md`, the ADRs D-27 to D-30 with any amendment the build forced, the PRD §7 rows, `refdocs/guides/file_structure.md` (new modules and the removed fields), and both index tables (plan: Done; execution: Done).
2. Check the plan's definition of done item by item in the plan file, with a note for any item met partly; an unmet item is stated, never rounded up.
3. Run `/session-end`.

**Verify:** every box in the plan's definition of done is ticked with a note or explicitly marked partly met or unmet; the index rows match; `git status` is clean after the commit; no unresolved `ASSUMED:` item introduced by this phase is left unrecorded.

---

## Task order at a glance

`A1` (read, spike, catalog doc with the extension recipe, agent map; ADRs D-27 to D-30 already written) → `A2` (shared evidence helpers) → `A3` (catalog spine with placement hints, multi-block Composer) → `B1` SourceList → `B2` GraphView → `B3` ComparisonGrid and `align_documents` → `B4` ConceptMap → `B5` InsightCard (stretch) → `C1` extensible LayoutSpec, toy-component test, removing placement from `BlockMeta` → `C2` `GET /workspace` (the prebuilt version before any question) → `C3` web shell, Basic first with the Adaptive switch → `C4` composition record in the trace → `D1` real browser end to end → `D2` admission-rate study → `D3` reviews → `D4` wrap-up.
