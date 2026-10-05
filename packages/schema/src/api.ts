// HTTP and stream shapes that cross the wire. Anything that crosses the wire belongs here.

import type { UIBlock } from "./blocks";
import type { ErrorEnvelope } from "./errors";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

/**
 * POST /chat body. Single user (D-04), so there is no notebook or user id.
 * The schema has no length bounds; the endpoint enforces them (non-empty message, capped history).
 */
export interface ChatRequest {
  message: string;
  history: ChatMessage[];
}

/** POST /ingest response. The request itself is multipart/form-data and has no schema type. */
export interface IngestResponse {
  docId: string;
  title: string;
  status: "ready" | "failed";
  /** @int */
  chunkCount: number;
  /** Populated when status is "failed". */
  error: string | null;
}

// ── SSE stream (POST /chat) ─────────────────────────────────────────────────
// Each SSE message carries exactly one StreamEvent as JSON in `data:`.
// A BlockEvent whose block.id was already seen REPLACES that block (upsert by id): this is how a
// block moves loading -> partial -> ready. There is no patch type.

export interface BlockEvent {
  type: "block";
  block: UIBlock;
}

/** A failure of the whole turn (as opposed to one block, which carries meta.error). */
export interface StreamErrorEvent {
  type: "error";
  error: ErrorEnvelope;
}

export interface DoneEvent {
  type: "done";
}

export type StreamEvent = BlockEvent | StreamErrorEvent | DoneEvent;
