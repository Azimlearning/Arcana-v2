// How two concepts connect through the documents, as a chain of grounded steps. New in v2 (no v1 counterpart).
//
// Structural precondition (constraint 7): the Graph agent found a path of two to six hops between two entities,
// every hop backed by a verbatim quote that names both of its concepts, and no concept repeats. A single hop is a
// GraphView case. The server validator re-checks every step against the store.
//
// The ordered list is the whole component: it is the accessible form and needs no picture. Each step shows the
// path order (concept, then the next concept) and, beneath it, the claim in the direction the document states it:
// when `reversed` is set the stored relation runs against the path, and the claim is written that way round so the
// map never says a relation the wrong way. Labels, relations and quotes render as text, never as markup.

import type { ConceptMap as ConceptMapBlock, PathStep } from "@arcana/schema";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { safeId } from "./ids";

export function ConceptMap({ block }: { block: ConceptMapBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Following the connection…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="No connection found."
          hint="Your documents do not link these concepts through a chain of stated relations."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The connection could not be traced." />;
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

function claim(step: PathStep) {
  return step.reversed
    ? { subject: step.target, object: step.source }
    : { subject: step.source, object: step.target };
}

function Body({ block }: { block: ConceptMapBlock }) {
  const { steps, citations } = block.data;
  const citationById = new Map(citations.map((c) => [c.id, c]));
  const anchor = (citationId: string) => `${safeId(block.id)}-${safeId(citationId)}`;
  const first = steps[0]?.source;
  const last = steps[steps.length - 1]?.target;

  return (
    <div className="space-y-4">
      {first && last && (
        <p className="font-medium text-stone-900">
          {first} <span aria-hidden="true">→</span>
          <span className="sr-only"> to </span> {last}
          <span className="font-normal text-stone-500">
            {" "}
            ({steps.length} {steps.length === 1 ? "step" : "steps"})
          </span>
        </p>
      )}

      <ol aria-label="Steps" className="space-y-4">
        {steps.map((step, index) => {
          const citation = citationById.get(step.citationId);
          const { subject, object } = claim(step);
          return (
            <li key={index} className="border-l-2 border-emerald-600 pl-3">
              <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Step {index + 1}</div>
              <div className="font-medium text-stone-900">
                {step.source} <span aria-hidden="true">→</span>
                <span className="sr-only"> to </span> {step.target}
              </div>
              <div className="text-sm text-stone-700">
                {subject} <span className="text-stone-500">{step.relation}</span> {object}
                {step.reversed && <span className="text-stone-500"> (stated in the opposite direction)</span>}
              </div>
              {citation ? (
                <>
                  <blockquote className="mt-1 border-l-2 border-stone-300 pl-2 text-sm text-stone-600">
                    {citation.quote}
                  </blockquote>
                  <a
                    href={`#${anchor(citation.id)}`}
                    aria-label={`Source ${citation.id}: ${citation.docTitle}${citation.page != null ? `, page ${citation.page}` : ""}`}
                    className="text-xs text-emerald-700 underline"
                  >
                    {citation.docTitle}
                    {citation.page != null ? `, page ${citation.page}` : ""}
                  </a>
                </>
              ) : (
                <p role="alert" className="mt-1 text-sm text-red-700">
                  Evidence for this step is unavailable.
                </p>
              )}
            </li>
          );
        })}
      </ol>

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
