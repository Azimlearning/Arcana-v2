import type { CitedSummary, ComparisonGrid, ConceptMap, ConceptPage, ErrorEnvelope, GraphView, LayoutSpec, NotesGraph, QuizAnswerResponse, QuizCard, DocBrief, CheatSheet, LearningInsights, StudyPlan, StudySet, VerifiedLab, WritingDraft, SavedPattern, SourceList, TraversalView, WorkspaceResponse, StreamEvent, TurnTrace } from "@arcana/schema";

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

export function traversalView(
  status: TraversalView["meta"]["status"],
  overrides: Partial<TraversalView["data"]> = {},
  error: ErrorEnvelope | null = null,
): TraversalView {
  const content = status === "ready" || status === "partial";
  return {
    type: "TraversalView",
    id: "turn-1-traversal-view",
    meta: { status, error },
    data: {
      seeds: content
        ? [
            { nodeId: "dense", match: "exact" },
            { nodeId: "bm25", match: "approximate" },
          ]
        : [],
      nodes: content
        ? [
            { id: "dense", label: "Dense Retrieval" },
            { id: "bm25", label: "BM25" },
            { id: "rrf", label: "Reciprocal Rank Fusion" },
          ]
        : [],
      steps: content
        ? [
            { source: "dense", target: "bm25", relation: "contrasted_with", citationId: "c1", hop: 1 },
            { source: "dense", target: "rrf", relation: "merged_by", citationId: "c2", hop: 1 },
          ]
        : [],
      reached: content
        ? [
            { citationId: "c1", via: "mentions", rank: 1, seedIds: ["dense", "bm25"] },
            { citationId: "c2", via: "edge", rank: 2, seedIds: ["dense"] },
            { citationId: "c3", via: "neighbour", rank: 3, seedIds: ["bm25"] },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 3, quote: "Dense Retrieval alone and BM25 alone are two arms." },
            { id: "c2", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: null, quote: "Reciprocal Rank Fusion merges Dense Retrieval with the others." },
            { id: "c3", chunkId: "d_c_3", docId: "d", docTitle: TITLE, page: 4, quote: "Sparse retrieval such as BM25 scores exact terms." },
          ]
        : [],
      stepsLeftOut: content ? 7 : 0,
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


export function conceptPage(
  status: ConceptPage["meta"]["status"],
  overrides: Partial<ConceptPage["data"]> = {},
  error: ErrorEnvelope | null = null,
): ConceptPage {
  const content = status === "ready" || status === "partial";
  return {
    type: "ConceptPage",
    id: "page:rag",
    meta: { status, error },
    data: content
      ? {
          page: { id: "rag", label: "Retrieval-Augmented Generation" },
          kind: "concept",
          aliases: ["RAG"],
          passages: 2,
          documents: 2,
          definitions: [{ citationId: "c1" }],
          links: [
            {
              other: { id: "self_rag", label: "Self-RAG" },
              kind: "asserted",
              relation: "extended_by",
              direction: "in",
              citationId: "c2",
              passages: 1,
            },
            {
              other: { id: "large_language_model", label: "large language models" },
              kind: "co_mention",
              relation: null,
              direction: null,
              citationId: "c3",
              passages: 1,
            },
          ],
          linksLeftOut: 1,
          claims: [
            {
              citationId: "c2",
              pages: [
                { id: "rag", label: "Retrieval-Augmented Generation" },
                { id: "self_rag", label: "Self-RAG" },
              ],
            },
          ],
          mentions: [{ citationId: "c1" }, { citationId: "c3" }],
          mentionsLeftOut: 3,
          mastery: null,
          citations: [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 1, quote: "Retrieval-Augmented Generation (RAG) combines retrieval with generation." },
            { id: "c2", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: null, quote: "Self-RAG extends RAG with reflection tokens." },
            { id: "c3", chunkId: "e_c_1", docId: "e", docTitle: "Second Paper", page: 4, quote: "RAG helps large language models answer from documents." },
          ],
          ...overrides,
        }
      : {
          page: { id: "", label: "" },
          kind: null,
          aliases: [],
          passages: 0,
          documents: 0,
          definitions: [],
          links: [],
          linksLeftOut: 0,
          claims: [],
          mentions: [],
          mentionsLeftOut: 0,
          citations: [],
          mastery: null,
        },
  };
}

export function notesGraph(
  status: NotesGraph["meta"]["status"],
  overrides: Partial<NotesGraph["data"]> = {},
  error: ErrorEnvelope | null = null,
): NotesGraph {
  const content = status === "ready" || status === "partial";
  return {
    type: "NotesGraph",
    id: "notes-graph",
    meta: { status, error },
    data: {
      focusId: null,
      query: "",
      nodes: content
        ? [
            { id: "rag", label: "Retrieval-Augmented Generation", kind: "concept", passages: 2, documents: 2, degree: 2, mastery: null },
            { id: "self_rag", label: "Self-RAG", kind: "method", passages: 1, documents: 1, degree: 2, mastery: null },
            { id: "llm", label: "large language models", kind: null, passages: 1, documents: 1, degree: 1, mastery: null },
          ]
        : [],
      edges: content
        ? [
            { source: "self_rag", target: "rag", kind: "asserted", relation: "extends", passages: 1 },
            { source: "llm", target: "rag", kind: "co_mention", relation: null, passages: 1 },
          ]
        : [],
      nodesLeftOut: 0,
      ...overrides,
    },
  };
}

export function quizCard(
  status: QuizCard["meta"]["status"],
  overrides: Partial<QuizCard["data"]> = {},
  error: ErrorEnvelope | null = null,
): QuizCard {
  const content = status === "ready" || status === "partial";
  return {
    type: "QuizCard",
    id: "quiz",
    meta: { status, error },
    data: {
      focusId: null,
      items: content
        ? [
            {
              id: "claim-1~dense_retrieval",
              text: "_____ finds passages by comparing embedding vectors of the query and the text.",
              options: [
                { id: "bm25", label: "BM25" },
                { id: "dense_retrieval", label: "dense retrieval" },
                { id: "reranking", label: "reranking" },
                { id: "rrf", label: "reciprocal rank fusion" },
              ],
              docTitle: TITLE,
              page: 3,
            },
            {
              id: "claim-2~bm25",
              text: "_____ scores terms by their frequency in a passage and their rarity across the corpus.",
              options: [
                { id: "reranking", label: "reranking" },
                { id: "bm25", label: "BM25" },
                { id: "query_expansion", label: "query expansion" },
                { id: "rrf", label: "reciprocal rank fusion" },
              ],
              docTitle: TITLE,
              page: null,
            },
          ]
        : [],
      skipped: 0,
      ...overrides,
    },
  };
}

export function quizAnswer(overrides: Partial<QuizAnswerResponse> = {}): QuizAnswerResponse {
  return {
    itemId: "claim-1~dense_retrieval",
    correct: true,
    answer: { id: "dense_retrieval", label: "dense retrieval" },
    citation: {
      id: "c1",
      chunkId: "c1",
      docId: "d1",
      docTitle: TITLE,
      page: 3,
      quote: "Dense retrieval finds passages by comparing embedding vectors of the query and the text.",
    },
    mastery: { score: 0.6667, events: 1 },
    ...overrides,
  };
}


export const LAB_SOURCE =
  "function lab(p) {\n  const d = p.sj - p.si;\n  if (d > 0) {\n    return d + Math.log1p(Math.exp(-d));\n  }\n  return Math.log1p(Math.exp(d));\n}";
export const LAB_SHA256 = "8ffe9aa0bdcc9b90f4795f3b27ff397533afac5abf1348fbe748ec8769424be7";

export function verifiedLab(
  status: VerifiedLab["meta"]["status"],
  overrides: Partial<VerifiedLab["data"]> = {},
  error: ErrorEnvelope | null = null,
): VerifiedLab {
  const content = status === "ready";
  return {
    type: "VerifiedLab",
    id: "lab",
    meta: { status, error },
    data: {
      labId: content ? "ranknet_pairwise_loss-8ffe9aa0bdcc" : "",
      contractId: content ? "ranknet_pairwise_loss" : "",
      title: content ? "RankNet pairwise loss for one pair of passages" : "",
      parameters: content
        ? [
            { name: "si", label: "score of the passage ranked first", min: -4, max: 4, default: 0, unit: null },
            { name: "sj", label: "score of the passage ranked second", min: -4, max: 4, default: 1, unit: null },
          ]
        : [],
      sweep: content ? "sj" : "",
      gridSteps: content ? 64 : 0,
      outputLabel: content ? "loss" : "",
      source: content ? LAB_SOURCE : "",
      sourceSha256: content ? LAB_SHA256 : "",
      templateVersion: content ? 2 : 0,
      citations: content
        ? [
            {
              id: "c1",
              chunkId: "c1",
              docId: "d1",
              docTitle: "A Ranking Paper",
              page: 16,
              quote: "RankNet is a pairwise loss that measures the correctness of relative passage orders",
            },
          ]
        : [],
      checked: content ? { referenceCases: 4, properties: 5, fuzzCases: 200, gridPoints: 4225 } : { referenceCases: 0, properties: 0, fuzzCases: 0, gridPoints: 0 },
      ...overrides,
    },
  };
}

export function writingDraft(
  status: WritingDraft["meta"]["status"],
  overrides: Partial<WritingDraft["data"]> = {},
  error: ErrorEnvelope | null = null,
): WritingDraft {
  const content = status === "ready" || status === "partial";
  return {
    type: "WritingDraft",
    id: "turn-1-writing-draft",
    meta: { status, error },
    data: {
      title: content ? "Hybrid retrieval in brief" : "",
      sections: content
        ? [
            { heading: "Background", segments: [{ text: "Dense retrieval embeds passages and queries.", citationIds: ["c1"] }] },
            { heading: "Sparse methods", segments: [{ text: "BM25 scores exact terms.", citationIds: ["c1", "c2"] }] },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 1, quote: "Dense Retrieval embeds passages and queries." },
            { id: "c2", chunkId: "d_c_2", docId: "e", docTitle: "BM25 in Practice", page: null, quote: "BM25 is a sparse method." },
          ]
        : [],
      bibliography: content
        ? [
            { docId: "d", apa: `${TITLE}.`, ieee: `"${TITLE}."`, bibtex: `@misc{arcanad,\n  title = {${TITLE}}\n}` },
            {
              docId: "e",
              apa: "BM25 in Practice. arXiv:2401.00001.",
              ieee: '"BM25 in Practice," arXiv:2401.00001.',
              bibtex: "@misc{arcanae,\n  title = {BM25 in Practice},\n  eprint = {2401.00001},\n  archivePrefix = {arXiv}\n}",
            },
          ]
        : [],
      ...overrides,
    },
  };
}

