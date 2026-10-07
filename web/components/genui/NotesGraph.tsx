"use client";

// The vault's graph: pages and the links among them, local to one page or across the whole vault. New in v2 (D-35).
//
// Structural precondition (constraint 7): the vault holds at least one page that matches the query (or the focus page). The server
// validator derives the graph again from the vault and requires exactly this block. A solid line is a relation the documents state
// (a model found it and the builder checked it against a sentence); a dashed line only says two names occur in one sentence.
//
// Interaction. A page is a button (in the diagram and in the list below it): it opens that page when the screen can (`useNotesNav`),
// otherwise it only highlights. The list under the diagram carries every page and its numbers, so nothing depends on the picture.
// Keyboard order: the pages in the diagram, then the list. Names render as text, never as markup.

import type { NotesEdge, NotesGraph as NotesGraphBlock, NotesNode } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { safeId } from "./ids";
import { BAND_FILL, BAND_SWATCH, BAND_WORDS, band } from "./mastery";
import { useNotesNav } from "./notesNav";
import { ringLayout } from "./notesLayout";

export function NotesGraph({ block }: { block: NotesGraphBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Drawing the pages…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title={block.data.query ? `No page matches “${block.data.query}”.` : "There are no pages yet."}
          hint={
            block.data.query
              ? "Try another word, or clear the search."
              : "Pages appear once documents have been read and their notes compiled."
          }
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The pages could not be shown." />;
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

const shorten = (label: string, max = 22) => (label.length > max ? `${label.slice(0, max - 1)}…` : label);

function Body({ block }: { block: NotesGraphBlock }) {
  const { focusId, query, nodes, edges, nodesLeftOut } = block.data;
  const nav = useNotesNav();
  const [picked, setPicked] = useState<string | null>(null);
  const layout = ringLayout(focusId, nodes.map((n) => n.id));
  const where = new Map(layout.pages.map((p) => [p.id, p]));
  const byId = new Map<string, NotesNode>(nodes.map((n) => [n.id, n]));
  const arrow = `${safeId(block.id)}-arrow`;
  const lit = (edge: NotesEdge) => picked !== null && (edge.source === picked || edge.target === picked);
  const stated = edges.filter((e) => e.kind === "asserted").length;
  // Lines are drawn when they say something: all of a chosen page's lines, otherwise the lines the documents state and the
  // lines of the page the graph is about. Forty pages with every co-mention drawn is a hairball (seen in the real browser).
  const drawn = (edge: NotesEdge) =>
    picked !== null
      ? lit(edge)
      : edge.kind === "asserted" || (focusId !== null && (edge.source === focusId || edge.target === focusId));

  const choose = (id: string) => {
    setPicked((cur) => (cur === id ? null : id));
    if (nav && id !== focusId) nav.openPage(id);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-stone-600">
        {focusId !== null
          ? `${byId.get(focusId)?.label ?? "This page"} and the pages linked to it.`
          : query
            ? `Pages that match “${query}”, the most linked first.`
            : "The most linked pages across your documents."}{" "}
        A solid line is a relation the documents state; a dashed line only says two names occur in one sentence. Choose a page to
        see all of its lines.
      </p>

      <svg
        role="group"
        aria-label={`Page graph of ${nodes.length} pages, ${stated} stated links and ${edges.length - stated} named-together links`}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="h-auto w-full max-w-full"
      >
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#57534e" />
          </marker>
        </defs>
        <g aria-hidden="true">
          {edges.filter(drawn).map((edge, i) => {
            const from = where.get(edge.source);
            const to = where.get(edge.target);
            if (!from || !to) return null;
            const dx = to.x - from.x;
            const dy = to.y - from.y;
            const len = Math.hypot(dx, dy) || 1;
            const r = layout.nodeRadius;
            const stateds = edge.kind === "asserted";
            return (
              <line
                key={i}
                x1={from.x + (dx / len) * r}
                y1={from.y + (dy / len) * r}
                x2={to.x - (dx / len) * (r + (stateds ? 2 : 0))}
                y2={to.y - (dy / len) * (r + (stateds ? 2 : 0))}
                stroke={lit(edge) ? "#047857" : stateds ? "#57534e" : "#a8a29e"}
                strokeWidth={lit(edge) ? 2.5 : stateds ? 1.5 : 1}
                strokeDasharray={stateds ? undefined : "4 3"}
                markerEnd={stateds ? `url(#${arrow})` : undefined}
                opacity={picked !== null && !lit(edge) ? 0.25 : 1}
              />
            );
          })}
        </g>
        {nodes.map((node) => {
          const place = where.get(node.id);
          if (!place) return null;
          const isFocus = node.id === focusId;
          const on = picked === node.id;
          const dx = place.side === "start" ? layout.nodeRadius + 6 : place.side === "end" ? -(layout.nodeRadius + 6) : 0;
          const dy = place.side === "middle" ? (place.y < layout.height / 2 ? -(layout.nodeRadius + 8) : layout.nodeRadius + 16) : 4;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-pressed={on}
              aria-label={`${node.label}, in ${node.passages} ${node.passages === 1 ? "passage" : "passages"}, linked to ${node.degree} ${node.degree === 1 ? "page" : "pages"}, ${BAND_WORDS[band(node.mastery)]}${isFocus ? ", the page you are on" : ""}`}
              onClick={() => choose(node.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  choose(node.id);
                }
              }}
              className="cursor-pointer outline-none [&:focus-visible>circle]:stroke-emerald-600 [&:focus-visible>circle]:stroke-[3]"
            >
              <title>{node.label}</title>
              <circle
                cx={place.x}
                cy={place.y}
                r={isFocus ? layout.nodeRadius + 3 : layout.nodeRadius}
                className={on ? "fill-emerald-600" : BAND_FILL[band(node.mastery)]}
                stroke={isFocus ? "#047857" : "#78716c"}
                strokeWidth={isFocus ? 3 : 1.5}
              />
              {(!place.inner || on) && (
              <text
                x={place.x + dx}
                y={place.y + dy}
                textAnchor={place.side}
                className={`fill-stone-800 text-[11px] ${isFocus ? "font-semibold" : ""}`}
              >
                {shorten(node.label)}
              </text>
              )}
            </g>
          );
        })}
      </svg>

      {nodes.some((n) => n.mastery !== null) && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-600">
          <span>Colour shows what you know:</span>
          {(["comfortable", "getting-there", "needs-work", "none"] as const).map((b) => (
            <span key={b} className="inline-flex items-center gap-1">
              <span className={`inline-block h-2.5 w-2.5 rounded-full border border-stone-400 ${BAND_SWATCH[b]}`} aria-hidden="true" />
              {BAND_WORDS[b]}
            </span>
          ))}
        </p>
      )}

      <section aria-label="Pages">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Pages ({nodes.length})</h3>
        <ul className="space-y-1 text-sm">
          {nodes.map((node) => (
            <li key={node.id} className="flex flex-wrap items-baseline gap-x-2">
              <button
                type="button"
                aria-pressed={picked === node.id}
                onClick={() => choose(node.id)}
                className={`rounded px-1 text-left hover:bg-stone-100 ${node.id === focusId ? "font-semibold" : "font-medium text-emerald-800"}`}
              >
                {node.label}
              </button>
              <span className="text-xs text-stone-500">
                {node.passages} {node.passages === 1 ? "passage" : "passages"} · {node.documents}{" "}
                {node.documents === 1 ? "document" : "documents"} · {node.degree} {node.degree === 1 ? "link" : "links"}
                {node.mastery !== null && ` · ${BAND_WORDS[band(node.mastery)]}`}
              </span>
            </li>
          ))}
        </ul>
        {nodesLeftOut > 0 && (
          <p className="mt-2 text-xs text-stone-500">
            {nodesLeftOut} more {nodesLeftOut === 1 ? "page is" : "pages are"} not shown.
            {focusId === null && !query ? " Search for a concept to find it." : ""}
          </p>
        )}
      </section>
    </div>
  );
}
