import type { CitedSummary, ErrorEnvelope, StreamEvent } from "@arcana/schema";

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
    meta: { panel: "chat", order: 0, status, error },
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
