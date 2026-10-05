// Non-streaming calls. Failures are returned as the shared ErrorEnvelope, never thrown as strings.

import type { ErrorEnvelope, IngestResponse } from "@arcana/schema";

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
