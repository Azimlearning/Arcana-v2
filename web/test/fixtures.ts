import type { CitedSummary, ComparisonGrid, ConceptMap, ErrorEnvelope, GraphView, LayoutSpec, SavedPattern, SourceList, WorkspaceResponse, StreamEvent, TurnTrace } from "@arcana/schema";

export const TITLE = "Hybrid Retrieval over Knowledge Graphs";

export function block(
  status: CitedSummary["meta"]["status"],
  overrides: Partial<CitedSummary["data"]> = {},
  error: ErrorEnvelope | null = null,
): CitedSummary {
  const content = status === "ready" || status === "partial";
  return {
    type: "CitedSummary",
    id: "turn-1",
    meta: { status, error },
    data: {
      segments: content
        ? [
            { text: "Dense retrieval embeds passages.", citationIds: ["c1"] },
            { text: "BM25 scores exact terms.", citationIds: ["c1", "c2"] },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 1, quote: "Dense Retrieval embeds passages and queries." },
            { id: "c2", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: null, quote: "BM25 is a sparse method." },
          ]
        : [],
      ...overrides,
    },
  };
}

export function sourceList(
  status: SourceList["meta"]["status"],
  documents: SourceList["data"]["documents"] = [
    { docId: "d1", title: TITLE, chunkCount: 12 },
    { docId: "d2", title: "BM25 in Practice", chunkCount: 1 },
  ],
  error: ErrorEnvelope | null = null,
): SourceList {
  const content = status === "ready" || status === "partial";
  return {
    type: "SourceList",
    id: "turn-1-sources",
    meta: { status, error },
    data: { documents: content ? documents : [] },
  };
}

export function graphView(
  status: GraphView["meta"]["status"],
  overrides: Partial<GraphView["data"]> = {},
  error: ErrorEnvelope | null = null,
): GraphView {
  const content = status === "ready" || status === "partial";
  return {
    type: "GraphView",
    id: "turn-1-graph-view",
    meta: { status, error },
    data: {
      nodes: content
        ? [
            { id: "dense", label: "Dense Retrieval" },
            { id: "bm25", label: "BM25" },
            { id: "rrf", label: "Reciprocal Rank Fusion" },
          ]
        : [],
      edges: content
        ? [
            { source: "dense", target: "bm25", relation: "contrasted with", citationId: "c1" },
            { source: "dense", target: "rrf", relation: "merged by", citationId: "c2" },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 3, quote: "Dense Retrieval alone and BM25 alone are two arms." },
            { id: "c2", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: null, quote: "Reciprocal Rank Fusion merges Dense Retrieval with the others." },
          ]
        : [],
      ...overrides,
    },
  };
}

export function comparisonGrid(
  status: ComparisonGrid["meta"]["status"],
  overrides: Partial<ComparisonGrid["data"]> = {},
  error: ErrorEnvelope | null = null,
): ComparisonGrid {
  const content = status === "ready" || status === "partial";
  return {
    type: "ComparisonGrid",
    id: "turn-1-comparison-grid",
    meta: { status, error },
    data: {
      dimensions: content
        ? [
            { id: "dense", label: "Dense Retrieval" },
            { id: "bm25", label: "BM25" },
          ]
        : [],
      rows: content
        ? [
            {
              docId: "d1",
              docTitle: TITLE,
              cells: [
                { dimensionId: "dense", citationId: "c1" },
                { dimensionId: "bm25", citationId: "c2" },
              ],
            },
            { docId: "d2", docTitle: "Second Paper", cells: [{ dimensionId: "dense", citationId: "c3" }] },
            { docId: "d3", docTitle: "Third Paper", cells: [{ dimensionId: "bm25", citationId: "c4" }, { dimensionId: "dense", citationId: "c5" }] },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "k1", docId: "d1", docTitle: TITLE, page: 1, quote: "Dense Retrieval embeds queries." },
            { id: "c2", chunkId: "k2", docId: "d1", docTitle: TITLE, page: 2, quote: "BM25 scores exact terms." },
            {
              id: "c3",
              chunkId: "k3",
              docId: "d2",
              docTitle: "Second Paper",
              page: null,
              quote: "In this second paper, Dense Retrieval underpins the baseline pipeline and is described at considerable length across many sentences.",
            },
            { id: "c4", chunkId: "k4", docId: "d3", docTitle: "Third Paper", page: 5, quote: "BM25 is the sparse arm of the third paper." },
            { id: "c5", chunkId: "k5", docId: "d3", docTitle: "Third Paper", page: 6, quote: "Dense Retrieval is also used in the third paper." },
          ]
        : [],
      ...overrides,
    },
  };
}

