# The GenUI catalog: components, preconditions, and how to add one

> Written in P2 task A1, before any component's schema type exists (hard constraint 7: a component joins the
> catalog on evidence, with a written structural precondition that retrieval can satisfy). Plan:
> `refdocs/plans/2026-10-06-p2-genui-catalog-dashboard.md`. Decisions: D-27 (layout), D-28 (Composer), D-29 (scope),
> D-31 (pipeline). Status of each component is stated in its section; five are built (`CitedSummary`, `SourceList`, `GraphView`, `ComparisonGrid`, `ConceptMap`) and `InsightCard` is deferred.

## The bound

A typed component is a claim about the *shape* of an answer. A comparison grid claims documents align on shared
entities; a graph view claims entities stand in labelled relations; a concept map claims a chain of them. The MCAIT
paper's bound: for a component `c` with structural precondition `P(c)`, and the evidence `E(R, q)` a retrieval layer
`R` returns for a query `q`, the catalog a layer can honestly offer is `X(R) = { c | P(c) is satisfiable from E(R, q) }`.
If retrieval cannot supply the structure, filling the component means inventing it.

In v2 the check is code, not prose: each component has a deterministic `check(evidence)` in `api/genui/catalog.py`
(task A3 onward) and the Composer offers a component only when its check passes. The validator re-checks the
block's content independently, so a builder bug cannot put an ungrounded component on the wire.

**Admission is necessary, not sufficient.** A satisfied precondition says the structure exists in the evidence. It does
not say the component is a good answer to the question.

## Conventions every component follows

**Grounding.** Every assertion a component displays is a stored chunk's verbatim words:

- a citation names a stored `chunkId` under the document it claims, its `docTitle` and `page` match the store, and its
  `quote` is a verbatim span of that chunk (whitespace normalised) of at least 20 characters (or the whole chunk if
  shorter);
- for a relational element (an edge, a path step, a grid cell) the quote **also contains the label of every entity the
  element names**. This needs only the chunk text, so the validator needs no graph access;
- no free text: a component carries labels, relation names, titles and quotes. There is no summary string and no
  placeholder text for a cell without evidence. A cell with no evidence is absent.

**Fail closed.** A block that fails validation is dropped, never repaired, and the refusal is recorded with a reason
code. The turn still renders its `CitedSummary`.

