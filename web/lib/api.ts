// Non-streaming calls. Failures are returned as the shared ErrorEnvelope, never thrown as strings.

import type { ErrorEnvelope, IngestResponse, TurnTrace } from "@arcana/schema";

import { API_BASE, clientError, envelopeFromResponse } from "./stream";

export type UploadResult =
  | { ok: true; document: IngestResponse }
  | { ok: false; error: ErrorEnvelope };

export async function uploadPdf(
  file: File,
  options: { baseUrl?: string; fetchImpl?: typeof fetch } = {},
): Promise<UploadResult> {
  const { baseUrl = API_BASE, fetchImpl = fetch } = options;
  const form = new FormData();
  form.append("file", file);
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/ingest`, { method: "POST", body: form });
  } catch {
    return { ok: false, error: clientError("Could not reach the server.") };
  }
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    return { ok: true, document: (await response.json()) as IngestResponse };
  } catch {
    return { ok: false, error: clientError("The server sent an unreadable response.", false) };
  }
}

export type TraceResult = { ok: true; trace: TurnTrace } | { ok: false; error: ErrorEnvelope };

function isTurnTrace(value: unknown): value is TurnTrace {
  if (typeof value !== "object" || value === null) return false;
  const t = value as Partial<TurnTrace>;
  return (
    typeof t.turnId === "string" &&
    typeof t.hopsUsed === "number" &&
    typeof t.tokensUsed === "number" &&
    typeof t.outcome === "string" &&
    Array.isArray(t.steps) &&
    t.steps.every(
      (s) =>
        typeof s === "object" &&
        s !== null &&
        typeof s.agent === "string" &&
        typeof s.status === "string" &&
        typeof s.hop === "number" &&
        typeof s.tokens === "number" &&
        typeof s.latencyMs === "number" &&
        (s.note === null || typeof s.note === "string"),
    )
  );
}

/** What the agents did on one turn. The server validates the trace; this only refuses a body that is not one. */
export async function fetchTrace(
  turnId: string,
  options: { baseUrl?: string; fetchImpl?: typeof fetch } = {},
): Promise<TraceResult> {
  const { baseUrl = API_BASE, fetchImpl = fetch } = options;
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/turns/${encodeURIComponent(turnId)}/trace`);
  } catch {
    return { ok: false, error: clientError("Could not reach the server.") };
  }
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const body: unknown = await response.json();
    if (isTurnTrace(body)) return { ok: true, trace: body };
  } catch {
    // not JSON
  }
  return { ok: false, error: clientError("The server sent an unreadable response.", false) };
}
