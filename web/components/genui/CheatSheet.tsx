"use client";

// A one-page cheat sheet for a concept and its neighbours (D-43, V4). New in v2; the Studio's counterpart of VERA AI's "Visual"
// function, with no image model: the picture is a small diagram drawn here from the block's own entries and edges, and the same entries
// are listed beside it as the text alternative.
//
// Structural precondition (constraint 7): the vault holds the focus page and a stored sentence for it or for a page linked to it. The
// server validator derives the sheet again and requires exactly this block, so nothing here chooses, ranks or invents a concept or a
// link. Every sentence is cited and rendered as text, never as markup.

import type { CheatSheet as CheatSheetBlock, SheetEntry } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { PageName } from "./notesNav";

export function CheatSheet({ block }: { block: CheatSheetBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Making the sheet…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No sheet could be made."
          hint={
            block.data.skipped > 0
              ? `${block.data.skipped} ${block.data.skipped === 1 ? "concept was" : "concepts were"} looked at, and none had a stored sentence to show.`
              : "The notes hold no definition or claim for this concept yet."
          }
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The sheet could not be shown." />;
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

/** The sheet as Markdown, from the block's own text: nothing is added. */
export function sheetMarkdown(data: CheatSheetBlock["data"]): string {
  const quote = new Map(data.citations.map((c) => [c.id, c.quote]));
  const label = new Map(data.entries.map((e) => [e.pageId, e.pageLabel]));
  const lines: string[] = [`# Cheat sheet: ${label.get(data.focusId ?? "") ?? data.entries[0]?.pageLabel ?? ""}`, ""];
  for (const e of data.entries) lines.push(`- **${e.pageLabel}**${e.kind ? ` (${e.kind})` : ""}: ${quote.get(e.citationId) ?? ""}`);
  if (data.edges.length > 0) {
    lines.push("", "## Connections", "");
    for (const edge of data.edges) {
      lines.push(`- ${label.get(edge.src) ?? edge.src} ${edge.relation ? `${edge.relation} ` : "appears with "}${label.get(edge.dst) ?? edge.dst}`);
    }
  }
  return lines.join("\n") + "\n";
}

const W = 360;
const H = 260;

/** Where each entry sits: the focus in the middle, the others evenly round it. A pure function of the entries, so it never moves. */
export function layout(entries: SheetEntry[], focusId: string | null): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  const centre = entries.find((e) => e.pageId === focusId) ?? entries[0];
  if (centre) out.set(centre.pageId, { x: W / 2, y: H / 2 });
  const others = entries.filter((e) => e.pageId !== centre?.pageId);
  others.forEach((e, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    out.set(e.pageId, { x: W / 2 + (W / 2 - 70) * Math.cos(angle), y: H / 2 + (H / 2 - 28) * Math.sin(angle) });
  });
  return out;
}

function Diagram({ data }: { data: CheatSheetBlock["data"] }) {
  const at = layout(data.entries, data.focusId);
  return (
    <svg role="img" aria-label="Concept diagram" viewBox={`0 0 ${W} ${H}`} className="w-full max-w-md">
      <title>
        {data.entries.length} concepts and {data.edges.length} connections; the lists beside this diagram say the same in words.
      </title>
      {data.edges.map((edge, i) => {
        const a = at.get(edge.src);
        const b = at.get(edge.dst);
        if (!a || !b) return null;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="currentColor"
            className={edge.relation ? "text-emerald-600" : "text-stone-300"}
            strokeWidth={edge.relation ? 2 : 1}
            strokeDasharray={edge.relation ? undefined : "4 3"}
          />
        );
      })}
      {data.entries.map((e) => {
        const p = at.get(e.pageId);
        if (!p) return null;
        const focus = e.pageId === data.focusId;
        const text = e.pageLabel.length > 22 ? `${e.pageLabel.slice(0, 21)}…` : e.pageLabel;
        return (
          <g key={e.pageId} transform={`translate(${p.x}, ${p.y})`}>
            <rect
              x={-62}
              y={-13}
              width={124}
              height={26}
              rx={6}
              className={focus ? "fill-emerald-100 stroke-emerald-700" : "fill-white stroke-stone-400"}
              strokeWidth={focus ? 2 : 1}
            />
            <text textAnchor="middle" dominantBaseline="central" className="fill-stone-900 text-[10px]">
              {text}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Body({ block }: { block: CheatSheetBlock }) {
  const { focusId, entries, edges, citations, skipped } = block.data;
  const byId = new Map(citations.map((c) => [c.id, c]));
  const labelOf = new Map(entries.map((e) => [e.pageId, e.pageLabel]));
  const [copied, setCopied] = useState(false);
  const title = labelOf.get(focusId ?? "") ?? entries[0]?.pageLabel ?? "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sheetMarkdown(block.data));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // a blocked clipboard is not worth a dialog: the text is on screen to select
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Cheat sheet</p>
          <h2 className="font-serif text-xl font-semibold text-stone-900">{title}</h2>
        </div>
        <div className="flex gap-1 print:hidden">
          <button type="button" onClick={copy} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
            {copied ? "Copied" : "Copy as Markdown"}
          </button>
          <button type="button" onClick={() => window.print()} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
            Print
          </button>
        </div>
      </div>

      <Diagram data={block.data} />

      <section aria-label="Concepts">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Concepts</h3>
        <ul className="grid gap-3 sm:grid-cols-2">
          {entries.map((e) => {
            const citation = byId.get(e.citationId);
            if (!citation) return null; // the server guarantees it exists; never render a dead entry
            return (
              <li key={e.pageId} className="rounded-md border border-stone-200 p-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-stone-900">
                    <PageName id={e.pageId} label={e.pageLabel} current={e.pageId === focusId} />
                  </span>
                  {e.kind && <span className="text-xs text-stone-500">{e.kind}</span>}
                </div>
                <blockquote className="mt-1 border-l-2 border-emerald-300 pl-2 text-sm text-stone-800">{citation.quote}</blockquote>
                <span className="text-xs text-stone-500">
                  {citation.docTitle}
                  {citation.page != null && ` · page ${citation.page}`}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label="Connections">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Connections</h3>
        {edges.length === 0 ? (
          <p className="text-sm text-stone-600">No two of these concepts are linked in the notes.</p>
        ) : (
          <ul className="space-y-1 text-sm text-stone-800">
            {edges.map((edge, i) => (
              <li key={i}>
                {labelOf.get(edge.src) ?? edge.src} {edge.relation ? <em>{edge.relation}</em> : <span className="text-stone-500">appears with</span>}{" "}
                {labelOf.get(edge.dst) ?? edge.dst}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-stone-500">
        {skipped > 0 ? `${skipped} linked ${skipped === 1 ? "concept" : "concepts"} had no stored sentence and ${skipped === 1 ? "is" : "are"} not shown. ` : ""}
        Every sentence is from your documents. A solid line is a relation a source states; a dashed one means the two appear in a sentence
        together.
      </p>
    </div>
  );
}
