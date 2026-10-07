// Non-streaming calls. Failures are returned as the shared ErrorEnvelope, never thrown as strings.

import type {
  ErrorEnvelope,
  IngestResponse,
  LayoutMode,
  LearnerSignal,
  PatternState,
  SavedPattern,
  SavePatternRequest,
  TurnTrace,
  UIBlock,
  WorkspaceResponse,
} from "@arcana/schema";

import { readLayout } from "./layout";
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

/** The workspace body with its layout read (a version 1 layout upgraded), or null when it is not one. */
function readWorkspace(value: unknown): WorkspaceResponse | null {
  if (typeof value !== "object" || value === null) return null;
  const w = value as { layout?: unknown; blocks?: unknown };
  const layout = readLayout(w.layout);
  if (!layout || !Array.isArray(w.blocks) || !w.blocks.every(isBlockShape)) return null;
  return { ...(value as WorkspaceResponse), layout };
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
    const workspace = readWorkspace(body);
    if (workspace) return { ok: true, workspace };
  } catch {
    // not JSON
  }
  return { ok: false, error: clientError("The server sent an unreadable response.", false) };
}


/**
 * The notes view (M2.6, D-35): a concept page (when `page` is given) and the graph of pages around it, with the layout the
 * Composer chose. The same body as `/workspace`, read the same way: a body that is not one is an error, never a half-drawn view.
 */
export async function fetchNotes(
  params: { page?: string | null; query?: string } = {},
  options: { baseUrl?: string; fetchImpl?: typeof fetch; signal?: AbortSignal } = {},
): Promise<WorkspaceResult> {
  const { baseUrl = API_BASE, fetchImpl = fetch, signal } = options;
  const search = new URLSearchParams();
  if (params.page) search.set("page", params.page);
  if (params.query?.trim()) search.set("query", params.query.trim());
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/vault/notes${suffix}`, { signal });
  } catch {
    return { ok: false, error: clientError("Could not reach the server.") };
  }
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const workspace = readWorkspace(await response.json());
    if (workspace) return { ok: true, workspace };
  } catch {
    // not JSON
  }
  return { ok: false, error: clientError("The server sent an unreadable response.", false) };
}

/** Record the learner's own rating of a page of the vault (D-35 A6). True when the server saved it. */
export async function recordLearnerEvent(
  pageId: string,
  signal: LearnerSignal,
  options: { baseUrl?: string; fetchImpl?: typeof fetch } = {},
): Promise<boolean> {
  const { baseUrl = API_BASE, fetchImpl = fetch } = options;
  try {
    const response = await fetchImpl(`${baseUrl}/learner/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pageId, signal }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// ── saved views (patterns) ───────────────────────────────────────────────────

export type PatternsResult = { ok: true; patterns: SavedPattern[] } | { ok: false; error: ErrorEnvelope };
export type SaveResult = { ok: true; pattern: SavedPattern } | { ok: false; error: ErrorEnvelope };
export type DeleteResult = { ok: true } | { ok: false; error: ErrorEnvelope };

// Records, not arrays, so adding a member to the schema's union fails typecheck until it is added here.
const PATTERN_STATES: Record<PatternState, true> = { generated: true, verified: true, saved: true };
const LAYOUT_MODES: Record<LayoutMode, true> = { basic: true, research: true, exploration: true };
const isIn = (set: Record<string, true>, value: unknown) => typeof value === "string" && Object.hasOwn(set, value);

export function isSavedPattern(value: unknown): value is SavedPattern {
  if (typeof value !== "object" || value === null) return false;
  const p = value as Partial<SavedPattern>;
  return (
    typeof p.id === "string" &&
    p.id !== "" &&
    typeof p.name === "string" &&
    typeof p.templateId === "string" &&
    Number.isInteger(p.templateVersion) &&
    Array.isArray(p.params) &&
    p.params.every(
      (q) => typeof q === "object" && q !== null && typeof q.key === "string" && Array.isArray(q.values) && q.values.every((v) => typeof v === "string"),
    ) &&
    typeof p.layoutMode === "string" &&
    isIn(LAYOUT_MODES, p.layoutMode) &&
    typeof p.state === "string" &&
    isIn(PATTERN_STATES, p.state) &&
    Number.isInteger(p.useCount) &&
    typeof p.createdAt === "string" &&
    (p.lastUsedAt === null || typeof p.lastUsedAt === "string")
  );
}

type Options = { baseUrl?: string; fetchImpl?: typeof fetch };

async function call(path: string, init: RequestInit | undefined, options: Options): Promise<Response | ErrorEnvelope> {
  const { baseUrl = API_BASE, fetchImpl = fetch } = options;
  try {
    return await fetchImpl(`${baseUrl}${path}`, init);
  } catch {
    return clientError("Could not reach the server.");
  }
}

const unreadable = () => clientError("The server sent an unreadable response.", false);

/** The user's saved views. The server validates every one; this only refuses a body that is not a list of them. */
export async function listPatterns(options: Options = {}): Promise<PatternsResult> {
  const response = await call("/patterns", undefined, options);
  if (!(response instanceof Response)) return { ok: false, error: response };
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const body = (await response.json()) as { patterns?: unknown };
    if (Array.isArray(body?.patterns) && body.patterns.every(isSavedPattern)) return { ok: true, patterns: body.patterns };
  } catch {
    // not JSON
  }
  return { ok: false, error: unreadable() };
}

/** Keep one view of a finished turn. */
export async function savePattern(request: SavePatternRequest, options: Options = {}): Promise<SaveResult> {
  const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) };
  const response = await call("/patterns", init, options);
  if (!(response instanceof Response)) return { ok: false, error: response };
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const body: unknown = await response.json();
    if (isSavedPattern(body)) return { ok: true, pattern: body };
  } catch {
    // not JSON
  }
  return { ok: false, error: unreadable() };
}

/**
 * Check a saved view again against the current layout and your documents. On success it is current and `verified`; a
 * failure is the server's `pattern_refused` envelope (the view is left as it was).
 */
export async function reverifyPattern(id: string, options: Options = {}): Promise<SaveResult> {
  const response = await call(`/patterns/${encodeURIComponent(id)}/reverify`, { method: "POST" }, options);
  if (!(response instanceof Response)) return { ok: false, error: response };
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  try {
    const body: unknown = await response.json();
    if (isSavedPattern(body)) return { ok: true, pattern: body };
  } catch {
    // not JSON
  }
  return { ok: false, error: unreadable() };
}

export async function deletePattern(id: string, options: Options = {}): Promise<DeleteResult> {
  const response = await call(`/patterns/${encodeURIComponent(id)}`, { method: "DELETE" }, options);
  if (!(response instanceof Response)) return { ok: false, error: response };
  if (!response.ok) return { ok: false, error: await envelopeFromResponse(response) };
  return { ok: true };
}