**Four states.** `loading` (a skeleton), `empty` (nothing found, shown as "nothing found", not as a failure), `error`
(the block's own error envelope), and the ready content. `partial` is reserved and not emitted in P2. Components branch
on `meta.status`, never on whether arrays are empty.

**Text, never markup.** Document titles, labels, relations and quotes render as text. Nothing a document says is ever
interpreted as HTML or as an instruction.

**Accessibility.** Each component has a text form that carries all its information (a list or a table) and roles and
labels asserted in its component test; colour is never the only carrier of meaning.

**Schema conventions** (found by a spike on 2026-10-06 against `packages/schema/codegen/to_python.ts`; task A1b makes
codegen enforce them):

- `/** @int */` must be on **its own line** directly above the property. In a one-line interface it used to be silently
  ignored and the field became `float` (a count would accept 1.5); codegen now refuses it.
- Never use `interface X extends Y`: codegen drops the base's fields from `X`, so a required field would stop being
  required (it fails open).
- No generic interfaces: codegen emits a module that cannot be imported.
- A union of blocks is `export type UIBlock = A | B | ...` of interfaces that each have a string-literal `type`; a
  Pydantic discriminated union needs at least two variants, so a single-variant alias stays a plain alias until the
  second variant arrives (task B1).
- Strings only for saved-pattern parameters (D-31); no free-form JSON on the wire.

## CitedSummary

Status: **built** (P0).

- **Precondition:** ranked passages with sources; the answer's segments each cite at least one citation.
- **Supplied by:** flat retrieval (dense plus BM25), checked by the Fact Checker.
- **Payload:** `segments: {text, citationIds}[]`, `citations: Citation[]`.
- **Caps:** 40 segments and 40 citations (the Fences line below; `api/genui/validate.py` enforces them).
- **Fences:** caps `segments=40 citations=40`; grounding `citation_verbatim_quote`; a11y `region:Sources`. Slots: none. Template version 1; reusable without Research: no.
- **Validator invariants:** as in `api/genui/validate.py` (citations unique and resolvable, no orphan citation, a ready
  block has a segment, every segment cites).
- **States:** all four; `empty` for a declined or unanswerable question (the `q-single-01` control renders here).
- **Placement hint:** chat panel, priority 10 (first).
- **Admissible with flat retrieval:** yes.

## SourceList

Status: **built** (P2 B1).

- **Precondition:** at least one document with status `ready` in the document store.
- **Supplied by:** the document store (metadata only).
- **Payload:** `documents: {docId, title, chunkCount}[]`.
- **Caps:** 50 documents (the `documents` cap in this component's fences, read through `cap()` by the validator); title as stored.
- **Fences:** caps `documents=50`; grounding `stored_document_metadata`; a11y `region:Documents`. Slots: none. Template version 1; reusable without Research: yes.
- **Validator invariants:** unique ids; every `docId` exists and is `ready`; `title` and `chunkCount` equal the stored
  values; placeholder statuses carry no documents. It asserts existence only, so it carries no citations.
- **States:** `loading`; `error`; ready list. `empty` is implemented by the component. The turn Composer never sends it (with no ready document the component is refused, `no_ready_document`), but `GET /workspace` sends an empty list so the sources panel can say there is nothing yet.
- **Placement hint:** sources panel, priority 10.
- **Admissible with flat retrieval:** yes (it needs no retrieval at all, which is why it can be shown before any question).

## GraphView

Status: **built** (P2 B2). **Works on real data and is interactive (D-29).**

- **Precondition:** at least 2 entities and 1 labelled edge after grounding; every edge is backed by a stored chunk whose
  cited quote contains both endpoint labels.
- **Supplied by:** the graph (Graph agent `neighborhood`).
- **Payload:** `nodes: {id, label}[]`, `edges: {source, target, relation, citationId}[]`, `citations`.
- **Caps:** 30 nodes, 40 edges; label at most 120 characters, relation at most 80.
- **Fences:** caps `nodes=30 edges=40 label_chars=120 relation_chars=80`; grounding `quote_names_both_ends_of_every_edge`; a11y `group:Graph of | region:Relations | region:Details | region:Sources`. Slots: `entities` (entity, 1 to 2). Template version 1; reusable without Research: yes.
- **Validator invariants:** labels 2 to 120 characters; node ids unique; every edge endpoint is a node; every node touches at least one edge; every
  edge cites a citation of this block; each cited quote contains both endpoint labels; no orphan citation.
- **States:** all four. Ready: a deterministic radial SVG diagram with selectable nodes and edges (selecting shows the
  incident edges' relation, quote and source link), keyboard operable, and a text list of every relation.
- **Placement hint:** studio panel, priority 20.
- **Admissible with flat retrieval:** no. Flat retrieval returns passages and no entities or labelled edges.
- **Feasibility measured on the live graph (2026-10-06, read-only):** 83 percent of edge endpoints and 70 percent of
  edges have their labels literally in the chunk they came from, so about 30 percent of edges would fail the label
  rule and be left out.
- **Measured through the Graph agent (B2, 2026-10-06):** on the 20 frozen benchmark questions, the agent returned 78
  edges and 34 (44 percent) were drawable under the label rule (a verbatim quote naming both endpoints as whole
  words or phrases, each label at least 2 characters); 16 of 20 questions had at least one drawable edge, so 16 would
  be offered a `GraphView`. (A first run with a plain substring match gave 41 edges, 53 percent, and 17 questions: the
  whole-word rule removed 7 edges where a label only appeared inside a longer word.) Path edges lose more than the
  corpus-wide 70 percent suggests, and `q-contra-04` (12 neighbourhood edges) had none. A looser label match (for
  example across a PDF hyphenation break) would raise the rate; it was not tried.
- **Quotes and the Research agent:** every Graph agent edge now carries `quote` (or null), `page` and `doc_title`.
  Edges without a quote stay in the payload, because the Research agent reads `chunk_ids` from it and the frozen
  evaluation depends on that; only the Composer leaves them out of the drawing (`graph_edges` in `catalog.py`).

## ComparisonGrid

Status: **built** (P2 B3, with the Graph agent tool `align_documents`).

- **Precondition:** at least 2 documents and 2 entities remain after alignment; every shown entity is evidenced in at
  least 2 of the shown documents; each present cell is grounded.
- **Supplied by:** cross-document entity alignment (`Node.doc_ids` and `chunk_ids` from the graph).
- **Payload:** `dimensions: {id, label}[]`, `rows: {docId, docTitle, cells: {dimensionId, citationId}[]}[]`, `citations`.
  A dimension with no evidence in a row has no cell; there is no text cell.
- **Caps:** 6 documents, 8 entities.
- **Fences:** caps `documents=6 entities=8 label_chars=120`; grounding `quote_of_row_document_names_column_label`; a11y `table:Comparison of | region:Comparison table | region:Sources`. Slots: `entities` (entity, 2 to 8), `documents` (document_id, 0 to 6). Template version 1; reusable without Research: yes.
- **Validator invariants:** unique dimension and row ids; two columns may not share a label; at most one cell per dimension in a row; a cell's dimension exists; a cell's citation exists, its chunk
  belongs to **the row's document**, and its quote contains the dimension's label; every dimension has cells in at least 2
  rows; every row has at least 1 cell; no orphan citation.
- **States:** all four. Ready: a table, documents as rows and entities as columns with headers; an empty cell is
  rendered as an explicit "no evidence in this paper" mark in text.
- **Placement hint:** chat panel, priority 20 (beneath the summary).
- **Admissible with flat retrieval:** no. Aligning documents on shared entities needs the graph.
- **Measured through the Graph agent (B3, 2026-10-06, read-only on a copy of the live data):** on the 20 frozen
  questions a grid was offered for all 20, each with the 6-document cap reached and 4 to 8 entity columns; 589 of the 858
  (document, entity) cells had evidence (69 percent), the rest render as "No evidence in this paper". The columns are
  the question's own entities first (for example `hybrid retrieval`, `graph traversal`, `BM25`) and then shared
  neighbours, which on this corpus include the hubs `LLM` and `RAG`.
- **Known weakness:** shared entities include generic hubs (`LLM`, `RAG` occur in 12 to 15 of 16 papers). Dimensions are the
  question's resolved entities plus their shared neighbours, capped at 8; grounding is guaranteed, usefulness is not.

## ConceptMap

Status: **built** (P2 B4).

- **Precondition:** a path of two to six hops between two entities, every hop backed by a verbatim quote that names
  both of its concepts, no repeated concept (compared ignoring case and spacing). (A 1-hop path is a `GraphView` case.)
- **Supplied by:** graph traversal (Graph agent `find_path`).
- **Payload:** `steps: {source, target, relation, reversed, citationId}[]`, `citations`. (`source` and `target`, not
  `from` and `to`: `from` is a Python keyword and the generated model could not have it. `reversed` is true when the stored
  relation runs against the path, so the map states the claim the way the document does.)
- **Caps:** 6 steps.
- **Fences:** caps `min_steps=2 steps=6 label_chars=120 relation_chars=80`; grounding `quote_names_both_ends_of_every_step`; a11y `list:Steps | region:Sources`. Slots: `entities` (entity, 2 to 2). Template version 1; reusable without Research: yes.
- **Validator invariants:** steps contiguous (`steps[i].source == steps[i-1].target`); no repeated node; each step cites a
  citation of this block whose quote contains both labels; no orphan citation.
- **States:** all four. Ready: a vertical chain (concept, relation, concept) with each step's quote and source link.
- **Placement hint:** studio panel, priority 30.
- **Admissible with flat retrieval:** no.
- **Measured through the Graph agent (B4, 2026-10-06, read-only on a copy of the live data):** on the 20 frozen
  questions a `ConceptMap` was offered for 3 (two paths of 3 hops, one of 4). 15 were refused because at least one hop
  had no verbatim quote naming both concepts (`ungrounded_hop`), 1 was a single hop (`single_hop`), 1 was not a path
  (`not_a_path`). Requiring every hop to be grounded is what makes a map trustworthy, and also what makes it rare on
  this corpus, where 44 percent of edges are drawable.

## TraversalView

Status: **built** (P2c T2 to T4). New in v2 (D-33); no v1 counterpart.

- **Precondition:** the question resolved to at least one concept in the graph (no more than the seeds cap, so the view is
  the whole search and not part of it), and the one-hop expansion from those concepts followed at least one edge that led
  to a passage the graph signal returned (a stored chunk among its ranked top ten).
- **Supplied by:** the graph signal's traversal (`trace_graph_signal`, run by the Graph agent and put in its payload as
  `traversal`). Flat retrieval has no graph, so it supplies nothing.
- **Payload:** `seeds: {nodeId, match}[]` (`exact` or `approximate`), `nodes: {id, label}[]`, `steps: {source, target,
  relation, citationId, hop}[]`, `reached: {citationId, via, rank, seedIds}[]`, `citations`, `stepsLeftOut`.
- **Caps:** 10 seeds, 40 nodes, 60 steps, 10 passages; label at most 120 characters.
- **Fences:** caps `seeds=10 nodes=40 steps=60 reached=10 label_chars=120`; grounding `provenance_rederived_from_stores`; a11y `group:Search path | region:Passages reached | region:Details`. Slots: `entities` (entity, 1 to 10, from the traversal's seeds). Template version 1; reusable without Research: yes.
- **Grounding is provenance, not "the text states the relation".** The view shows what the search followed: a followed edge
  may be a co-mention. Every claim is re-derived from the stores by the validator: it re-runs the traversal from the block's
  seeds (stored nodes, with their stored labels) and requires exactly the block's `reached` (the chunk each citation names,
  its `via`, its `rank` and the seeds that reach it), `steps` (the edges that led to those passages, best-ranked passage
  first, within the node and step caps) and `stepsLeftOut`. The seeds' `match` kind is taken as given (the validator does
  not see the question); it sets each seed's weight, which changes the order only when seeds of different kinds compete.
- **Validator invariants:** placeholders carry nothing; a ready block has at least one seed, step and passage; node ids
  unique with the stored label; every seed is a stored node; `reached` and `steps` equal the re-derived ones; every
  passage cites a stored chunk (title, page, a verbatim quote of at least the minimum length); every step cites a
  passage's citation; `hop` is 1; no orphan citation; caps.
- **States:** all four. Ready: a diagram with the seeds in a left column, the concepts they reach on the right, the
  followed edges between them, and the passages reached as a ranked list saying how each was reached, with selection by
  click or keyboard; and a text list of every step.
- **Placement hint:** studio panel, priority 25 (under `GraphView`).
- **Admissible with flat retrieval:** no.
- **Refusal reasons:** `no_graph_result`, `nothing_resolved`, `no_edge_followed`, `too_many_seeds` (more than 10 concepts).
- **What "reached" means:** the passages the graph signal itself ranks top ten, not the fused top ten the answer is built from; the view says it shows the route of the search, not what the documents state.
- **Feasibility measured on the live stores (2026-10-07, read-only):** on the 20 frozen questions the question resolves to
  3 to 10 concepts; the search follows 16 to 755 edges; the top ten are almost all reached by a concept's own mention. The
  view therefore shows only the edges that led to those passages and counts the rest. Admission on the 20 questions is
  measured in task T3.

## ConceptPage

Status: **built** (M2.6). New in v2 (D-35); no v1 counterpart. A **notes component**, not a turn component: the Composer never offers it
to a question and the trace never lists it. It is shown by the notes view (`GET /vault/notes?page=<id>`), and it has its own small
registry (`api/genui/notes_catalog.py`) instead of an entry in `CATALOG`.

- **Precondition:** the vault holds a page with this id, and at least one stored passage mentions it.
- **Supplied by:** the vault (`api/vault/`, compiled deterministically from the graph and the stored passages).
- **Payload:** `page: {id, label}`, `kind`, `aliases`, `passages`, `documents`, `definitions: {citationId}[]`, `links: {other,
  kind, relation, direction, citationId, passages}[]`, `linksLeftOut`, `claims: {citationId, pages}[]`, `mentions: {citationId}[]`,
  `mentionsLeftOut`, `citations`.
- **Caps:** 8 definitions, 40 links, 10 claims, 10 mentions, 20 aliases; label at most 120 characters.
- **Fences:** caps `definitions=8 links=40 claims=10 mentions=10 aliases=20 label_chars=120`; grounding `vault_rederived`; a11y `region:Definitions | region:Links | region:Claims | region:Mentions`. Template version 1; reusable without Research: no (it is not a turn component).
- **Grounding is derivation, not trust.** A page is a function of its id and the vault, so the validator derives it again and requires
  the block's data to equal the derived data exactly (names, counts, definitions, links in their order, claims, backlinks and every
  citation). Every sentence shown is a verbatim span of a stored passage and is cited: a definition is the builder's note, an asserted
  link's sentence is the evidence stored with the relation, a co-mention's sentence is the first one in which both names occur (it says
  nothing about how they are related), a claim is a sentence a builder marked, and a backlink is one sentence of a passage that
  mentions the page (passages in turn from each document, so a page that occurs in several papers shows several).
