"use client";

// The user's saved views (D-31): the views they kept from earlier answers, listed beside the Basic and Adaptive switch as
// their own prebuilt versions. Choosing one shows it again without asking the question again (no model is called); a view
// that can no longer be shown says why in plain words and shows nothing; any can be deleted. The list holds names and
// kinds only: a saved view carries no evidence, it is re-checked against your documents each time it is shown.

import type { ErrorEnvelope, PatternRefusalReason, SavedPattern } from "@arcana/schema";

/** What each kind of view is called to a reader. A template not listed is shown under its own name. */
const KIND_WORDS: Record<string, string> = {
  GraphView: "Connection graph",
  ComparisonGrid: "Document comparison",
  ConceptMap: "Connection path",
  SourceList: "Source list",
};

/** Why a saved view could not be shown. Typed over the reasons the server names; anything else gets a generic sentence. */
const REFUSAL_WORDS: Record<PatternRefusalReason, string> = {
  precondition_not_met: "Your documents no longer support this view.",
  template_changed: "This view was made with an older version of its layout and needs to be checked again before it can be shown.",
  document_missing: "A document this view needs is no longer in your library.",
};
const GENERIC_REFUSAL = "This saved view cannot be shown.";

/** A refusal from the server in plain words, or the server's own message for any other failure. */
export function refusalWords(error: ErrorEnvelope): string {
  if (error.code !== "pattern_refused") return error.message;
  const reason = error.issues[0]?.path ?? "";
  return (REFUSAL_WORDS as Record<string, string | undefined>)[reason] ?? GENERIC_REFUSAL;
}

export function SavedViews({
  patterns,
  busy,
  message,
  staleId = null,
  onApply,
  onDelete,
  onReverify,
}: {
  patterns: SavedPattern[];
  busy: boolean;
  /** A sentence about the last attempt (a refusal, or a failed delete), or null. */
  message: string | null;
  /** The view whose last attempt was refused because its layout moved on: it can be checked again. */
  staleId?: string | null;
  onApply: (id: string) => void;
  onDelete: (id: string) => void;
  onReverify?: (id: string) => void;
}) {
  return (
    <div className="relative">
      <details className="text-sm">
        <summary className="cursor-pointer select-none rounded-md border border-stone-300 bg-white px-3 py-1 text-stone-700 hover:bg-stone-100">
          Saved views ({patterns.length})
        </summary>
        <div className="absolute right-0 z-10 mt-1 w-80 rounded-lg border border-stone-200 bg-white p-3 shadow-lg">
          {patterns.length === 0 ? (
            <p className="text-stone-500">No saved views yet. Save one from the dashboard after an answer.</p>
          ) : (
            <ul aria-label="Saved views" className="space-y-2">
              {patterns.map((pattern) => (
                <li key={pattern.id} className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-stone-800">{pattern.name}</div>
                    <div className="text-xs text-stone-500">{KIND_WORDS[pattern.templateId] ?? pattern.templateId}</div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`Show ${pattern.name}`}
                      onClick={() => onApply(pattern.id)}
                      className="rounded border border-stone-300 px-2 py-0.5 hover:bg-stone-100 disabled:opacity-40"
                    >
                      Show
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${pattern.name}`}
                      onClick={() => onDelete(pattern.id)}
                      className="rounded border border-stone-300 px-2 py-0.5 text-red-700 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
      {message && (
        <div className="mt-1 max-w-80 text-xs">
          <p role="alert" className="text-red-700">
            {message}
          </p>
          {staleId && onReverify && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onReverify(staleId)}
              className="mt-1 rounded border border-stone-300 px-2 py-0.5 text-stone-700 hover:bg-stone-100 disabled:opacity-40"
            >
              Check this view again
            </button>
          )}
        </div>
      )}
    </div>
  );
}