export function studySet(
  status: StudySet["meta"]["status"],
  overrides: Partial<StudySet["data"]> = {},
  error: ErrorEnvelope | null = null,
  item: Partial<StudySet["data"]["items"][number]> = {},
  withSummary = false,
): StudySet {
  const content = status === "ready" || status === "partial";
  const quote = "Dense retrieval finds passages by comparing embedding vectors of the query and the text.";
  return {
    type: "StudySet",
    id: "turn-1-study-set",
    meta: { status, error },
    data: {
      kind: "flashcard",
      focusId: content ? "dense_retrieval" : null,
      items: content
        ? [
            {
              id: "i1",
              prompt: "dense retrieval",
              hint: null,
              pageId: "dense_retrieval",
              pageLabel: "dense retrieval",
              notes: [{ citationId: "c1" }],
              ...item,
            },
          ]
        : [],
      summary: content && withSummary ? { citationId: "c1" } : null,
      citations: content ? [{ id: "c1", chunkId: "d_c_1", docId: "d1", docTitle: "Paper One", page: 3, quote }] : [],
      skipped: 0,
      ...overrides,
    },
  };
}

export function studyPlan(
  status: StudyPlan["meta"]["status"],
  overrides: Partial<StudyPlan["data"]> = {},
  error: ErrorEnvelope | null = null,
): StudyPlan {
  const content = status === "ready" || status === "partial";
  return {
    type: "StudyPlan",
    id: "turn-1-study-plan",
    meta: { status, error },
    data: {
      asOf: "2026-10-15",
      items: content
        ? [
            { pageId: "bm25", pageLabel: "BM25", score: 0.2, events: 3, due: "now", daysSince: 1 },
            { pageId: "rrf", pageLabel: "reciprocal rank fusion", score: 0.6, events: 1, due: "soon", daysSince: 3 },
            { pageId: "dense_retrieval", pageLabel: "dense retrieval", score: 0.9, events: 6, due: "later", daysSince: 0 },
          ]
        : [],
      ratedPages: content ? 5 : 0,
      leftOut: content ? 2 : 0,
      ...overrides,
    },
  };
}

