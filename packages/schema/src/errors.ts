// The one error shape. Every failure the client can see arrives as an ErrorEnvelope, never a stack trace.

export type ErrorCode =
  | "validation_failed"
  | "bad_request"
  | "not_found"
  | "budget_exhausted"
  | "spend_cap_exceeded"
  | "provider_unavailable"
  | "pattern_refused"
  | "internal";

/**
 * Why a saved view cannot be shown: `precondition_not_met` (the evidence no longer supports the view), `template_changed`
 * (the view was made with another version of its template, so it is stale until re-verified) or `document_missing` (a
 * document it names is gone).
 */
export type PatternRefusalReason = "precondition_not_met" | "template_changed" | "document_missing";

// `pattern_refused` is the answer to applying a saved view that can no longer be shown. The one issue's `path` is a
// PatternRefusalReason and its `message` is a plain sentence. Nothing is shown from a refused view.

/**
 * One violation, located by a dotted path into the offending payload. For a block the path is
 * relative to the block (e.g. "data.citations.0.chunkId"), not to the stream event wrapping it. For a
 * malformed request it is relative to the request body (e.g. "history.0.role"). Two sentinels exist:
 * "(block)" and "(body)" mean the problem is the whole block or body, not one field.
 */
export interface FieldIssue {
  path: string;
  message: string;
}

export interface ErrorEnvelope {
  code: ErrorCode;
  message: string;
  issues: FieldIssue[];
  retryable: boolean;
}
