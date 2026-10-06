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