- **Mastery (M2.7, D-35 A6):** `mastery: {score, events} | null`, the learner's own belief about the concept from their ratings (a decayed Beta belief, half-life 14 days, `score = (A + 1) / (A + B + 2)`; null when they have no events, which is not a low score). It is derived from **one snapshot the Composer takes per request** and checked against that snapshot; a block that claims a mastery the snapshot does not hold is refused. The page shows it in words (comfortable from 0.67, getting there from 0.4, needs work below) and a meter, never as a mark, and offers the three ratings only when the screen can record them.
- **Always present:** every section is drawn, with a sentence saying so when its list is empty (the Claims region exists even before any builder has produced claims). A name longer than the label cap is cut on a word boundary where it is derived, so the cap is enforced and the block still equals the derived one.
- **Validator invariants:** placeholders carry nothing; a ready page needs at least one passage that mentions it; a block is refused when no vault is given or the vault has no such page; plain
  citation defects first (stored chunk, matching title and page, a verbatim quote of at least the minimum length, no orphan); then
  exact equality with the derived page, with the first differing places named.

## NotesGraph

Status: **built** (M2.6). New in v2 (D-35). A notes component (see ConceptPage).

- **Precondition:** the vault holds at least one page that matches the query (or the focus page). A focused graph shows that page and the
  pages linked to it, strongest first; the overview shows the most linked pages, narrowed by a case-insensitive match on a page's names.
