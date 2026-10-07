// Per-component data payloads. One *Data interface per UIBlock variant.
//
// Codegen conventions (see codegen/to_python.ts):
//   - `number` maps to Python `float`; tag a property `/** @int */` to get `int`.
//   - Every generated model is strict (no coercion) and forbids unknown fields (fail closed).

/** A claim's evidence: the stored chunk it came from. `chunkId` is what makes it traceable. */
export interface Citation {
  id: string;
  chunkId: string;
  docId: string;
  docTitle: string;
  /** @int */
  page: number | null;
  quote: string;
}

/** A span of the answer and the citations that support it. */
export interface SummarySegment {
  text: string;
  citationIds: string[];
}

/**
 * The answer is its segments, in order; there is no separate summary string to drift from them.
 * In a `ready` block every segment cites at least one entry of `citations`, and every citation's
 * chunkId and docId resolve to stored chunks. The schema cannot say so; the server validator does.
 */
export interface CitedSummaryData {
  segments: SummarySegment[];
  citations: Citation[];
}

/** One uploaded document as the source list shows it. Both fields are copied from the document store. */
export interface SourceItem {
  docId: string;
  /** The stored title, verbatim. Render it as text. */
  title: string;
  /**
   * Number of stored passages for the document.
   * @int
   */
  chunkCount: number;
}

/**
 * The documents the workspace can answer from. In a `ready` block there is at least one item (at most 50),
 * ids are unique, every docId is a stored document whose status is `ready`, and `title` and `chunkCount`
 * equal the stored values. Placeholder blocks (`empty`, `loading`, `error`) carry no documents. The schema
 * cannot say so; the server validator does.
 */
export interface SourceListData {
  documents: SourceItem[];
}

/** A concept in the graph. `id` is the graph's canonical key; `label` is its display name as stored. */
export interface GraphNode {
  id: string;
  label: string;
}

/**
 * A relation between two nodes, evidenced by one citation of this block (`citationId`). In a `ready` block the
 * cited quote contains the labels of both endpoints. Direction is source to target.
 */
export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  citationId: string;
}

/**
 * A node-link graph of what the documents say connects. In a `ready` block there is at least one edge, at most 30
 * nodes and 40 edges, node ids are unique, every edge joins two different listed nodes, every node touches an
 * edge, every edge cites a citation of this block, and every citation is cited. Citations follow the CitedSummary
 * rules (stored chunk, matching title and page, verbatim quote). Placeholders carry no nodes, edges or citations.
 * The schema cannot say so; the server validator does.
 */
export interface GraphViewData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  citations: Citation[];
}

/** A column of the comparison: one entity the compared documents all discuss. `label` is its display name. */
export interface GridDimension {
  id: string;
  label: string;
}

/**
 * What one document says about one dimension: `citationId` names a citation of this block whose chunk belongs to
 * the row's document and whose quote contains the dimension's label. A dimension with no evidence in a row simply
 * has no cell: there is no text cell and no placeholder.
 */
export interface GridCell {
  dimensionId: string;
  citationId: string;
}

/** One document of the comparison. `docTitle` is the stored title. */
export interface GridRow {
  docId: string;
  docTitle: string;
  cells: GridCell[];
}

/**
 * Documents as rows and shared entities as columns. In a `ready` block there are at least 2 rows (at most 6) and 2
 * dimensions (at most 8), ids are unique, every row exists in the store under its title, every row has a cell, every
 * dimension has cells in at least 2 rows, each document and dimension has at most one cell per row, and every
 * citation is cited. Placeholders carry no rows, dimensions or citations. The schema cannot say so; the server
 * validator does.
 */
export interface ComparisonGridData {
  dimensions: GridDimension[];
  rows: GridRow[];
  citations: Citation[];
}

/**
 * One hop of a concept path, in path order: from `source` to `target` (both are concept labels as stored).
 * `reversed` says the stored relation runs the other way: when true the document says `target` `relation`
 * `source`, so a reader never sees a relation pointing the wrong way. In a `ready` block the cited quote
 * (`citationId`, a citation of this block) contains both labels.
 */
export interface PathStep {
  source: string;
  target: string;
  relation: string;
  reversed: boolean;
  citationId: string;
}

/**
 * How two concepts connect through the documents: an ordered path of 2 to 6 hops. In a `ready` block the steps are
 * contiguous (each step's source is the previous step's target), no concept repeats, every step cites a citation of
 * this block whose quote contains both of its labels, and every citation is cited. Placeholders carry no steps or
 * citations. The schema cannot say so; the server validator does.
 */
export interface ConceptMapData {
  steps: PathStep[];
  citations: Citation[];
}

// ── TraversalView (P2c, D-33): what the graph signal followed for one question ──────────────────────────────────────

/** How a seed concept was found in the question: the whole name matched (`exact`) or only part of it (`approximate`). */
export type SeedMatch = "exact" | "approximate";

