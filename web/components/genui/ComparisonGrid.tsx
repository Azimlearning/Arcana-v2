"use client";

// Documents side by side on the entities they all discuss. New in v2 (no v1 counterpart).
//
// Structural precondition (constraint 7): at least two documents and two entities remain after alignment, and
// every entity shown is evidenced in two or more of the documents by a verbatim quote that names it. Only the
// graph can supply this; flat retrieval returns passages, not shared entities. The server validator re-checks
// every cell: its quote is from that row's own document and contains the column's label.
//
// A cell holds a quote and a source link. Where a document has no evidence for an entity the cell is marked in
// words ("No evidence in this paper"), never left blank and never filled with a guess. Document titles, labels and
// quotes render as text, never as markup. The table has row and column headers; long quotes are shortened and can
// be expanded, and the full quotes are always in the Sources list that the links point to.

import type { ComparisonGrid as ComparisonGridBlock } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { safeId } from "./ids";

const PREVIEW_CHARS = 110;

export function ComparisonGrid({ block }: { block: ComparisonGridBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Lining up your documents…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="Nothing to compare."
          hint="The documents do not share enough concepts for a side-by-side view."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The comparison could not be built." />;
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

function Body({ block }: { block: ComparisonGridBlock }) {
  const { dimensions, rows, citations } = block.data;
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const citationById = new Map(citations.map((c) => [c.id, c]));
  const anchor = (citationId: string) => `${safeId(block.id)}-${safeId(citationId)}`;
  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto" role="region" aria-label="Comparison table" tabIndex={0}>
        <table
          className="w-full break-normal border-collapse text-left text-sm"
          // Each column keeps room to read (about 9rem) and the table scrolls sideways instead of squeezing: with seven or
          // eight columns in a narrow panel, squeezed columns were a few characters wide (seen on real data, task D1).
          style={{ minWidth: `${9 + 9 * dimensions.length}rem` }}
        >
          <caption className="sr-only">
            {`Comparison of ${rows.length} documents on ${dimensions.length} shared concepts`}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="border-b border-stone-300 p-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                Document
              </th>
              {dimensions.map((dimension) => (
                <th
                  key={dimension.id}
                  scope="col"
                  className="border-b border-stone-300 p-2 align-bottom font-medium text-stone-800"
                >
                  {dimension.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.docId} className="align-top">
                <th scope="row" className="border-b border-stone-200 p-2 font-medium text-stone-900 [overflow-wrap:anywhere]">
                  {row.docTitle}
                </th>
                {dimensions.map((dimension) => {
                  const cell = row.cells.find((c) => c.dimensionId === dimension.id);
                  const citation = cell ? citationById.get(cell.citationId) : undefined;
                  const key = `${row.docId}:${dimension.id}`;
                  return (
                    <td key={dimension.id} className="border-b border-stone-200 p-2">
                      {citation ? (
                        <Quote
                          text={citation.quote}
                          expanded={open.has(key)}
                          onToggle={() => toggle(key)}
                          label={`${row.docTitle}, ${dimension.label}`}
                          href={`#${anchor(citation.id)}`}
                          source={citation.page != null ? `page ${citation.page}` : "source"}
                          sourceLabel={`Source ${citation.id}: ${citation.docTitle}${citation.page != null ? `, page ${citation.page}` : ""}`}
                        />
                      ) : cell ? (
                        // The server guarantees a cell's citation exists; if it ever does not, say so plainly
                        // rather than claim the paper has no evidence.
                        <span role="alert" className="text-red-700">
                          Evidence for this cell is unavailable.
                        </span>
                      ) : (
                        <span className="text-stone-500 italic">No evidence in this paper</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section aria-label="Sources" className="border-t border-stone-200 pt-3">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Sources</h3>
        <ul className="space-y-3 text-sm">
          {citations.map((citation) => (
            <li key={citation.id} id={anchor(citation.id)} className="flex gap-2">
              <span className="shrink-0 pt-0.5 font-mono text-xs text-emerald-700">[{citation.id}]</span>
              <div>
                <div className="text-stone-900">
                  {citation.docTitle}
                  {citation.page != null && <span className="text-stone-500"> · page {citation.page}</span>}
                </div>
                <blockquote className="mt-0.5 border-l-2 border-stone-300 pl-2 text-stone-600">{citation.quote}</blockquote>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Quote({
  text,
  expanded,
  onToggle,
  label,
  href,
  source,
  sourceLabel,
}: {
  text: string;
  expanded: boolean;
  onToggle: () => void;
  label: string;
  href: string;
  source: string;
  sourceLabel: string;
}) {
  const long = text.length > PREVIEW_CHARS;
  const shown = long && !expanded ? `${Array.from(text).slice(0, PREVIEW_CHARS).join("").trimEnd()}…` : text;
  return (
    <div>
      <p className="text-stone-700">{shown}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
        {long && (
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={`${expanded ? "Show less" : "Show more"}: ${label}`}
            onClick={onToggle}
            className="text-emerald-700 underline"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
        <a href={href} aria-label={sourceLabel} className="text-emerald-700 underline">
          {source}
        </a>
      </div>
    </div>
  );
}