- **Supplied by:** the vault.
- **Payload:** `focusId`, `query`, `nodes: {id, label, kind, passages, documents, degree}[]`, `edges: {source, target, kind, relation,
  passages}[]`, `nodesLeftOut`.
- **Caps:** 40 nodes, 120 edges; label at most 120 characters.
- **Fences:** caps `nodes=40 edges=120 label_chars=120`; grounding `vault_rederived`; a11y `group:Page graph | region:Pages`. Template version 1; reusable without Research: no.
- **Grounding is derivation.** The graph is a function of its focus, its query and the vault; the validator derives it again and requires
  the block's nodes, edges and `nodesLeftOut` to equal the derived ones. An edge is either asserted (a relation a model stated and the
  builder checked) or co-mentioned; the kind is on every edge so the two are never drawn alike.
- **Mastery colour:** each node carries `mastery` (a score or null). The screen fills a page by band (green comfortable, amber getting there, rose needs work, pale not rated yet) and says the same in words in the page's accessible name, in the list and in a legend: colour is never the only cue.
- **Edges beyond the cap:** the 120 edges shown are the first by kind (stated before named-together), then strength; the graph does not count the rest (every page is still listed with its link count, so nothing about a page is hidden). The screen draws only the lines that say something: the stated ones, those of the focus page and all of a chosen page's.
- **Validator invariants:** placeholders carry nothing but may repeat the query that found no page (it is shown as text); a ready graph has at least one page; equality with the derived graph.

