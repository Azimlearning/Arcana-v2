// Adapted from Azimlearning/Arcana (v1), web/lib/stream.ts @ 9a3d67f. Read in full. Kept: SSE over
// POST via fetch + ReadableStream (EventSource is GET-only) and frame-by-frame parsing across chunk
// boundaries. Rewritten for v2: the server sends only `data:` lines, each one a StreamEvent with its
// type inside the JSON; failures arrive as the shared ErrorEnvelope; and the client guarantees
// exactly one terminal callback.
//
// Terminal rule: a turn ends in onDone (the server's `done` event) or onError, never both and never
// neither. A stream that closes without `done`, a network failure, an HTTP error and a malformed
// frame are all onError. A caller-initiated abort is silent.

import type { BlockEvent, ChatRequest, ErrorEnvelope, LayoutSpec, StreamEvent, UIBlock } from "@arcana/schema";

import { isLayoutSpec } from "./layout";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export interface StreamHandlers {
  onBlock: (block: UIBlock) => void;
  /** The layout for the turn's blocks. Only a readable layout is delivered; an unreadable one is dropped. */
  onLayout?: (layout: LayoutSpec) => void;
  onError: (error: ErrorEnvelope) => void;
  onDone: () => void;
}

export interface StreamOptions {
  signal?: AbortSignal;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export function clientError(message: string, retryable = true): ErrorEnvelope {
  // No dedicated "network" code exists on the wire; an unreachable server is "provider_unavailable".
  return { code: "provider_unavailable", message, issues: [], retryable };
}

/** Read an error envelope from a non-2xx response body, or fall back to a generic one. */
export async function envelopeFromResponse(response: Response): Promise<ErrorEnvelope> {
  try {
    const body: unknown = await response.json();
    if (isEnvelope(body)) return body;
  } catch {
    // not JSON
  }
  return clientError(`The server answered with an error (HTTP ${response.status}).`, response.status >= 500);
}

function isEnvelope(value: unknown): value is ErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ErrorEnvelope).code === "string" &&
    typeof (value as ErrorEnvelope).message === "string" &&
    Array.isArray((value as ErrorEnvelope).issues)
  );
}

/** Turn one SSE message (the text between blank lines) into a StreamEvent, or null if it has no data. */
export function parseFrame(raw: string): StreamEvent | null {
  const data = raw
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  if (!data) return null; // a comment or keep-alive
  const parsed: unknown = JSON.parse(data);
  if (typeof parsed !== "object" || parsed === null) throw new Error("event is not an object");
  const event = parsed as { type?: unknown; block?: unknown; error?: unknown; layout?: unknown };
  if (event.type === "done") return { type: "done" };
  // A layout this client cannot read is not an error: it is ignored and the client keeps the layout it has.
  if (event.type === "layout") return isLayoutSpec(event.layout) ? { type: "layout", layout: event.layout } : null;
  if (event.type === "error" && isEnvelope(event.error)) return { type: "error", error: event.error };
  if (
    event.type === "block" &&
    typeof event.block === "object" &&
    event.block !== null &&
    typeof (event.block as { type?: unknown }).type === "string"
  ) {
    return event as BlockEvent;
  }
  throw new Error("unrecognised event");
}

/** Ask a question: POST /chat, a stream of blocks, a layout, then done. */
export function streamChat(request: ChatRequest, handlers: StreamHandlers, options: StreamOptions = {}): Promise<void> {
  return streamFrom(
    "/chat",
    { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body: JSON.stringify(request) },
    handlers,
    options,
  );
}

/**
 * Apply a saved view: POST /patterns/{id}/apply streams its block and layout the same way. A view that can no longer be
 * shown is refused before anything streams, as an HTTP 409 `pattern_refused` envelope: `onError` receives it and no
 * block is delivered.
 */
export function streamApply(patternId: string, handlers: StreamHandlers, options: StreamOptions = {}): Promise<void> {
  return streamFrom(
    `/patterns/${encodeURIComponent(patternId)}/apply`,
    { method: "POST", headers: { Accept: "text/event-stream" } },
    handlers,
    options,
  );
}

async function streamFrom(
  path: string,
  init: RequestInit,
  handlers: StreamHandlers,
  options: StreamOptions,
): Promise<void> {
  const { signal, baseUrl = API_BASE, fetchImpl = fetch } = options;
  let finished = false;
  const finish = (terminal: () => void) => {
    if (finished) return;
    finished = true;
    terminal();
  };
  const fail = (error: ErrorEnvelope) => finish(() => handlers.onError(error));

  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}${path}`, { ...init, signal });
  } catch {
    if (signal?.aborted) return;
    return fail(clientError("Could not reach the server."));
  }

  if (!response.ok) return fail(await envelopeFromResponse(response));
  if (!response.body) return fail(clientError("The server sent no response body."));

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatch = (raw: string) => {
    let event: StreamEvent | null;
    try {
      event = parseFrame(raw);
    } catch {
      return fail(clientError("The server sent a malformed message.", false));
    }
    if (finished || event === null) return;
    if (event.type === "block") handlers.onBlock(event.block);
    else if (event.type === "layout") handlers.onLayout?.(event.layout);
    else if (event.type === "error") fail(event.error);
    else finish(handlers.onDone);
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        dispatch(raw);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatch(buffer);
  } catch {
    if (signal?.aborted) return;
    return fail(clientError("The connection to the server was lost."));
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // already released
    }
  }

  // The stream ended cleanly but the server never said `done`: the turn was cut short.
  fail(clientError("The connection closed before the answer was complete."));
}
