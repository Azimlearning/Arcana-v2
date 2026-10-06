# The GenUI catalog: components, preconditions, and how to add one

> Written in P2 task A1, before any component's schema type exists (hard constraint 7: a component joins the
> catalog on evidence, with a written structural precondition that retrieval can satisfy). Plan:
> `refdocs/plans/2026-10-06-p2-genui-catalog-dashboard.md`. Decisions: D-27 (layout), D-28 (Composer), D-29 (scope),
> D-31 (pipeline). Status of each component is stated in its section; only `CitedSummary` is built today.

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
- **Caps:** none beyond the citation rules.
- **Validator invariants:** as in `api/genui/validate.py` (citations unique and resolvable, no orphan citation, a ready
  block has a segment, every segment cites).
- **States:** all four; `empty` for a declined or unanswerable question (the `q-single-01` control renders here).
- **Placement hint:** chat panel, priority 10 (first).
- **Admissible with flat retrieval:** yes.

## SourceList

Status: planned, task B1.

- **Precondition:** at least one document with status `ready` in the document store.
- **Supplied by:** the document store (metadata only).
- **Payload:** `documents: {docId, title, chunkCount}[]`.
- **Caps:** 50 documents; title as stored.
- **Validator invariants:** unique ids; every `docId` exists and is `ready`; `title` and `chunkCount` equal the stored
  values; placeholder statuses carry no documents. It asserts existence only, so it carries no citations.
- **States:** `empty` when no documents exist; `loading`; `error`; ready list.
- **Placement hint:** sources panel, priority 10.
- **Admissible with flat retrieval:** yes (it needs no retrieval at all, which is why it can be shown before any question).

## GraphView

Status: planned, task B2. **Must work on real data and be interactive (D-29).**

- **Precondition:** at least 2 entities and 1 labelled edge after grounding; every edge is backed by a stored chunk whose
  cited quote contains both endpoint labels.
- **Supplied by:** the graph (Graph agent `neighborhood`).
- **Payload:** `nodes: {id, label}[]`, `edges: {source, target, relation, citationId}[]`, `citations`.
- **Caps:** 30 nodes, 40 edges; label at most 120 characters, relation at most 80.
- **Validator invariants:** node ids unique; every edge endpoint is a node; every node touches at least one edge; every
  edge cites a citation of this block; each cited quote contains both endpoint labels; no orphan citation.
