"use client";

// What the search followed for your question. New in v2 (D-33): the graph signal resolves the question to concepts (the
// seeds), follows the edges that touch them one hop, and returns the passages those lead to. This shows that route.
//
// Structural precondition (constraint 7): the question resolved to at least one concept and the one-hop expansion from
// them followed at least one edge that led to a passage the signal returned. The server validator re-runs the traversal
// from the block's seeds over the stores and requires exactly this block, so every concept, edge and passage here is the
// one the search used. It shows what the SEARCH did, not what the documents state: a followed edge may be only a
// co-mention (GraphView is the view that shows what the documents say).
//
// Interaction. Select a concept (click, Enter or Space on a node) or a passage (click its row) to see, in the details
// area, the steps and passages that connect to it. Keyboard order: the concepts in the diagram (seeds first), then the
// steps list, then the passages (each row's button followed by its own source link). Lines are mouse targets only; the
// step and passage lists carry everything, so nothing depends on the picture.
// Labels, relations and quotes render as text, never as markup.

import type { Citation, GraphNode, ReachedPassage, TraversalStep, TraversalView as TraversalViewBlock } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { safeId } from "./ids";
import { columnLayout } from "./traversalLayout";

type Selection = { kind: "node"; id: string } | { kind: "passage"; rank: number } | null;