## QuizCard

Status: **built** (Q1, D-35 amendment A8, which amends D-29: it was "Studio agent work (P5); no agent produces their evidence yet", and the vault's claims are that evidence). A notes component (see ConceptPage), shown by the notes view (`GET /vault/quiz?page=<id>`), and the quiz tool of the Studio's learning group (D-30): no agent is in front of it yet, and the Studio agent (P5) may add a second supplier of the same block behind the same validator.

- **Precondition:** the vault holds claims, and at least one names a page whose name (or an alias) occurs **literally** in the claim's sentence as a whole word, so a blank can be made, and that has at least three fair distractors: pages of its kind (when it has one) mentioned in at least two passages, whose names are not paper titles (at most six words, no `:` or `?`), are not in the sentence and are not made of the same words as the target's (so "language models" is never offered for "large language models").
- **Supplied by:** the vault (its claims, pages and the stored passages), the learner's mastery for the order. No model.
- **Payload:** `focusId`, `items: {id, text, options: {id, label}[4], docTitle, page}[]`, `skipped`. `text` is the claim's quote with every literal occurrence of every name of the target (label and aliases) replaced by `_____`, and no item is made when a name would still show; `docTitle` is empty when the title holds a name of the answer. **No item carries the answer or the unblanked sentence**; `id` is `<claim id>~<page id>`.
- **Caps:** 5 items, 4 options, label at most 120 characters.
- **Fences:** caps `items=5 options=4 label_chars=120`; grounding `vault_rederived`; a11y `region:Quiz questions | group:Answer choices`. Template version 1; reusable without Research: no.
- **Choosing items:** without a focus, claims are taken weakest first by the mastery of the page each would blank (an unrated page counts 0.5), then claim id, **one item per page**; with a focus, the claims that name that page in claim id order (up to 5). `skipped` counts the claims passed over (no blankable name, or looked at before the items were found and not made fairly). The options and their order depend on the item id and the vault only (a hash), so an item always reads the same.
- **Answering:** `POST /quiz/answer {itemId, chosenId}` derives the item again, records `quiz_correct` or `quiz_wrong` for the **blanked** page (never the page chosen) and answers `{correct, answer, citation (the sentence unblanked), mastery}`. An item the vault cannot derive is a 404, a choice that is not one of the four options a 422; neither records anything. The rating route still accepts only the three self-ratings.
- **Validator invariants:** `loading` and `error` carry nothing; the data equals the derived quiz exactly (every sentence, blank, option, order and `skipped`); a `ready` block has at least one item; an `empty` block is refused when the vault can make a question (it carries `skipped` so the screen can say how many claims were looked at); a block with an answer field is refused by the schema (no extra fields).
- **Failures:** a store failure while the server derives a quiz is a generic error envelope (the validator turns the same failure into a refusal); if the documents change after a quiz was shown, answers are refused (404 or 422, nothing recorded) and the screen offers more questions. The reply to an answer is built before the event is recorded.
- **Limit, stated on the screen:** a cloze tests recognising a name in a sentence, not understanding it; distractors chosen without a model can be too easy.

## InsightCard (stretch)

Status: **deferred** (task B5 was a stretch and was not built in P2; it needs Azim's agreement to start). Nothing below exists in code.

- **Precondition:** a path of at least 2 hops whose two endpoint entities are evidenced only in different documents
  (their document sets are disjoint).
- **Supplied by:** multi-hop traversal (Graph agent `cross_document_paths`).
- **Payload:** the two documents, the path steps and the citations; no free text beyond labels, relations and quotes.
- **Caps:** 6 steps.
- **Validator invariants:** all `ConceptMap` rules, plus the named documents are the ones the endpoints' cited chunks
  belong to, and the endpoints' document sets are disjoint as evidenced by those chunks.
- **Placement hint:** studio panel, priority 40.
- **Admissible with flat retrieval:** no.

## Not admitted, and why

| Component | Why it is not in P2 (D-29) |
|---|---|
| `ContradictionAlert` | "Disagree" needs a judge, a model call whose reliability is unmeasured. Only its structural half (two papers co-retrieved on one entity) is checkable |
| `Timeline` | Extraction records no dates; adding them changes the frozen extraction prompt and forces a second paid ingestion |
| `GapAnalysis` | Asserts absence; coverage over a concept space is undefined and communities are not a coverage claim |
| `ComparisonChart`, `DataTable` | No structured or numeric extraction exists; filling them means inventing values |
| `FlashcardDeck`, `BlurtingPrompt`, `FeynmanExplainer`, `CornellNotes`, `SocraticDialog`, `StudyPlanner` | Studio agent work (P5); no agent produces their evidence yet |
| `DraftEditor`, `CitationPreview`, `PlagiarismReport`, `BibliographyExport` | Studio and Fact Checker work (P5) |
| `ProgressDashboard` | Needs mastery data (P3, optional) |
| `AudioSummary` | A PRD non-goal |

## Layout defaults and placement hints

Each component declares a placement hint (`PlacementHint`: preferred panel, priority, optionally a region of that panel
(`main` unless it asks for `secondary` or `shelf`) and a split direction (`rows` or `columns`); lower priority sits first
in its region) on its catalog entry; `compose_layout` (`api/genui/layout.py`) reads the hints and contains no component names
(D-27, asserted by a source-scan test). The widths below are judgement defaults asserted by invariants (integers
summing to 100, chat at least 25, a panel with no placements has width 0 except chat and the studio, which keeps a narrow
column for its shelf), not by exact numbers.

| Layout | When | Sources | Chat | Studio |
|---|---|---|---|---|
| `prebuilt` (mode `basic`) | the workspace before any question, and the fallback | 20 | 60 | 20 |
| `adaptive`, mode `research`, with a `SourceList` | a turn whose admitted components include a studio-hinted one | 20 | 45 | 35 |
| `adaptive`, mode `research`, with a `SourceList`, no studio component | answer plus source list, or plus a grid | 20 | 60 | 20 (the shelf only) |
| `adaptive`, mode `exploration`, with a `SourceList` | intent `relate` and a studio-hinted component admitted | 10 | 30 | 60 |
| any adaptive layout with an empty panel | nothing placed there (for example no `SourceList`, so answer only is 0 / 80 / 20) | 0 for sources, 20 for the studio | the rest | |

**Regions inside a panel (D-32).** A panel is divided into the regions that hold something plus the ones it always
keeps (the studio always keeps `shelf`), sharing the panel in the weights main 3, secondary 2, shelf 2 (so main and
shelf are 60 and 40, main and secondary are 60 and 40), in whole numbers summing to 100. The direction is that of the
highest-priority hint in the panel that names one, else the panel's default (chat `columns`, studio and sources `rows`).
The studio panel is the graph area (`main`) above the shelf; the chat panel splits into `main` and `secondary` only when
a component asks for `secondary` (none of the five built ones does; the Studio components of P5 will). The prebuilt
layout always shows the studio's graph area above its shelf; in Basic the graph shows below the answer, so the graph
area says so. A new region role is a schema change, like a new panel. The fixed prebuilt layout is the exception to the shares: its studio is graph area 25 and shelf 75 (Basic shows graphs in chat, so the graph area is a sentence). A hint may name any region of any panel: a block placed in a region the screen gives no content of its own is still shown there. The chat panel always has a `main` region.

The prebuilt layout places only the workspace's own source list (in the sources panel, task C2); every turn block with no
placement is shown in chat in arrival order. `validate_layout` (`api/genui/validate.py`) asserts the invariants: version 2 (a version 1
layout, which has no regions, is read as one `main` region in every panel), the prebuilt origin goes with the basic mode,
whole-number widths summing to 100, chat present and at least 25, a hidden panel holds nothing; every panel has at least
one region, region ids are unique within a panel, sizes are whole numbers from 0 to 100 summing to 100, a region of size 0
holds nothing; each block placed once, in a region its panel has, orders unique within a region, only blocks the turn
produced (the caller must pass them). A layout that fails is not sent; the client applies the same rules
(`web/lib/layout.ts`, `readLayout`) and ignores one that does not pass. The Composer's rules for regions are below. A new
*component* needs no edit to `layout.py`; a new *panel* or *mode* is a change to the schema (`PanelId`, `LayoutMode`, `RegionId` and `SplitDirection` are closed unions), `layout.py`, `layout.ts` and the shell together (D-27, amended 2026-10-07).

## How to add a component

The recipe, in order. Task C1's toy-component test (`api/genui/test_layout.py`) follows steps 2 and 6 literally (a `Spec` with a hint, and a
`_RAW` entry); it reuses an existing block type, so steps 3, 4, 5 and 7 are not exercised by it.

1. **Write the precondition first** in a new section of this file: what the payload asserts, which retrieval signal
   supplies it, caps, validator invariants, states, placement hint, and whether flat retrieval could supply it. If
   retrieval cannot satisfy it, stop: the component is not admissible (see "Not admitted").
2. **Catalog entry** (`api/genui/catalog.py`): name, precondition statement, supplier, caps, a `PlacementHint`, and the
   deterministic `check(evidence)` returning satisfied plus reason codes.
3. **Schema first** (`packages/schema/src/payloads.ts`, `blocks.ts`): the `*Data` interface and the block variant added
   to the `UIBlock` union. Follow the schema conventions above. Then `pnpm codegen` and `pnpm codegen:check`.
4. **Validator rules** (`api/genui/validate.py`): the invariants, fail closed, each with a tamper test.
5. **Builder** (`api/genui/builders.py`): a raw block dict from the evidence, added to the `BUILDERS` dict (the
   completeness test compares it with the catalog and the schema). Only the Composer imports it.
6. **Admission and placement**: the Composer walks the catalog, so admission is automatic. Add one entry to `_RAW` in
   `api/agents/compose.py` (how the raw block is made from the evidence). Nothing in `layout.py`, `layout.ts` or the shell:
   the layout places the block by its hint (`test_layout.py` proves it with a toy component).
7. **Web component** (`web/components/genui/`): all four states, text form, roles and labels; registered in
   `registry.tsx` (a missing entry is a compile error).
8. **Tests**: admission (satisfied and not satisfied), tamper (each invariant), component states, a11y roles.
9. **Run `schema-guardian`**, update the completeness test's set (`PLANNED` in `api/agents/test_catalog.py`; `_RAW` and
   `BUILDERS` must also cover the name) and this file's status line.