export function docBrief(
  status: DocBrief["meta"]["status"],
  overrides: Partial<DocBrief["data"]> = {},
  error: ErrorEnvelope | null = null,
): DocBrief {
  const content = status === "ready" || status === "partial";
  return {
    type: "DocBrief",
    id: "turn-1-doc-brief",
    meta: { status, error },
    data: {
      docId: content ? "d" : "",
      docTitle: content ? TITLE : "",
      keyPoints: content
        ? [
            { citationId: "c1", pageLabels: ["dense retrieval", "BM25"] },
            { citationId: "c2", pageLabels: ["reciprocal rank fusion"] },
          ]
        : [],
      terms: content ? [{ pageId: "dense_retrieval", pageLabel: "dense retrieval", citationId: "c3" }] : [],
      actions: content
        ? [
            { kind: "review", pageId: "bm25", pageLabel: "BM25", reason: "Your mastery is 20 percent: revisit it." },
            { kind: "learn", pageId: "dense_retrieval", pageLabel: "dense retrieval", reason: "You have not rated it yet: start with its definition." },
            { kind: "quiz", pageId: "dense_retrieval", pageLabel: "dense retrieval", reason: "Test yourself: ask for a quiz on it." },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 1, quote: "Dense retrieval embeds passages and BM25 scores exact terms." },
            { id: "c2", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: 2, quote: "Reciprocal rank fusion merges two ranked lists." },
            { id: "c3", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 1, quote: "Dense retrieval is a method that embeds text into vectors." },
          ]
        : [],
      claimsInDocument: content ? 9 : 0,
      leftOut: content ? 3 : 0,
      ...overrides,
    },
  };
}

