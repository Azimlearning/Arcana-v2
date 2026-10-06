"use client";

// A node-link diagram of what the documents say connects. New in v2: v1's graph output was a static list that
// never worked (D-29), so this one is interactive and drawn from real, grounded data.
//
// Structural precondition (constraint 7): the Graph agent returned at least one edge whose stored chunk holds a
// verbatim quote naming both endpoints. The server validator re-checks every edge against the store, so every
// connection shown here cites a stored passage that names both concepts. That is co-mention, not proof of the
// relation word: the relation and its direction come from the extractor, and the quote is there for the reader
// to judge them.
//
// Interaction. Select a concept (click, Enter or Space on a node) or a relation (click its row in the list, or
// the line in the diagram) to see, in the details area below, each relation involved with its quote and a link to
// the source. Keyboard order: the concepts in the diagram in the order given, then the relations list (each row's
// button followed by its own source link), then the links in the details area. Lines in the diagram are mouse
// targets only; the list is the keyboard route to a relation, and it carries every relation, so nothing depends
// on the picture.
// Labels, relations and quotes render as text, never as markup.

import type { Citation, GraphEdge, GraphNode, GraphView as GraphViewBlock } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { radialLayout } from "./graphLayout";
import { safeId } from "./ids";

type Selection = { kind: "node"; id: string } | { kind: "edge"; index: number } | null;