export function conceptMap(
  status: ConceptMap["meta"]["status"],
  overrides: Partial<ConceptMap["data"]> = {},
  error: ErrorEnvelope | null = null,
): ConceptMap {
  const content = status === "ready" || status === "partial";
  return {
    type: "ConceptMap",
    id: "turn-1-concept-map",
    meta: { status, error },
    data: {
      steps: content
        ? [
            { source: "Alpha Method", target: "Beta Index", relation: "builds on", reversed: false, citationId: "c1" },
            { source: "Beta Index", target: "Gamma Cache", relation: "compared with", reversed: false, citationId: "c2" },
            { source: "Gamma Cache", target: "Delta Store", relation: "feeds", reversed: false, citationId: "c3" },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "k1", docId: "d", docTitle: TITLE, page: 1, quote: "Alpha Method builds on Beta Index for fast lookup." },
            { id: "c2", chunkId: "k2", docId: "d", docTitle: TITLE, page: 2, quote: "Beta Index is compared with Gamma Cache in experiments." },
            { id: "c3", chunkId: "k3", docId: "d", docTitle: TITLE, page: 3, quote: "Gamma Cache feeds the Delta Store in the pipeline." },
          ]
        : [],
      ...overrides,
    },
  };
}

/** An adaptive layout placing the given blocks, as the server's `compose_layout` would for a turn. */
export function layout(placements: LayoutSpec["placements"], overrides: Partial<LayoutSpec> = {}): LayoutSpec {
  return {
    version: 2,
    origin: "adaptive",
    mode: "research",
    panels: [
      { id: "sources", width: 20, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
      { id: "chat", width: 45, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
      { id: "studio", width: 35, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    ],
    placements,
    ...overrides,
  };
}

/** What GET /workspace returns: the prebuilt layout and the source list it places. */
export function workspace(documents: SourceList["data"]["documents"] = [{ docId: "d0", title: "Stored Paper", chunkCount: 7 }]): WorkspaceResponse {
  const prebuilt = JSON.parse(JSON.stringify(FALLBACK)) as LayoutSpec;
  const list = sourceList(documents.length ? "ready" : "empty", documents);
  return { layout: prebuilt, blocks: [{ ...list, id: "workspace-sources" }] };
}

const FALLBACK: LayoutSpec = {
  version: 2,
  origin: "prebuilt",
  mode: "basic",
  panels: [
    { id: "sources", width: 20, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    { id: "chat", width: 60, direction: "columns" as const, regions: [{ id: "main" as const, size: 100 }] },
    {
      id: "studio",
      width: 20,
      direction: "rows" as const,
      regions: [
        { id: "main" as const, size: 25 },
        { id: "shelf" as const, size: 75 },
      ],
    },
  ],
  placements: [{ blockId: "workspace-sources", panel: "sources", region: "main" as const, order: 0 }],
};

export function savedPattern(overrides: Partial<SavedPattern> = {}): SavedPattern {
  return {
    id: "p-1",
    name: "Dense vs BM25",
    templateId: "GraphView",
    templateVersion: 1,
    params: [{ key: "entities", values: ["Dense Retrieval", "BM25"] }],
    layoutMode: "research",
    state: "saved",
    useCount: 0,
    createdAt: "2026-10-07T10:00:00+00:00",
    lastUsedAt: null,
    ...overrides,
  };
}

export function envelope(overrides: Partial<ErrorEnvelope> = {}): ErrorEnvelope {
  return { code: "provider_unavailable", message: "The model is unavailable.", issues: [], retryable: true, ...overrides };
}

export const frame = (event: StreamEvent) => `data: ${JSON.stringify(event)}\n\n`;

const encoder = new TextEncoder();

/**
 * An SSE response delivered as the given chunks, one per read. `breakAfter` errors the stream after
 * the last chunk instead of closing it, like a dropped connection. It must be pull-based: calling
 * controller.error() right after enqueue() would discard the queued chunks, which a real network
 * drop does not do to data already received.
 */
export function sseResponse(chunks: string[], options: { breakAfter?: boolean; status?: number } = {}): Response {
  let next = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (next < chunks.length) {
        controller.enqueue(encoder.encode(chunks[next++] ?? ""));
      } else if (options.breakAfter) {
        controller.error(new Error("connection reset"));
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { status: options.status ?? 200, headers: { "Content-Type": "text/event-stream" } });
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export function trace(overrides: Partial<TurnTrace> = {}): TurnTrace {
  return {
    turnId: "turn-1",
    outcome: "answered",
    hopsUsed: 3,
    tokensUsed: 1200,
    steps: [
      { hop: 0, agent: "orchestrator", status: "ok", tokens: 1200, latencyMs: 40, note: null },
      { hop: 1, agent: "research", status: "ok", tokens: 900, latencyMs: 25, note: null },
      { hop: 2, agent: "fact_checker", status: "partial", tokens: 300, latencyMs: 8, note: "removed 1 of 3 segments" },
    ],
    composition: [
      { component: "CitedSummary", offered: true, reasons: [] },
      { component: "SourceList", offered: true, reasons: [] },
      { component: "GraphView", offered: false, reasons: ["no_grounded_edge"] },
      { component: "ComparisonGrid", offered: false, reasons: ["no_shared_entities"] },
      { component: "ConceptMap", offered: false, reasons: ["single_hop"] },
    ],
    ...overrides,
  };
}