/** A concept the question resolved to: a stored node. The label is in `nodes`. */
export interface TraversalSeed {
  nodeId: string;
  match: SeedMatch;
}

/**
 * One edge the search followed from a seed, one hop, in either direction. `relation` is the stored relation string,
 * unchanged. `citationId` names the reached passage the edge was extracted from.
 */
export interface TraversalStep {
  source: string;
  target: string;
  relation: string;
  citationId: string;
  /** @int */
  hop: number;
}

/**
 * How a passage was reached, strongest first: `mentions` (it mentions a seed), `edge` (a relation touching a seed was
 * extracted from it), `neighbour` (it only mentions a concept one hop from a seed).
 */
export type ReachedVia = "mentions" | "edge" | "neighbour";

/** A passage the graph signal returned. `rank` is its place in the signal's own ranking (1 first). */
export interface ReachedPassage {
  citationId: string;
  via: ReachedVia;
  /** @int */
  rank: number;
  /** The seeds that reach it (any way). */
  seedIds: string[];
}

/**
 * What the graph signal followed for one question, derived from the stores and checked against them: the concepts the
 * question resolved to (`seeds`), the edges followed from them that led to a returned passage (`steps`), the passages
 * returned in the signal's order (`reached`), and how many followed edges are not listed (`stepsLeftOut`). It shows what
 * the SEARCH did, not what the documents state: a followed edge may be a co-mention. In a `ready` block, re-running the
 * traversal from `seeds` over the stores gives exactly these `steps`, `reached` and `stepsLeftOut`; every node is a stored
 * node with its stored label; every reached passage cites a stored chunk with a verbatim quote; at most 10 seeds, 40
 * nodes, 60 steps and 10 passages. Placeholders carry no seeds, nodes, steps, passages or citations. The schema cannot
 * say so; the server validator does.
 */
export interface TraversalViewData {
  seeds: TraversalSeed[];
  nodes: GraphNode[];
  steps: TraversalStep[];
  reached: ReachedPassage[];
  citations: Citation[];
  /** @int */
  stepsLeftOut: number;
}

// ── The notes view (M2, D-35): a page per concept and a graph of pages, derived from the vault ─────────────────────

/** A concept page, by id and display label. `id` is the page's key in the vault; `label` is its stored display name. */
export interface PageRef {
  id: string;
  label: string;
}

/** A verbatim sentence of a stored passage, cited by `citationId` (a citation of the same block). */
export interface PageSentence {
  citationId: string;
}

/**
 * How `ConceptPage` is linked to another page. `asserted`: a model stated the relation (`relation`, with `direction`
 * `out` if this page is its source and `in` if it is its target) and the cited sentence is the evidence the builder stored.
 * `co_mention`: the two names occur in the cited sentence, which says nothing about how they are related (`relation` and
 * `direction` are null). `passages` is how many passages carry the link.
 */
export type PageLinkKind = "asserted" | "co_mention";
export type PageLinkDirection = "out" | "in";

export interface PageLinkItem {
  other: PageRef;
  kind: PageLinkKind;
  relation: string | null;
  direction: PageLinkDirection | null;
  citationId: string;
  /** @int */
  passages: number;
}

/** A sentence that states a finding or a definition worth remembering, with the pages it names. */
export interface PageClaimItem {
  citationId: string;
  pages: PageRef[];
}

/**
 * One concept across every document: its names, how widely it occurs, the sentences that define it, how it is linked to
 * other pages (asserted links first, then co-mentions, strongest first), the claims that name it, and passages that
 * mention it (the backlinks). Derived from the vault and checked against it: in a `ready` block, re-deriving the page from
 * `page.id` over the vault and the stored passages gives exactly this data; every citation is a stored passage with a
 * verbatim quote; at most 8 definitions, 40 links, 10 claims and 10 mentions are shown and the rest are counted. Placeholders
 * carry nothing. The schema cannot say so; the server validator does.
 */
export interface ConceptPageData {
  page: PageRef;
  kind: string | null;
  aliases: string[];
  /** @int */
  passages: number;
  /** @int */
  documents: number;
  definitions: PageSentence[];
  links: PageLinkItem[];
  /** @int */
  linksLeftOut: number;
  claims: PageClaimItem[];
  mentions: PageSentence[];
  /** @int */
  mentionsLeftOut: number;
  citations: Citation[];
  /** The learner's mastery of this concept, or null when they have no events for it. */
  mastery: Mastery | null;
}

/** A page as the notes graph draws it: how many passages and documents mention it and how many pages it is linked to. */
export interface NotesNode {
  id: string;
  label: string;
  kind: string | null;
  /** @int */
  passages: number;
  /** @int */
  documents: number;
  /** @int */
  degree: number;
  /** The learner's mastery score in [0, 1], or null when they have no events for this page. */
  mastery: number | null;
}