export function TraversalView({ block }: { block: TraversalViewBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Retracing the search…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="No search path to show."
          hint="The question did not match a concept in your documents, or no relation led to a passage."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The search path could not be shown." />;
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

const shorten = (label: string, max = 20) => (label.length > max ? `${label.slice(0, max - 1)}…` : label);

/** How a passage was reached, in words. */
function viaWords(via: ReachedPassage["via"], seeds: string[]): string {
  const names = seeds.join(", ");
  if (via === "mentions") return `mentions ${names}`;
  if (via === "edge") return `an edge from ${names} was found in it`;
  return `mentions a concept next to ${names}`;
}

function Body({ block }: { block: TraversalViewBlock }) {
  const { seeds, nodes, steps, reached, citations, stepsLeftOut } = block.data;
  const [selection, setSelection] = useState<Selection>(null);

  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const citationById = new Map(citations.map((c) => [c.id, c]));
  const label = (id: string) => nodeById.get(id)?.label ?? id;
  const seedIds = seeds.map((s) => s.nodeId);
  const seedSet = new Set(seedIds);
  const matchOf = new Map(seeds.map((s) => [s.nodeId, s.match]));
  const otherIds = nodes.map((n) => n.id).filter((id) => !seedSet.has(id));
  const layout = columnLayout(seedIds, otherIds);
  const position = new Map(layout.nodes.map((p) => [p.id, p]));
  const anchor = (citationId: string) => `${safeId(block.id)}-${safeId(citationId)}`;
  const arrow = `${safeId(block.id)}-arrow`;

  // A selection whose target is no longer in the block (the block was replaced) is simply no selection.
  const active: Selection =
    selection?.kind === "node" && nodeById.has(selection.id)
      ? selection
      : selection?.kind === "passage" && reached.some((r) => r.rank === selection.rank)
        ? selection
        : null;

  const passageOf = (rank: number) => reached.find((r) => r.rank === rank);
  const stepOn = (step: TraversalStep) =>
    active?.kind === "node"
      ? step.source === active.id || step.target === active.id
      : active?.kind === "passage"
        ? step.citationId === passageOf(active.rank)?.citationId
        : false;
  const passageOn = (passage: ReachedPassage) =>
    active?.kind === "passage"
      ? passage.rank === active.rank
      : active?.kind === "node"
        ? passage.seedIds.includes(active.id) || steps.some((s) => s.citationId === passage.citationId && stepOn(s))
        : false;
  const nodeOn = (id: string) =>
    active?.kind === "node"
      ? active.id === id || steps.some((s) => stepOn(s) && (s.source === id || s.target === id))
      : active?.kind === "passage"
        ? (passageOf(active.rank)?.seedIds.includes(id) ?? false) ||
          steps.some((s) => stepOn(s) && (s.source === id || s.target === id))
        : false;
  const degree = (id: string) => steps.filter((s) => s.source === id || s.target === id).length;
  const toggleNode = (id: string) =>
    setSelection((cur) => (cur?.kind === "node" && cur.id === id ? null : { kind: "node", id }));
  const togglePassage = (rank: number) =>
    setSelection((cur) => (cur?.kind === "passage" && cur.rank === rank ? null : { kind: "passage", rank }));

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        What the search followed for your question: the concepts it found, the relations it followed from them, and the
        passages those led to. This is the route the search took, not what your documents state.
      </p>

      <svg
        role="group"
        aria-label={`Search path of ${nodes.length} concepts and ${steps.length} steps`}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="h-auto w-full max-w-full"
      >
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#78716c" />
          </marker>
        </defs>

        <g aria-hidden="true">
          {steps.map((step, index) => {
            const from = position.get(step.source);
            const to = position.get(step.target);
            if (!from || !to) return null;
            const on = stepOn(step);
            const r = layout.nodeRadius;
            const sameColumn = from.column === to.column;
            const bend = sameColumn ? (from.column === "left" ? -50 : 50) : 0;
            const midX = (from.x + to.x) / 2 + bend;
            const midY = (from.y + to.y) / 2;
            const dx = to.x - (sameColumn ? midX : from.x);
            const dy = to.y - (sameColumn ? midY : from.y);
            const len = Math.hypot(dx, dy) || 1;
            const endX = to.x - (dx / len) * (r + 2);
            const endY = to.y - (dy / len) * (r + 2);
            const path = sameColumn
              ? `M ${from.x} ${from.y} Q ${midX} ${midY} ${endX} ${endY}`
              : `M ${from.x + (dx / len) * r} ${from.y + (dy / len) * r} L ${endX} ${endY}`;
            return (
              <path
                key={index}
                d={path}
                fill="none"
                stroke={on ? "#047857" : "#a8a29e"}
                strokeWidth={on ? 2.5 : 1.25}
                markerEnd={`url(#${arrow})`}
                opacity={active && !on ? 0.3 : 1}
              />
            );
          })}
        </g>

        {layout.nodes.map((place) => {
          const node = nodeById.get(place.id);
          if (!node) return null;
          const selected = active?.kind === "node" && active.id === node.id;
          const lit = selected || nodeOn(node.id);
          const isSeed = seedSet.has(node.id);
          const side = place.column === "left" ? "end" : "start";
          const dx = side === "end" ? -(layout.nodeRadius + 6) : layout.nodeRadius + 6;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${node.label}, ${isSeed ? `a concept from your question (${matchOf.get(node.id) === "exact" ? "exact match" : "partial match"})` : "reached by a relation"}, ${degree(node.id)} ${degree(node.id) === 1 ? "step" : "steps"}`}
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
                className={lit ? "fill-emerald-600" : isSeed ? "fill-amber-100" : "fill-stone-100"}
                stroke={selected ? "#047857" : isSeed ? "#b45309" : "#78716c"}
                strokeWidth={selected ? 3 : 1.5}
                strokeDasharray={isSeed && matchOf.get(node.id) === "approximate" ? "3 2" : undefined}
              />
              <text x={place.x + dx} y={place.y + 4} textAnchor={side} className="fill-stone-800 text-[11px]">
                {shorten(node.label)}
              </text>
            </g>
          );
        })}
      </svg>

      <section aria-label="Steps">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Steps followed ({steps.length})</h3>
        <ul className="space-y-1 text-sm">
          {steps.map((step, index) => (
            <li key={index} className={`rounded px-1 ${stepOn(step) ? "bg-emerald-50 font-medium" : ""}`}>
              {label(step.source)} <span className="text-stone-500">{step.relation.replaceAll("_", " ")}</span>{" "}
              {label(step.target)}{" "}
              <a
                href={`#${anchor(step.citationId)}`}
                aria-label={`Passage ${step.citationId} this relation was found in`}
                className="inline-block rounded bg-emerald-100 px-1.5 text-xs font-medium text-emerald-800 no-underline hover:bg-emerald-200"
              >
                {step.citationId}
              </a>
            </li>
          ))}
        </ul>
        {stepsLeftOut > 0 && (
          <p className="mt-2 text-xs text-stone-500">
            {stepsLeftOut} other {stepsLeftOut === 1 ? "relation" : "relations"} followed from these concepts led to passages the
            search did not return, and {stepsLeftOut === 1 ? "is" : "are"} not shown.
          </p>
        )}
      </section>

      <section aria-label="Passages reached">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Passages reached ({reached.length})</h3>
        <ol className="space-y-2 text-sm">
          {reached.map((passage) => {
            const citation = citationById.get(passage.citationId);
            return (
              <li key={passage.rank} id={anchor(passage.citationId)} className="flex gap-2">
                <span className="shrink-0 pt-0.5 font-mono text-xs text-stone-500">{passage.rank}.</span>
                <div className="min-w-0">
                  <button
                    type="button"
                    aria-pressed={active?.kind === "passage" && active.rank === passage.rank}
                    onClick={() => togglePassage(passage.rank)}
                    className={`rounded px-1 text-left hover:bg-stone-100 ${passageOn(passage) ? "bg-emerald-50 font-medium" : ""}`}
                  >
                    {citation ? citation.docTitle : "A passage"}
                    {citation?.page != null && <span className="text-stone-500"> · page {citation.page}</span>}
                  </button>
                  <div className="px-1 text-xs text-stone-500">{viaWords(passage.via, passage.seedIds.map(label))}</div>
                  {citation && (
                    <blockquote className="mt-0.5 border-l-2 border-stone-300 pl-2 text-stone-600">{citation.quote}</blockquote>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-label="Details" aria-live="polite" className="rounded border border-stone-200 bg-stone-50 p-3 text-sm">
        {active === null ? (
          <p className="text-stone-500">Select a concept or a passage to see how they connect.</p>
        ) : (
          <Details
            active={active}
            steps={steps}
            reached={reached}
            stepOn={stepOn}
            passageOn={passageOn}
            nodes={nodeById}
            citations={citationById}
            title={active.kind === "node" ? label(active.id) : `Passage ${active.rank}`}
          />
        )}
      </section>
    </div>
  );
}

function Details({
  active,
  steps,
  reached,
  stepOn,
  passageOn,
  nodes,
  citations,
  title,
}: {
  active: NonNullable<Selection>;
  steps: TraversalStep[];
  reached: ReachedPassage[];
  stepOn: (step: TraversalStep) => boolean;
  passageOn: (passage: ReachedPassage) => boolean;
  nodes: Map<string, GraphNode>;
  citations: Map<string, Citation>;
  title: string;
}) {
  const name = (id: string) => nodes.get(id)?.label ?? id;
  const onSteps = steps.filter(stepOn);
  const onPassages = reached.filter(passageOn);
  return (
    <>
      <h3 className="mb-2 font-medium text-stone-800">{title}</h3>
      <p className="mb-1 text-xs text-stone-500">
        {onSteps.length} {onSteps.length === 1 ? "step" : "steps"} and {onPassages.length}{" "}
        {onPassages.length === 1 ? "passage" : "passages"} connect {active.kind === "node" ? "to this concept" : "to this passage"}.
      </p>
      <ul className="space-y-1">
        {onSteps.map((step, index) => (
          <li key={index}>
            {name(step.source)} <span className="text-stone-500">{step.relation.replaceAll("_", " ")}</span> {name(step.target)}
          </li>
        ))}
      </ul>
      {onPassages.length > 0 && (
        <ul className="mt-2 space-y-2">
          {onPassages.map((passage) => (
            <li key={passage.rank}>
              <span className="font-mono text-xs text-stone-500">{passage.rank}.</span> {citations.get(passage.citationId)?.docTitle}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
