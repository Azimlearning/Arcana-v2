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