/** A link between two pages, drawn as a line: asserted (`relation` as stored) or co-mentioned; `passages` is its strength. */
export interface NotesEdge {
  source: string;
  target: string;
  kind: PageLinkKind;
  relation: string | null;
  /** @int */
  passages: number;
}

/**
 * Pages and the links among them. With a `focusId` it is that page and the pages linked to it (strongest first), with the
 * links among them; without one it is the pages most linked across the vault, narrowed by `query` (a case-insensitive
 * match on a page's names; empty for none). Derived from the vault and checked against it: re-deriving the graph from
 * `focusId` and `query` gives exactly these nodes and edges and `nodesLeftOut`; at most 40 nodes and 120 edges. A `ready`
 * block has at least one node. Placeholders carry nothing. The schema cannot say so; the server validator does.
 */
export interface NotesGraphData {
  focusId: string | null;
  query: string;
  nodes: NotesNode[];
  edges: NotesEdge[];
  /** @int */
  nodesLeftOut: number;
}

// ── The quiz (Q1, D-35 A8): a sentence from the documents with one concept name blanked ───────────────────────────────

/**
 * One question: `text` is a sentence of a stored passage with one concept name replaced by `_____`, `options` are four pages
 * (the blanked one and three others, in a fixed shuffled order), `docTitle` and `page` say where the sentence is from. The item
 * does not say which option is right and does not carry the sentence unblanked: the server answers (POST /quiz/answer).
 * `id` is `<claim id>~<page id of the blanked concept>` and is what the answer route reads.
 */
export interface QuizItem {
  id: string;
  text: string;
  options: PageRef[];
  docTitle: string;
  /** @int */
  page: number | null;
}

/**
 * A quiz over the vault's claims: with a `focusId`, claims that name that page; without one, claims across the vault, the
 * concepts the learner knows least first. At most 5 items; `skipped` counts claims looked at and passed over (no way to make
 * a blank, or fewer than three fair distractors). Derived from the vault, the stored passages and the learner's mastery and
 * checked against them: re-deriving the quiz from `focusId` gives exactly these items and `skipped`. A `ready` block has at
 * least one item, and no item names its answer. An `empty` block (nothing could be made into a question) has no items and says in
 * `skipped` how many claims were looked at; `loading` and `error` carry nothing. The schema cannot say so; the server validator does.
 */
export interface QuizCardData {
  focusId: string | null;
  items: QuizItem[];
  /** @int */
  skipped: number;
}

// ── VerifiedLab (P4, D-36): a generated function that only the verifier can let through ─────────────────────────────

/** One parameter of a lab: a finite range with a default, drawn as a slider. */
export interface LabParameter {
  name: string;
  label: string;
  min: number;
  max: number;
  default: number;
  unit: string | null;
}

/** What the verifier ran, as counts: it is not a proof for every input. */
export interface LabChecked {
  /** @int */
  referenceCases: number;
  /** @int */
  properties: number;
  /** @int */
  fuzzCases: number;
  /** Every combination of slider positions the interface can ask the function for: all of them were run. */
  /** @int */
  gridPoints: number;
}

/**
 * A lab: one pure function `lab(p)` from the declared parameters to a number, generated and then verified (D-36). `source` is the
 * verified function text and is INERT DATA until the web host places it, with its own fixed template, in an iframe whose sandbox is
 * exactly `allow-scripts`; `sourceSha256` is its hash and `templateVersion` the version of the host's template it was verified for.
 * The host checks both before it renders. The sliders snap to the grid and the plot is the function's value as `sweep` runs across its grid
 * values, drawn by the template; the verifier ran every combination of grid values, so every input the interface can ask for was verified.
 * `citations` holds one citation: the stored passage that states the formula. Derived from the verified record and checked against it:
 * the server validator re-derives the block from `labId` and requires equality, so a changed byte, a stale template version or an
 * unverified lab is refused. Placeholders carry nothing. The schema cannot say so; the server validator does.
 */
export interface VerifiedLabData {
  labId: string;
  contractId: string;
  title: string;
  parameters: LabParameter[];
  sweep: string;
  /** Steps per parameter: a slider has `gridSteps + 1` positions and nothing between, `min + (max - min) * k / gridSteps`. */
  /** @int */
  gridSteps: number;
  outputLabel: string;
  source: string;
  sourceSha256: string;
  /** @int */
  templateVersion: number;
  citations: Citation[];
  checked: LabChecked;
}

// ── The learner layer (M2.7, D-35 A6) ────────────────────────────────────────────────────────────────────────────────

/**
 * What the learner knows about one concept, from their own events (self-ratings now, quiz results later): `score` is a belief in
 * [0, 1] that decays towards ignorance (D-35 A6), `events` how many events there have been. A page with no events has no
 * mastery (null), which is not the same as a low one.
 */
export interface Mastery {
  score: number;
  /** @int */
  events: number;
}