- **States:** all four. Ready: a deterministic radial SVG diagram with selectable nodes and edges (selecting shows the
  incident edges' relation, quote and source link), keyboard operable, and a text list of every relation.
- **Placement hint:** studio panel, priority 20.
- **Admissible with flat retrieval:** no. Flat retrieval returns passages and no entities or labelled edges.
- **Feasibility measured on the live graph (2026-10-06, read-only):** 83 percent of edge endpoints and 70 percent of
  edges have their labels literally in the chunk they came from, so about 30 percent of edges would fail the label
  rule and be left out.

## ComparisonGrid

Status: planned, task B3 (with the Graph agent tool `align_documents`).

- **Precondition:** at least 2 documents and 2 entities remain after alignment; every shown entity is evidenced in at
  least 2 of the shown documents; each present cell is grounded.
- **Supplied by:** cross-document entity alignment (`Node.doc_ids` and `chunk_ids` from the graph).
- **Payload:** `dimensions: {id, label}[]`, `rows: {docId, docTitle, cells: {dimensionId, citationId}[]}[]`, `citations`.
  A dimension with no evidence in a row has no cell; there is no text cell.
- **Caps:** 6 documents, 8 entities.
- **Validator invariants:** unique dimension and row ids; a cell's dimension exists; a cell's citation exists, its chunk
  belongs to **the row's document**, and its quote contains the dimension's label; every dimension has cells in at least 2
  rows; every row has at least 1 cell; no orphan citation.
- **States:** all four. Ready: a table, documents as rows and entities as columns with headers; an empty cell is
  rendered as an explicit "no evidence in this paper" mark in text.
- **Placement hint:** chat panel, priority 20 (beneath the summary).
- **Admissible with flat retrieval:** no. Aligning documents on shared entities needs the graph.
- **Known weakness:** shared entities include generic hubs (`LLM`, `RAG` occur in 12 to 15 of 16 papers). Dimensions are the
  question's resolved entities plus their shared neighbours, capped at 8; grounding is guaranteed, usefulness is not.

## ConceptMap

Status: planned, task B4.

- **Precondition:** a path of at least 2 labelled hops between two entities, every hop grounded, no repeated node. (A
  1-hop path is a `GraphView` case.)
- **Supplied by:** graph traversal (Graph agent `find_path`).
- **Payload:** `steps: {from, relation, to, citationId}[]`, `citations`.
- **Caps:** 6 steps.
- **Validator invariants:** steps contiguous (`steps[i].to == steps[i+1].from`); no repeated node; each step cites a
  citation of this block whose quote contains both labels; no orphan citation.
- **States:** all four. Ready: a vertical chain (concept, relation, concept) with each step's quote and source link.
- **Placement hint:** studio panel, priority 30.
- **Admissible with flat retrieval:** no.

## InsightCard (stretch)

Status: planned only if the phase has room, task B5.

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
| `FlashcardDeck`, `QuizCard`, `BlurtingPrompt`, `FeynmanExplainer`, `CornellNotes`, `SocraticDialog`, `StudyPlanner` | Studio agent work (P5); no agent produces their evidence yet |
| `DraftEditor`, `CitationPreview`, `PlagiarismReport`, `BibliographyExport` | Studio and Fact Checker work (P5) |
| `ProgressDashboard` | Needs mastery data (P3, optional) |
| `AudioSummary` | A PRD non-goal |

## Layout defaults and placement hints

Each component declares a placement hint (preferred panel, priority) on its catalog entry; `compose_layout` reads the
hints and contains no component names (D-27). The widths below are judgement defaults asserted by invariants (integers
summing to 100, chat at least 25, a panel with no placements has width 0 except chat), not by exact numbers.

| Layout | When | Sources | Chat | Studio |
|---|---|---|---|---|
| `prebuilt` (mode `basic`) | the workspace before any question, and the fallback | 20 | 60 | 20 |
| `adaptive`, mode `research` | a turn whose admitted components include a studio-hinted one | 20 | 45 | 35 |
| `adaptive`, mode `research`, no studio component | answer only or answer plus grid | 20 | 80 | 0 |
| `adaptive`, mode `exploration` | intent `relate` and a graph-hinted component admitted | 10 | 30 | 60 |
| any adaptive layout without a `SourceList` | no sources component | 0 | chat plus studio as above, sources width added to chat | |

## How to add a component

The recipe, in order. Task C1's toy-component test follows it literally; if a step here is wrong, that test fails.

1. **Write the precondition first** in a new section of this file: what the payload asserts, which retrieval signal
   supplies it, caps, validator invariants, states, placement hint, and whether flat retrieval could supply it. If
   retrieval cannot satisfy it, stop: the component is not admissible (see "Not admitted").
2. **Catalog entry** (`api/genui/catalog.py`): name, version, precondition statement, supplier, caps, fences, placement
   hint, and the deterministic `check(evidence)` returning satisfied plus reason codes.
3. **Schema first** (`packages/schema/src/payloads.ts`, `blocks.ts`): the `*Data` interface and the block variant added
   to the `UIBlock` union. Follow the schema conventions above. Then `pnpm codegen` and `pnpm codegen:check`.
4. **Validator rules** (`api/genui/validate.py`): the invariants, fail closed, each with a tamper test.
5. **Builder** (`api/genui/builders.py`): a raw block dict from the evidence. Only the Composer imports it.
6. **Admission**: automatic. The Composer walks the catalog; nothing to edit in `compose.py` and nothing in
   `layout.py`.
7. **Web component** (`web/components/genui/`): all four states, text form, roles and labels; registered in
   `registry.tsx` (a missing entry is a compile error).
8. **Tests**: admission (satisfied and not satisfied), tamper (each invariant), component states, a11y roles.
9. **Run `schema-guardian`**, update the completeness test's set and this file's status line.

## UI generation pipeline

D-31. One pipeline, five stages, for every UI the system produces. In P2 it runs for typed (data) UI; P4 adds generated
code to the same stages. The pipeline may be changed after testing (Azim, 2026-10-06), so each stage is a small,
replaceable interface.

| Stage | P2 (typed UI) | Where in code | P4 adds |
|---|---|---|---|
| **Template** | a catalog entry: version, typed slots, evidence requirements, placement hint | `api/genui/catalog.py`, `templates.py` (task E1) | a template body for generated artifacts; the Lab Builder starts from a template, never a blank page |
| **Fences** | caps, the grounding rule, accessibility requirements, declared per template | `templates.py` (E1) | allowed libraries, no network, no same-origin, resource budgets |
| **Checking** | precondition, build, schema, content validation, a registration-time mutation suite, accessibility structure | `catalog.py`, `validate.py`, `templates.py` | static analysis, contract property tests, fuzzing, a sandbox run, the verifier and delivery gate |
| **Save** | a pattern: template id and version, typed parameters, layout mode; content-addressed; state `generated`, `verified`, `saved`; evidence never stored | `api/genui/patterns.py`, `ui_patterns` table (E2) | `cached`, `audited`, `promoted`, eviction, crystallisation into a template |
| **Reuse** | apply a saved pattern: re-bind fresh evidence, re-check, fail closed with a reason (`precondition_not_met`, `template_changed`, `document_missing`) | `compose_from_pattern` (E3), re-verification (E4) | reuse selected by evidence shape; staleness on a model or prompt change |

Hard constraint 3 is unchanged: no generated code reaches the client except as a verifier-minted type, and P2 contains
no code generation.
