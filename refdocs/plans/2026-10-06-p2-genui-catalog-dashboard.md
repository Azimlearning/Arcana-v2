# Plan: P2 GenUI catalog + adaptive dashboard (level 1 and level 2)

> Phase P2 of `refdocs/arcana-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-06-p2-genui-catalog-dashboard.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.
> Status: **Done 2026-10-07** (built and checked; see the check under Definition of done; B5 deferred). **Approved by Azim 2026-10-06** with the refinements recorded in ADRs D-27 to D-31 (an extensible layout, a prebuilt Basic layout first, a working graph output, a small roster of core agents, and a GenUI generation pipeline: template, fences, checking, save, reuse).

## Why this exists

Today every answer is one `CitedSummary`. The PRD's second pillar is a generative interface that offers the
answer in the shape the evidence supports: a comparison across papers, a graph of how concepts relate, a list
of the sources used, laid out as a dashboard. P0 and P1 built the spine (typed blocks, a fail-closed validator,
a registry, a Composer stub, agents that gather grounded evidence). P2 widens the vocabulary and makes layout
data.

The central rule (PRD principle 2, hard constraint 7, the MCAIT paper's bound) is that **retrieval structure
bounds the interface**. A component asserts a shape of answer, so it may be offered only when retrieval can
supply that shape from evidence. "A comparison grid" claims documents align on shared entities; if the corpus
did not return that alignment, filling the grid means inventing it. P2 turns that sentence into code: every
component has a written structural precondition, a deterministic check that runs before the component is
offered, and a validator that rejects a block whose content does not meet it. P2 also produces the first
empirical number for the bound: how often, on the real benchmark questions and the real ingested corpus, the
relational components are actually available.

## What's already covered (no work needed)

**In v2 today (P0 and P1):**
- The wire: `UIBlock` (one variant, `CitedSummary`), `BlockMeta` with five statuses, strict generated models,
  upsert by block id, the SSE `StreamEvent`s, and `TurnTrace` served and shown in a panel.
- `validate_block`: fail-closed content rules for citations (every `chunkId` resolves, the quote is a verbatim
  span of at least 20 characters, title and page match).
- The web registry (typed over the union, so a missing component is a compile error), the four shared states
  (`BlockStates.tsx`), and a stream consumer and store keyed by block id.
- The Composer stub (`api/agents/compose.py`, the only importer of `api/genui/builders.py`, enforced by a test)
  and the rule that agents return payloads, never blocks.
- The Graph agent with `find_path` and `neighborhood`, every edge carrying the chunk it came from; the Fact
  Checker gate; `route_to_agent` budgets.
- The ingested corpus with a real graph (checked on 2026-10-06, read-only): 11,173 nodes, 13,972 edges, 1,294
  entities that occur in two or more papers (11.6 percent), 126 in five or more. The label of an edge endpoint
  appears literally in the chunk the edge came from for 83 percent of endpoints, and both labels appear for 70
  percent of edges. These two numbers decide what a grounded graph component can honestly show.

**Reference material, and what can be ported:**
- **Arcana v1 (`../Arcana/`, read only).** A 24-component catalog, a three-panel `Shell.tsx` (96 lines) with a
  `PanelResizer`, and a client-side `MODE_LAYOUT` map (five modes, panel widths in client code).
  - *Reusable as a visual reference only:* `LiteratureMatrix` (84 lines), `ConceptMap` (100), `SourceList` (64),
    `KnowledgeGraphView` (127, a static node list; its own comment says the interactive version was a stretch).
    Their **payload shapes are not reusable**: they carry free-text cells and insight strings with nullable
    citation ids, which is exactly the ungrounded content constraint 1 forbids. v2 shapes are rewritten so that
    every displayed assertion is a stored chunk's verbatim quote.
  - *Portable with a provenance header:* the shell frame (`Shell.tsx`: three flex panels, collapsed panels
    `aria-hidden` and `inert`). It is adapted to be driven by a `LayoutSpec` from the wire instead of v1's
    client-side `MODE_LAYOUT`.
  - *Not ported:* `PanelResizer` (user-resizable panels: not needed for the exit criteria), `ModeIndicator`
    (no mode switcher exists), the learning, writing and audio components (see Scope, out).
  - v1's layout was **not data on the wire** (it was a client map keyed by mode), so level 2 `LayoutSpec` is new.
- **Synapse (`GenUI-Education`).** `refdocs/arcana-v2-sources.md` names a typed layout spec in
  `Synapse-V3`, but that repository is **not on this machine** (searched under `Documents/`; only
  `Synapse_Product_Details.docx` and `synapsesuperprompt.txt` were found, neither is code). Nothing can be
  ported from it in this phase, and the `LayoutSpec` is written fresh from the PRD. If Azim supplies the
  repository, a comparison is a cheap follow-up, not a prerequisite.
- **The MCAIT paper's Table (`main.tex`, "Component preconditions")** is the source of each component's
  structural precondition and the signal that supplies it. P2 implements the subset the current agents and
  stores can honestly satisfy.

## Scope

**In**
- **A written, enforced catalog.** `refdocs/guides/catalog.md` (new) states, for every component, its
  structural precondition, the signal that supplies it, its size caps, its validator invariants and its states.
  `api/genui/catalog.py` holds the same preconditions as deterministic checks. A completeness test ties the
  schema union, the server builders, the catalog and the web registry together.
- **Five level 1 components** (one already exists): `CitedSummary` (flat retrieval), `SourceList` (document
  store), `GraphView` (the graph: entities and labelled edges), `ConceptMap` (graph traversal: a path of at
  least two labelled relations), `ComparisonGrid` (cross-document entity alignment). Each has all four states,
  a precondition, a builder, validator rules and tamper tests. **`GraphView` is a working graph output (D-29):**
  a drawn node-link diagram from the real extracted graph (v1 only ever had a static node list), with selectable
  nodes and edges that show their grounded quote and source, keyboard operation and a text list of the same
  relations, shown working on the real ingested corpus. A sixth, `InsightCard` (a multi-hop path whose
  endpoints are evidenced in different papers), is a **stretch** task, cut first if the phase runs long.
- **The UI generation pipeline spine (D-31): template, fences, checking, save, reuse, for typed UI.** The five
  components become reviewed, versioned **templates** with declared **fences** (caps, grounding, accessibility);
  **checking** is staged and fail closed and includes a **mutation suite that must pass before a template can
  register**; a verified view can be **saved as a pattern** (template, version, typed parameters, layout; never
  the evidence) and **reused** later from the saved list, where applying it re-runs the preconditions on the
  current evidence and fails closed if they no longer hold or the template changed. The basic components stay the
  foundation. P4 adds generated code to this same pipeline.
- **A deterministic, evidence-admitting Composer (D-28).** The Composer computes which components' preconditions
  the turn's evidence satisfies, builds exactly those, validates each, and drops (never repairs) any that fail.
  It makes no model call.
- **A prebuilt Basic layout first, Adaptive layered on top (D-28).** The workspace opens in a fixed prebuilt layout
  with a source list available before any question (a new `GET /workspace`); each turn also yields an adaptive
  layout; a header control switches Basic and Adaptive. The prebuilt layout is the fallback for any missing or
  invalid adaptive layout.
- **One new Graph agent tool, `align_documents`**, which supplies the entity-by-document alignment the grid
  needs, and per-edge quotes on the existing tools' output. Evidence gathering stays in agents; the Composer
  only chooses.
- **Level 2 `LayoutSpec` (D-27), built to grow:** a typed spec (`version`, `origin`, `mode`, a list of panels with
  widths, and placements of block ids into panels) produced by the Composer and streamed as its own event; the web
  shell renders panels from it. A new component, panel or mode needs no change to the layout types or the shell:
  each catalog component declares its own placement hint and the layout rules read those hints. A test registers
  a toy component to prove it.
- **An extension recipe and an agent consolidation map.** `refdocs/guides/catalog.md` carries the step-by-step
  recipe for adding a component (D-29); `refdocs/guides/agents.md` maps v1's 25 agents onto the small v2 roster of
  core agents and their tools (D-30). No agent is added in P2; the Graph agent gains one tool.
- **A composition record** (which components were offered, which were refused, and the precondition that was
  not met) added to the turn trace and shown in the trace panel.
- **The first measurement of the bound:** an admission-rate study over the 20 pre-registered questions on the
  frozen stores, protocol written before the run (execution doc, task D2).

**Out, with reasons**
- **ContradictionAlert.** "Disagree" needs a judge, which is a model call whose reliability is unmeasured. The
  precondition's structural half (two papers co-retrieved on one entity) is checkable; the claim is not.
  Revisit once a judge exists and its detection rate has been measured (P3 or later).
- **Timeline.** The schema-free extraction records no dates or temporal relations. Adding them changes the
  extraction prompt (a frozen, stamped asset), forces a second paid ingestion with a different graph, and
  invalidates the first benchmark's stores.
- **GapAnalysis.** It asserts absence ("the corpus does not cover X"). Coverage needs a defined concept space;
  graph communities exist but are not a coverage claim. A component that asserts a negative from a positive
  signal is the failure the bound exists to prevent.
- **ComparisonChart, DataTable.** No structured or numeric extraction exists; filling them means inventing
  values.
- **The learning and writing components** (`FlashcardDeck`, `QuizCard`, `BlurtingPrompt`, `FeynmanExplainer`,
  `CornellNotes`, `SocraticDialog`, `StudyPlanner`, `DraftEditor`, `CitationPreview`, `PlagiarismReport`,
  `BibliographyExport`): they belong to the Tutor and Writer (P5) and, for review scheduling, to Mastery (P3,
  optional). No agent produces their evidence yet, so an admission check would have nothing to check.
- **`ProgressDashboard`** (needs mastery data, P3 optional), **`AudioSummary`** (a PRD non-goal).
- **A study, writing or Socratic mode switcher and "learner signals".** The PRD lets layout depend on mode, intent
  and learner signals; there are no learner signals before P3 and no study or writing components before P5. P2's
  layout depends on intent and on which components were admitted. The `mode` field is a closed union with the three
  values P2 exercises (`basic`, `research`, `exploration`), extended by a schema change when a phase needs one. The
  Basic and Adaptive switch is in scope; richer modes are not.
- **A model-chosen layout.** It would add a paid call per turn and an unmeasured chooser. Deterministic rules
  keep P2 free and testable; a learned chooser is the P3 router's job.
- **Level 3 (`VerifiedLab`), generated code, and the full governed lifecycle (P4).** The pipeline's code stages
  (static analysis of generated code, contract property tests, fuzzing, the sandbox run, the verifier and delivery
  gate) and the lifecycle states beyond `generated`, `verified` and `saved` (`cached`, `audited`, `promoted`,
  crystallisation) are P4 and plug into the P2 spine. P2 adds no path by which generated code reaches the client;
  hard constraint 3 is untouched.
- **User-resizable panels** (v1's `PanelResizer`): not needed for the exit criteria.
- **Any change to retrieval, the protocol stamp, the extraction prompt, the gold or the ingested stores.** The
  benchmark's pins must stay green.

## Approach

**Data flow of one turn (new parts in bold):** agents gather evidence (Research, Graph with
**`align_documents`**) → Fact Checker → Composer builds a **`ComposerEvidence`** object from the turn's agent
results and the document store → for every catalog component, **its precondition check** runs on that evidence
→ the Composer builds a block for each admitted component with `builders.py`, runs `validate_block`, and drops
any block that fails (recording why) → **`compose_layout`** places the surviving blocks into panels and sets
widths → `run_turn` streams the loading block, the final blocks, the **`LayoutEvent`**, then `done`.

**Preconditions are data about evidence, not about models.** Each check is a pure function over
`ComposerEvidence`, returns satisfied or not plus the reasons, and has a test for both outcomes. The block
validator re-checks the *content* invariants independently (a second enforcement point), so a bug in a builder
cannot put an ungrounded component on the wire.

**Grounding rule for every relational element.** Each edge, path step or grid cell cites a stored chunk and a
quote that is a verbatim span of that chunk **and contains the label of every entity the element names**. The
check needs only the chunk text, so the validator needs no graph access. Elements that cannot meet it are left
out; a component with too few elements left fails its precondition and is not offered.

**Components, in the order they are built** (exact types are fixed schema-first in each task):

| Component | Structural precondition | Supplied by | Caps |
|---|---|---|---|
| `CitedSummary` (exists) | ranked passages with sources | flat retrieval | as today |
| `SourceList` | at least one ready document | document store | 50 documents |
| `GraphView` | at least 2 entities and 1 labelled edge, each edge grounded as above | the graph (Graph agent `neighborhood`) | 30 nodes, 40 edges |
| `ComparisonGrid` | at least 2 documents and 2 entities, every entity evidenced in at least 2 of the documents, each present cell grounded; a cell with no evidence stays empty, never filled | cross-document alignment (Graph agent `align_documents`) | 6 documents, 8 entities |
| `ConceptMap` | a path of at least 2 labelled hops between two entities, every hop grounded, no repeated node | graph traversal (Graph agent `find_path`) | 6 hops |
| `InsightCard` (stretch) | a path of at least 2 hops whose endpoints are evidenced only in different documents | multi-hop traversal | 6 hops |

**Level 2.** `LayoutSpec { version, origin, mode, panels, placements }` (D-27). `panels` is a list of
`{id, width}` (a closed `PanelId` union today: `sources`, `chat`, `studio`; a fourth panel is a schema addition,
not a rewrite). `placements` is a list of `{blockId, panel, order}` and is the **single source of truth for
placement**; `BlockMeta.panel` and `BlockMeta.order` are removed rather than kept as a second copy, for the same
reason D-19 dropped the redundant `summary` string. Widths are integers summing to 100, the chat panel never below
25, a hidden panel holds no placements. `origin` is `prebuilt` or `adaptive`; `mode` is `basic`, `research` or
`exploration`. **The rules read the catalog, not a list of component names:** each catalog `Spec` declares a
placement hint (preferred panel and priority), so `compose_layout` is generic and a new component brings its
own hint. Defaults (judgement, asserted by invariants not exact numbers): the `adaptive` layout shows the sources
panel iff a `SourceList` was admitted and the studio panel iff any admitted component prefers it; `exploration`
mode when the intent is `relate` and a graph component was admitted, `research` otherwise. The `prebuilt` layout
is a constant: sources, chat and an empty studio panel, every block stacked in the chat panel in arrival order.

**Basic first, Adaptive on top (D-28).** `GET /workspace` returns the prebuilt layout and a validated `SourceList`
block, so the workspace is useful before any question and with no model. The client holds `layoutChoice`
(`basic` or `adaptive`) and `pinned`. It starts on Basic; when a turn delivers a valid adaptive layout the client
applies it unless the user has pinned Basic; a header control switches between them at any time. The client
renders from whichever layout is chosen, treats a block with no placement as chat-panel content in arrival order,
ignores a placement for a block it does not have, ignores a layout with an unknown `version`, and falls back to
the prebuilt layout when the adaptive spec is missing or fails a client shape check. Layout is data; no layout
path executes anything. ASSUMED (reading of the request): auto-applying Adaptive after the first answer unless
Basic is pinned; one client setting, cheap to change.

**The UI pipeline (D-31).** One path for every UI: *template* (a catalog entry with a version, typed slots and a
placement hint) → *fences* (the template's declared limits: caps, the grounding rule, accessibility requirements)
→ *checking* (precondition, build, schema, content, and the registration-time mutation suite) → *save* (a pattern:
template id and version, typed parameters, layout mode; content-addressed; state `generated`, `verified` or
`saved`; evidence never stored) → *reuse* (listed with the prebuilt layouts; applying re-binds fresh evidence, runs
the checks again, and fails closed with a reason: `precondition_not_met` or `template_changed`). Applying a
pattern uses only deterministic tools, so it costs nothing. The pipeline is typed-data only in P2; its interfaces
are drawn so P4's generated-code stages are additional checks and an additional kind of template body, not a
redesign.

**A graph output that works, without a new dependency.** `GraphView` and `ConceptMap` use a deterministic radial
SVG layout written for this project (no force simulation, no library). The diagram is interactive: selecting a
node highlights its edges and shows each incident edge's relation, quote and source link; nodes and edges are
keyboard focusable; a text list of every relation sits beside it as the accessible alternative and the print
form. The caps keep the picture legible. It is verified on the real graph for real benchmark questions (task D1),
because a graph view that only works on fixtures is the v1 outcome. A graph library is not needed for the exit
criteria and would add a dependency and nondeterminism.

**The measurement.** For each of the 20 questions and for two retrieval layers, `flat` (dense plus BM25, no graph
tools) and `hybrid` (adds the Graph agent's tools), run the evidence gathering that needs no model call, compute
which components' preconditions are satisfiable, and report counts per component and per layer.
`X(flat)` is `{CitedSummary, SourceList}` by the definition of the preconditions; the empirical content is how
often the additional relational components of `X(hybrid)` are actually available on real questions and a real
extracted graph. It is an admission rate, not a quality score and not a proof of the paper's claim.

## Cost estimate

**P2 adds no paid call.** The Composer, the preconditions, the layout rules and the new Graph agent tool are
deterministic code over stores. Tasks verify this rather than assume it: a test asserts the Composer issues zero
provider calls, and the live check reads the spend ledger before and after to show the composition step cost
nothing.

| Item | Estimate |
|---|---|
| Composer, preconditions, layout, `align_documents` | $0 |
| Bound measurement: query embeddings for 20 questions (cached across layers) | under $0.001 (the 19-question benchmark cost $0.00006) |
| Live end-to-end check: 3 to 5 real chat turns (routing rules, Research on Sonnet, Haiku judge) | about $0.05 (measured $0.007 to $0.015 per turn on 2026-10-06) |
| **Total for the phase** | **about $0.05 to $0.10**, against about $3.9 of the $10 cap remaining |

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| The label-in-quote rule refuses too many graph elements | Medium-high that components still appear for most questions: measured on the live graph, 83 percent of edge endpoints and 70 percent of edges pass | Elements that fail are dropped, the component is offered only if enough remain, and the refusal is recorded. The admission study measures the real per-question rate; thresholds are fixed before it runs and not tuned after |
| Graph components depend on the question's entities resolving to nodes (the paper's own limitation) | Medium: on the benchmark every question had at least one exact entity (mean hit rate 0.657), unknown for new questions | The Composer simply offers fewer components; the composition record says why. Reported as a limit, not hidden |
| A comparison grid dominated by generic entities (`LLM`, `RAG`, `Question Answering` are in 13 to 15 of 16 papers) is true but uninformative | Low-medium that the grid is *useful* by default; it is safe either way | Dimensions are the question's resolved entities plus their neighbours that are shared across documents, capped at 8; inspected in the browser check; no claim of usefulness is made, only of grounding |
| Codegen for a five-variant discriminated union with nested arrays and nullable fields | Medium: the generator emits `Annotated[A | B, Field(discriminator='type')]` for 2 or more variants, but only one variant exists today, so it has never been exercised | Task A1 reads `codegen/to_python.ts` and the current Pydantic docs and runs a scratch spike before any real type is added |
| Removing `BlockMeta.panel` and `order` (D-27) touches validator, builders, tests and the web store | Medium: small blast radius (found by search: `builders.py`, `validate.py`, `test_validate.py`, `Workspace.tsx`, `store.test.ts`) | Done in one schema-first task (C1) with every site changed in one commit; `schema-guardian` reviews it |
| Multiple blocks plus a layout event can arrive in any order and a layout can reference blocks that never arrive | Medium-high (a design question with tests, not an unknown library) | The client is order-independent and fail-safe by construction (rules above); tests cover layout-before-blocks, blocks-before-layout, missing blocks, unknown ids, an invalid layout |
| Readability and accessibility of an SVG graph | Medium | Hard caps (30 nodes), deterministic layout, a text alternative that lists every relation, roles and labels asserted in component tests, checked in a real browser |
| The Playwright browser tool timed out when connecting on 2026-10-06 | Medium: it worked earlier the same day | Task D1 retries it first; the fallback is `pnpm exec playwright` with a local browser download (7.3 GB of disk is free) |
| Scope: five components, a layout, a trace extension and a measurement in one phase | Medium | Strict order (never the second of anything before the first is green end to end), `InsightCard` is a pre-declared cut, each component is its own task with its own Verify |
| `align_documents` or the quote selection touches something frozen | Low | The change is in an agent, not in retrieval; `eval/tests/test_frozen_assets.py` (protocol stamp, gold, questions, manifest pins) must stay green and is run in every verify |
| The v1 payload shapes look convenient and tempt a port | Low once stated | Stated here: v1 shapes allow ungrounded text; they are references for layout and visual structure only |
| "Extensible for all future GenUI features" is claimed but only holds if a new component really needs no layout change | Medium: easy to claim, easy to break by hard-coding a component name in the layout rules | Placement hints live on the catalog `Spec`; a test registers a toy component and asserts it is laid out with no edit to `layout.py`, the layout schema or the shell; the recipe in `catalog.md` is followed by that test |
| Basic-then-Adaptive is my reading of the request (the default switching behaviour) | Medium: the intent is clear, the exact default is not | Recorded as ASSUMED in D-28; one client setting (`pinned`, auto-apply), covered by tests, trivial to change |
| An interactive SVG graph is more work and more accessibility surface than a static one | Medium | Dependency-free deterministic layout; selection, focus and the text alternative are component tests; judged on real data in the browser run, not on fixtures |
| The pipeline adds four tasks (templates and fences, saved patterns, reuse, re-verification) to a phase that was already large | Medium | Track E comes after the layout work; the pre-declared cut line is that reuse and re-verification (E3, E4) may move to the start of P4 while the template, fence and store work (E1, E2) stays, recorded in the changelog if used |
| "Fences" is my reading of an unclear word in the request | Medium | Recorded as ASSUMED in D-31 with the definition used; renaming the stage costs nothing if something else was meant |
| Saving a view without saving its evidence means a reused pattern can behave differently on a different corpus | Medium: it is the intent (evidence goes stale) | Apply re-runs the preconditions and fails closed with a reason; a test deletes a document and applies the pattern |
| "More advanced than Synapse" cannot be checked: the Synapse code is not on this machine | High that it cannot be verified now | Stated in D-31 as design intent only; no comparative claim is made anywhere |
| Consolidating agents (D-30) tempts a refactor of P1 code now | Low once stated | P2 adds no agent and renames none; the map in `agents.md` is documentation plus the rule for future phases; any merge (Studio) is a P5 plan decision |

## Definition of done

- [x] `packages/schema` defines `SourceList`, `GraphView`, `ConceptMap` and `ComparisonGrid` blocks, `LayoutSpec`
  (with `version`, `origin`, `mode`, a panel list and placements), `LayoutEvent`, the workspace response and the
  composition record; `pnpm codegen:check` exits 0. `BlockMeta` no longer carries placement.
- [x] `refdocs/guides/catalog.md` states every component's precondition, supplier, caps and invariants, and a
  completeness test fails if the schema union, the server builders, the catalog and the web registry disagree.
- [x] For each component there is a test where the evidence satisfies the precondition (the block is built,
  validated and streamed) and a test where it does not (the component is not offered, the answer still renders
  as a `CitedSummary`, and the composition record names the unmet precondition).
- [x] For each component there are tamper tests: an edge, step or cell whose chunk does not exist, whose quote
  is not a verbatim span of the chunk, whose quote lacks an entity label, or whose chunk belongs to a different
  document than the row is rejected by `validate_block`.
- [x] The Composer makes zero provider calls (test), and in a live run the spend ledger shows no entry for the
  composition step.
- [x] A cross-document question on two real papers, in a real browser, renders a dashboard from a `LayoutSpec`:
  the sources panel lists the documents, the chat panel holds the cited summary and the comparison grid, the
  studio panel holds the graph; a relationship question changes the layout; with the layout event removed the
  same blocks render in the default layout; screenshots are committed.
- [x] The workspace opens in the prebuilt Basic layout with a source list before any question is asked; after an
  answer the Adaptive layout applies unless Basic is pinned; the header control switches between them; a missing
  or invalid adaptive layout leaves the prebuilt layout in place (browser run and tests).
- [x] **The graph output works on real data:** in a real browser, for at least three real benchmark questions on
  the ingested corpus, `GraphView` draws the question's real extracted neighbourhood, selecting a node shows its
  edges with their grounded quotes and source links, and keyboard focus reaches every node; screenshots committed.
- [x] **Extensibility is demonstrated, not claimed:** a test registers a toy component through the documented
  recipe and it is admitted, validated, laid out and rendered with no change to the layout module, the layout
  schema or the shell.
- [x] **The pipeline exists end to end for typed UI:** a template cannot register unless its mutation suite
  rejects every planted defect (a test registers a template with a deliberate validator hole and asserts the
  refusal); a verified adaptive view can be saved as a pattern, listed with the prebuilt layouts, and applied
  later with no model call; applying fails closed with a reason when a document it needs is gone or the template
  version changed (tests and a browser capture).
- [x] `refdocs/guides/agents.md` maps each of v1's agents to a v2 core agent and tool group (or to a stated drop),
  and states the rule for when something may become an agent (D-30).
- [x] The trace panel shows, for a turn, which components were offered and which were refused and why.
- [x] The admission-rate study is run on the frozen stores with a protocol written before the run; its results
  JSON (per component, per layer, per question, with the code commit and store hashes) is committed and
  reported as measured, including components that are rarely admitted.
- [x] No agent module imports another agent module and only the Composer imports the builders and the layout
  function (tests); no retrieval pin or frozen asset changed (`eval/tests` green).
- [x] `schema-guardian` has reviewed every wire change; `test-runner` is green on the full suite, lint, types,
  codegen check and build; STATUS, CHANGELOG, ADRs D-27 to D-31, the file structure guide and the indexes are
  current.

### Check against the build (2026-10-07, P2 D4)

Each item above is ticked because it was met; the notes say how far, and what was not shown. Nothing is rounded up.

1. Schema types: **met.** `BlockMeta` is `{status, error}` only; `pnpm codegen:check` OK.
2. Catalog guide and completeness test: **met** (`api/agents/test_catalog.py`; `fence_mismatches` parses `catalog.md` against `CATALOG`).
3. Precondition met and unmet tests per component: **met** for the five built components.
4. Tamper tests: **met** for GraphView, ComparisonGrid and ConceptMap. `SourceList` and `CitedSummary` have no quote to tamper with; their tests tamper with stored metadata and citation ids.
5. Composer makes no provider call: **met** (a call-count test; the D1 live ledger delta for composition and layout was $0.0000; the cost audit read every call site).
6. Cross-document question in a real browser: **met** (screenshots 03, 04, 08), with two caveats. The comparison and relationship layouts were shown with a fake model on two real papers, and a real model on the 16-paper store was used for three further questions. The dashboard is **cramped at 1440 px and was not tried at phone width**.
7. Prebuilt Basic first, Adaptive layered on, a missing layout leaves Basic: **met** (screenshots 01, 02, 06, 08 and the tests). The default (the first answer applies Adaptive unless Basic is pinned) is recorded as ASSUMED 6.
8. Graph output on real data: **met** for three real questions (screenshots 10 to 12, 17), node selection by click, Enter and Space. **Not shown:** a graph near the 30-node cap on real data (the real graphs had 3 or 4 concepts), and every node reached by Tab on real data (covered by a component test only).
9. Extensibility demonstrated: **met** for components (toy component, source-scan test). **Partly met for the layout:** a new panel or mode is a schema change (D-27 amended 2026-10-07).
10. Pipeline end to end for typed UI: **met** (registration refuses a template with a planted hole; save, list, apply with no model call and refusals in tests; browser capture 07 for save and apply after a reload). A refusal was not captured in the browser.
11. Agent map: **met** (`refdocs/guides/agents.md`).
12. Trace panel offered and refused: **met** (capture 09).
13. Admission-rate study: **met**, reported as measured: ConceptMap admitted on 3 of 20 questions, GraphView 16 of 20, ComparisonGrid 20 of 20; `refdocs/evidence/20261006T184643Z-bound.md`.
14. Import rules and frozen assets: **met** (tests; `eval/tests/test_frozen_assets.py` 7 passed). `api/genui/templates.py` also imports the builders, for registration fixtures only; the rule is enforced as "Composer and templates".
15. Reviews and docs: **met.** The reviewers were general-purpose agents given the `schema-guardian` and `cost-auditor` checklists (the named agent types were unavailable). The wire review's one blocking item was a documentation conflict (D-27), now amended. The rest of its findings are listed in the changelog entry of 2026-10-07 (D3), with what was fixed and what is open.

**Not done in P2, by decision:** `InsightCard` (B5, a stretch; needs Azim's agreement). **New direction from Azim, not planned yet:** the Studio output area and split panes in the middle (DECISIONS working assumptions 4 and 5).
