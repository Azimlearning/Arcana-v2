// The shared state frames every block component uses: loading, empty, partial and error.
// A component renders its own content for "ready"; these cover everything else, so no block can
// show a blank panel.

import type { ErrorEnvelope } from "@arcana/schema";
import type { ReactNode } from "react";

export function Frame({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "error" }) {
  const border = tone === "error" ? "border-red-300 bg-red-50" : "border-stone-200 bg-white";
  return <div className={`rounded-lg border p-5 shadow-sm ${border}`}>{children}</div>;
}

export function LoadingState({ caption, rows = 3 }: { caption: string; rows?: number }) {
  return (
    <Frame>
      <div role="status" aria-busy="true" aria-live="polite">
        <p className="mb-3 text-sm text-stone-500">{caption}</p>
        <div className="space-y-2" aria-hidden="true">
          {Array.from({ length: rows }, (_, i) => (
            <div
              key={i}
              className="h-3 animate-pulse rounded bg-stone-200"
              style={{ width: `${95 - i * 12}%` }}
            />
          ))}
        </div>
      </div>
    </Frame>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <Frame>
      <div role="status">
        <p className="font-medium text-stone-700">{title}</p>
        {hint && <p className="mt-1 text-sm text-stone-500">{hint}</p>}
      </div>
    </Frame>
  );
}

/** Content that is still arriving: shown, with a note that it is not final. */
export function PartialState({ children }: { children: ReactNode }) {
  return (
    <Frame>
      {children}
      <p role="status" className="mt-3 text-xs text-stone-500">
        Still working. This answer is not final.
      </p>
    </Frame>
  );
}

/** Shows why a block failed: the message, and the field paths when the server rejected the content. */
export function ErrorState({ error, fallback }: { error: ErrorEnvelope | null; fallback: string }) {
  return (
    <Frame tone="error">
      <div role="alert">
        <p className="font-medium text-red-800">{error?.message ?? fallback}</p>
        {error && error.issues.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-red-700">
            {error.issues.map((issue) => (
              <li key={`${issue.path}:${issue.message}`}>
                <span className="font-mono">{issue.path}</span>: {issue.message}
              </li>
            ))}
          </ul>
        )}
        {error?.retryable && <p className="mt-2 text-xs text-red-700">You can try again.</p>}
      </div>
    </Frame>
  );
}