## UI generation pipeline

D-31. One pipeline, five stages, for every UI the system produces. In P2 it runs for typed (data) UI and is built end to
end; P4 adds generated code to the same stages. The pipeline may be changed after testing (Azim, 2026-10-06), so each
stage is a small, replaceable interface. The five stage names below are the same five as `PIPELINE_STAGES` in
`api/genui/templates.py`, and a test compares them.

| Stage | As built in P2 (typed UI) | Where in code | What P4 adds |
|---|---|---|---|
| **Template** | a catalog `Spec`: name, version, precondition, typed slots (strings only), `reusable`, placement hint, fences | `api/genui/catalog.py` | a template body for generated artifacts; the Lab Builder starts from a template, never a blank page |
| **Fences** | per template: caps (the one source of the validator's limits), the grounding rule id, accessibility requirements; stated in each component section above and checked against the code by a parse | `Fences` in `catalog.py`; `fence_mismatches` in `templates.py` | allowed libraries, no network, no same-origin, resource budgets |
| **Checking** | precondition (`Spec.check`), build, schema, content validation (`validate_block`), a registration-time mutation suite (`register_template`: a template cannot register unless every planted defect is rejected; run at start-up), the layout validator and the last gate | `catalog.py`, `validate.py`, `templates.py`, `layout.py` | static analysis, contract property tests, fuzzing, a sandbox run, the verifier and delivery gate |
| **Save** | a pattern: template id and version, string parameters validated against the template's slots, layout mode; content-addressed; state `generated`, `verified` or `saved`; evidence never stored; saved only from a turn whose view was recorded as verified | `api/genui/patterns.py`, tables `ui_patterns` and `turn_views`, `POST/GET/DELETE /patterns` | `cached`, `audited`, `promoted`, eviction, crystallisation into a template |
| **Reuse** | apply a saved pattern: re-bind the evidence with the Graph agent's tools, re-check, fail closed with a reason (`precondition_not_met`, `template_changed`, `document_missing`); no model call; a stale pattern is re-verified (`POST /patterns/{id}/reverify`) | `compose_from_pattern`, `reverify_pattern` in `api/agents/compose.py`; `POST /patterns/{id}/apply` | reuse selected by evidence shape; staleness on a model or prompt change |

Hard constraint 3 is unchanged: no generated code reaches the client except as a verifier-minted type, and P2 contains
no code generation.

### Where P4 plugs in

- **Template:** a generated artifact's template body goes into a new field on `Spec` (the catalog entry stays the record
  of version, slots, fences and placement). Its `check` is the same precondition over `ComposerEvidence`.
