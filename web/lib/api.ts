// Non-streaming calls. Failures are returned as the shared ErrorEnvelope, never thrown as strings.

import type { ErrorEnvelope, IngestResponse, TurnTrace, UIBlock, WorkspaceResponse } from "@arcana/schema";

import { isLayoutSpec } from "./layout";
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
    Array.isArray(t.composition) &&
    t.composition.every(
      (d) =>
        typeof d === "object" &&
        d !== null &&
        typeof d.component === "string" &&
        typeof d.offered === "boolean" &&
        Array.isArray(d.reasons) &&
        d.reasons.every((r) => typeof r === "string"),
    ) &&
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

export type WorkspaceResult = { ok: true; workspace: WorkspaceResponse } | { ok: false; error: ErrorEnvelope };

function isBlockShape(value: unknown): value is UIBlock {
  if (typeof value !== "object" || value === null) return false;
  const b = value as { type?: unknown; id?: unknown; meta?: unknown; data?: unknown };
  const meta = b.meta as { status?: unknown } | null;
  return (
    typeof b.type === "string" &&
    typeof b.id === "string" &&
    b.id !== "" &&
    typeof meta === "object" &&
    meta !== null &&
    typeof meta.status === "string" &&
    typeof b.data === "object" &&
    b.data !== null
  );
}

function isWorkspace(value: unknown): value is WorkspaceResponse {
  if (typeof value !== "object" || value === null) return false;
  const w = value as { layout?: unknown; blocks?: unknown };
  return isLayoutSpec(w.layout) && Array.isArray(w.blocks) && w.blocks.every(isBlockShape);
}

/**
 * The workspace before any question: the prebuilt layout and its blocks. The server validates both; this only refuses a
 * body that is not one, so an unreadable response is an error and never a half-rendered workspace.
 */
export async function fetchWorkspace(
  options: { baseUrl?: string; fetchImpl?: typeof fetch } = {},
): Promise<WorkspaceResult> {
  const { baseUrl = API_BASE, fetchImpl = fetch } = options;
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/workspace`);
  } catch {
    return { ok: false, error: clientError("Could not reach the server.") };
  }
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const body: unknown = await response.json();
    if (isWorkspace(body)) return { ok: true, workspace: body };
  } catch {
    // not JSON
  }
  return { ok: false, error: clientError("The server sent an unreadable response.", false) };
}