export function cheatSheet(
  status: CheatSheet["meta"]["status"],
  overrides: Partial<CheatSheet["data"]> = {},
  error: ErrorEnvelope | null = null,
): CheatSheet {
  const content = status === "ready" || status === "partial";
  return {
    type: "CheatSheet",
    id: "turn-1-cheat-sheet",
    meta: { status, error },
    data: {
      focusId: content ? "rrf" : null,
      entries: content
        ? [
            { pageId: "rrf", pageLabel: "reciprocal rank fusion", kind: "method", citationId: "c1" },
            { pageId: "dense_retrieval", pageLabel: "dense retrieval", kind: "method", citationId: "c2" },
            { pageId: "bm25", pageLabel: "BM25", kind: null, citationId: "c3" },
          ]
        : [],
      edges: content
        ? [
            { src: "dense_retrieval", dst: "rrf", relation: "combines" },
            { src: "bm25", dst: "rrf", relation: null },
          ]
        : [],
      citations: content
        ? [
            { id: "c1", chunkId: "d_c_2", docId: "d", docTitle: TITLE, page: 5, quote: "Reciprocal rank fusion combines the rankings of dense retrieval and BM25." },
            { id: "c2", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 3, quote: "Dense retrieval finds passages by comparing embedding vectors." },
            { id: "c3", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: null, quote: "BM25 scores terms by their frequency in a passage." },
          ]
        : [],
      skipped: content ? 1 : 0,
      ...overrides,
    },
  };
}

export function learningInsights(
  status: LearningInsights["meta"]["status"],
  overrides: Partial<LearningInsights["data"]> = {},
  error: ErrorEnvelope | null = null,
): LearningInsights {
  const content = status === "ready" || status === "partial";
  const days = (from: number, counts: number[]) =>
    counts.map((count, i) => ({ date: `2026-10-${String(from + i).padStart(2, "0")}`, count }));
  return {
    type: "LearningInsights",
    id: "turn-1-learning-insights",
    meta: { status, error },
    data: {
      asOf: "2026-10-15",
      pages: content ? 20 : 0,
      ratedPages: content ? 5 : 0,
      bands: content ? { needsWork: 2, gettingThere: 1, comfortable: 2 } : { needsWork: 0, gettingThere: 0, comfortable: 0 },
      weakest: content
        ? [
            { pageId: "bm25", pageLabel: "BM25", score: 0.2, events: 3 },
            { pageId: "rrf", pageLabel: "reciprocal rank fusion", score: 0.45, events: 2 },
          ]
        : [],
      activity: content ? days(2, [0, 1, 0, 2, 3, 0, 1, 0, 0, 2, 4, 1, 0, 3]) : [],
      activeDays: content ? 8 : 0,
      trend: content ? { slopePerDay: 0.12, movingAverage: [0, 0.5, 0.33, 1, 1.67, 1.67, 1.33, 0.33, 0.33, 0.67, 2, 2.33, 1.67, 1.33] } : null,
      workload: content ? days(16, [2, 2, 3, 3, 3, 4, 5]).map((d) => ({ date: d.date, due: d.count })) : [],
      ...overrides,
    },
  };
}