- **Fences:** `Fences` gains the code-specific fences (allowed libraries from the local vendor directory, no network, no
  same-origin, resource budgets) beside `caps`, `grounding` and `a11y`; the guide's `**Fences:**` line and
  `fence_mismatches` extend with them.
- **Checking:** the checks are an ordered list of functions that each return the problems they find; the code stages
  (static analysis, contract property tests, fuzzing, the sandbox run) are appended before the verifier, which alone mints
  the type the client may render. `register_template`'s planted defects extend to planted code defects.
- **Save:** `PatternState` gains `cached`, `audited` and `promoted` (a schema change, so a client that does not know them
  refuses the pattern rather than guessing); `SavedPattern` stays strings only, and a generated artifact is referenced by
  the id of its verified record, never carried inline.
- **Reuse:** `compose_from_pattern` and `reverify_pattern` already return refusal reasons; P4 adds reasons for a changed
  model or prompt. Re-verification re-runs the template's registration suite, which for generated code is the whole
  checking stage.

### Re-verification

A pattern whose template has moved on (a different version, `template_changed`) is **stale**: applying it shows nothing
and names the reason. `POST /patterns/{id}/reverify` re-runs the template's registration suite and applies the pattern as
a dry run on the current evidence against the template's current version. If both pass, the pattern is made current with
that version and marked `verified`; if either fails, the pattern is left exactly as it was, stale, and the response
names the reason. Saving the same view again also brings a stale pattern up to date (the user has just saved a verified
view of the current template). Neither path calls a model.
