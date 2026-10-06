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
