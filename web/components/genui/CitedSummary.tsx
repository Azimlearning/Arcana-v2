// Adapted from Azimlearning/Arcana (v1), web/components/genui/CitedSummary.tsx @ 9a3d67f. Read in
// full. Kept: the segment-with-citation-pills layout and the Sources list. Rewritten for v2: the five
// wire statuses (empty, loading, partial, ready, error), the error reason from meta.error (v1 reused
// the summary text), and no "answer may be ungrounded" fallback: the server refuses to send a ready
// block without citations, so the client never has to guess.
//
// Structural precondition (constraint 7): a CitedSummary needs retrieved evidence that supports every
// segment, resolvable to a stored chunk. Retrieval satisfies it; the server validator enforces it.

import type { CitedSummary as CitedSummaryBlock } from "@arcana/schema";

import { EmptyState, ErrorState, LoadingState, PartialState, Frame } from "./BlockStates";

export function CitedSummary({ block }: { block: CitedSummaryBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Searching your documents…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No evidence found in your documents."
          hint="Upload a PDF that covers this topic, or ask about something it contains."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="This answer could not be produced." />;
    case "partial":
      return (
        <PartialState>
          <Body block={block} />
        </PartialState>
      );
    case "ready":
      return (
        <Frame>
          <Body block={block} />
        </Frame>
      );
  }
}

function Body({ block }: { block: CitedSummaryBlock }) {
  const { segments, citations } = block.data;
  const byId = new Map(citations.map((c) => [c.id, c]));
  const anchor = (citationId: string) => `${block.id}-${citationId}`;

  return (
    <div className="space-y-4">
      <p className="font-serif text-base leading-relaxed text-stone-900">
        {segments.map((segment, i) => (
          <span key={i}>
            {segment.text}{" "}
            {segment.citationIds.map((id) => {
              const citation = byId.get(id);
              if (!citation) return null; // the server guarantees it exists; never render a dead pill
              const where = citation.page != null ? `, page ${citation.page}` : "";
              return (
                <a
                  key={id}
                  href={`#${anchor(id)}`}
                  title={citation.quote}
                  aria-label={`Source ${id}: ${citation.docTitle}${where}`}
                  className="mr-1 inline-block rounded bg-emerald-100 px-1.5 text-xs font-medium text-emerald-800 no-underline hover:bg-emerald-200"
                >
                  {id}
                </a>
              );
            })}
          </span>
        ))}
      </p>

      {citations.length > 0 && (
        <section className="border-t border-stone-200 pt-3" aria-label="Sources">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Sources</h3>
          <ul className="space-y-3 text-sm">
            {citations.map((citation) => (
              <li key={citation.id} id={anchor(citation.id)} className="flex gap-2">
                <span className="shrink-0 pt-0.5 font-mono text-xs text-emerald-700">[{citation.id}]</span>
                <div>
                  <div className="text-stone-900">
                    {citation.docTitle}
                    {citation.page != null && (
                      <span className="text-stone-500"> · page {citation.page}</span>
                    )}
                  </div>
                  <blockquote className="mt-0.5 border-l-2 border-stone-300 pl-2 text-stone-600">
                    {citation.quote}
                  </blockquote>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