export function GraphView({ block }: { block: GraphViewBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Tracing connections…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="No connections found."
          hint="Your documents do not state a relationship between these concepts."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The graph could not be drawn." />;
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

const shorten = (label: string, max = 18) => (label.length > max ? `${label.slice(0, max - 1)}…` : label);

function Body({ block }: { block: GraphViewBlock }) {
  const { nodes, edges, citations } = block.data;
  const [selection, setSelection] = useState<Selection>(null);

  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const citationById = new Map(citations.map((c) => [c.id, c]));
  const layout = radialLayout(nodes.map((n) => n.id));
  const position = new Map(layout.nodes.map((p) => [p.id, p]));
  const anchor = (citationId: string) => `${safeId(block.id)}-${safeId(citationId)}`;
  const label = (id: string) => nodeById.get(id)?.label ?? id;

  // A selection whose target is no longer in the block (the block was replaced) is simply no selection.
  const active: Selection =
    selection?.kind === "node" && nodeById.has(selection.id)
      ? selection
      : selection?.kind === "edge" && selection.index < edges.length
        ? selection
        : null;

  const incident = (index: number) =>
    active?.kind === "node"
      ? edges[index]!.source === active.id || edges[index]!.target === active.id
      : active?.kind === "edge"
        ? active.index === index
        : false;
  const shown = edges.map((edge, index) => ({ edge, index })).filter(({ index }) => incident(index));
  const degree = (id: string) => edges.filter((e) => e.source === id || e.target === id).length;
  const toggleNode = (id: string) =>
    setSelection((current) => (current?.kind === "node" && current.id === id ? null : { kind: "node", id }));
  const toggleEdge = (index: number) =>
    setSelection((current) => (current?.kind === "edge" && current.index === index ? null : { kind: "edge", index }));
  const arrow = `${safeId(block.id)}-arrow`;

  return (
    <div className="space-y-4">
      <svg
        role="group"
        aria-label={`Graph of ${nodes.length} concepts and ${edges.length} relations`}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="h-auto w-full max-w-full"
      >
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#78716c" />
          </marker>
        </defs>

        <g aria-hidden="true">
          {edges.map((edge, index) => {
            const from = position.get(edge.source);
            const to = position.get(edge.target);
            if (!from || !to) return null;
            const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
            const ux = (to.x - from.x) / length;
            const uy = (to.y - from.y) / length;
            const r = layout.nodeRadius;
            const on = incident(index);
            return (
              <g key={index} onClick={() => toggleEdge(index)} className="cursor-pointer">
                <line
                  x1={from.x + ux * r}
                  y1={from.y + uy * r}
                  x2={to.x - ux * (r + 2)}
                  y2={to.y - uy * (r + 2)}
                  stroke={on ? "#047857" : "#a8a29e"}
                  strokeWidth={on ? 2.5 : 1.25}
                  markerEnd={`url(#${arrow})`}
                  opacity={active && !on ? 0.35 : 1}
                />
                {/* a wide invisible line makes a thin edge easy to hit */}
                <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="transparent" strokeWidth={10} />
                {on && (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 4}
                    textAnchor="middle"
                    className="fill-emerald-800 text-[11px] font-medium"
                    paintOrder="stroke"
                    stroke="white"
                    strokeWidth={3}
                  >
                    {edge.relation}
                  </text>
                )}
              </g>
            );
          })}
        </g>

        {nodes.map((node) => {
          const place = position.get(node.id);
          if (!place) return null;
          const selected = active?.kind === "node" && active.id === node.id;
          const related =
            active?.kind === "edge" && (edges[active.index]!.source === node.id || edges[active.index]!.target === node.id);
          const side = place.x < layout.width / 2 - 4 ? "end" : place.x > layout.width / 2 + 4 ? "start" : "middle";
          const dx = side === "end" ? -(layout.nodeRadius + 5) : side === "start" ? layout.nodeRadius + 5 : 0;
          const dy = side === "middle" ? (place.y < layout.height / 2 ? -(layout.nodeRadius + 6) : layout.nodeRadius + 14) : 4;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${node.label}, ${degree(node.id)} ${degree(node.id) === 1 ? "relation" : "relations"}`}
              onClick={() => toggleNode(node.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  toggleNode(node.id);
                }
              }}
              className="cursor-pointer outline-none [&:focus-visible>circle]:stroke-emerald-600 [&:focus-visible>circle]:stroke-[3]"
            >
              <title>{node.label}</title>
              <circle
                cx={place.x}
                cy={place.y}
                r={layout.nodeRadius}
                className={selected || related ? "fill-emerald-600" : "fill-stone-100"}
                stroke={selected ? "#047857" : "#78716c"}
                strokeWidth={selected ? 3 : 1.5}
              />
              <text x={place.x + dx} y={place.y + dy} textAnchor={side} className="fill-stone-800 text-[11px]">
                {shorten(node.label)}
              </text>
            </g>
          );
        })}
      </svg>

      <section aria-label="Relations">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Relations ({edges.length})</h3>
        <ul className="space-y-1 text-sm">
          {edges.map((edge, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-2">
              <button
                type="button"
                aria-pressed={active?.kind === "edge" && active.index === index}
                onClick={() => toggleEdge(index)}
                className={`rounded px-1 text-left hover:bg-stone-100 ${incident(index) ? "bg-emerald-50 font-medium" : ""}`}
              >
                {label(edge.source)} <span className="text-stone-500">{edge.relation}</span> {label(edge.target)}
              </button>
              <a
                href={`#${anchor(edge.citationId)}`}
                aria-label={`Source ${edge.citationId} for ${label(edge.source)} ${edge.relation} ${label(edge.target)}`}
                className="inline-block rounded bg-emerald-100 px-1.5 text-xs font-medium text-emerald-800 no-underline hover:bg-emerald-200"
              >
                {edge.citationId}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Details" aria-live="polite" className="rounded border border-stone-200 bg-stone-50 p-3 text-sm">
        {active === null ? (
          <p className="text-stone-500">Select a concept or a relation to see the words that support it.</p>
        ) : (
          <>
            <h3 className="mb-2 font-medium text-stone-800">
              {active.kind === "node" ? label(active.id) : "Selected relation"}
            </h3>
            <ul className="space-y-3">
              {shown.map(({ edge, index }) => (
                <Evidence key={index} edge={edge} nodes={nodeById} citation={citationById.get(edge.citationId)} anchor={anchor} />
              ))}
            </ul>
          </>
        )}
      </section>

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

function Evidence({
  edge,
  nodes,
  citation,
  anchor,
}: {
  edge: GraphEdge;
  nodes: Map<string, GraphNode>;
  citation: Citation | undefined;
  anchor: (citationId: string) => string;
}) {
  const name = (id: string) => nodes.get(id)?.label ?? id;
  return (
    <li>
      <div className="font-medium text-stone-900">
        {name(edge.source)} <span className="font-normal text-stone-500">{edge.relation}</span> {name(edge.target)}
      </div>
      {citation && (
        <>
          <blockquote className="mt-0.5 border-l-2 border-stone-300 pl-2 text-stone-600">{citation.quote}</blockquote>
          <a href={`#${anchor(citation.id)}`} className="text-xs text-emerald-700 underline">
            {citation.docTitle}
            {citation.page != null ? `, page ${citation.page}` : ""}
          </a>
        </>
      )}
    </li>
  );
}
