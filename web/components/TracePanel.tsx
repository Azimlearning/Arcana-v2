"use client";

// A collapsible record of what the agents did on one turn: each hop with its agent, outcome, tokens and
// time. It loads only when opened, and only shows what the server's trace says; it never infers anything.
// Status is written out in words, not left to colour.

import type { ComponentDecision, DecisionReason, StepStatus, TurnOutcome, TurnTrace } from "@arcana/schema";
import { useEffect, useRef, useState } from "react";

import { fetchTrace } from "@/lib/api";

type Load =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready"; trace: TurnTrace }
  | { state: "error"; message: string };

const STATUS_WORDS: Record<StepStatus, string> = {
  ok: "completed",
  partial: "partly completed",
  failed: "failed",
  refused: "not run (limit reached)",
};

/**
 * Why a component was not shown, in plain sentences. Typed over the schema's closed list of codes, so adding a code to
 * the schema without a sentence here fails to compile. A code from a newer server falls back to a generic sentence.
 */
const REASON_WORDS: Record<DecisionReason, string> = {
  no_grounded_answer: "nothing in your documents could support an answer",
  no_ready_document: "there is no document ready yet",
  no_graph_result: "no connections were looked up for this question",
  no_grounded_edge: "no stated relationship had a quote naming both concepts",
  no_shared_entities: "the documents do not share enough concepts to compare",
  not_a_path: "the concepts in your question were not linked by a path",
  single_hop: "the concepts are directly linked, so a path map would add nothing",
  path_too_long: "the path between the concepts is longer than a map shows",
  broken_path: "the links between the concepts did not join up",
  ungrounded_hop: "one link on the path had no quote naming both of its concepts",
  repeated_concept: "the path went through the same concept twice",
  nothing_resolved: "the question did not match a concept in your documents, so the search followed nothing",
  no_edge_followed: "the search followed no relation that led to a passage it returned",
  too_many_seeds: "the question matched more concepts than the search path can show at once",
  block_failed_validation: "it was built but failed the server's checks, so it was not sent",
  answer_unavailable: "the answer could not be produced or checked",
  not_considered: "the turn ended before it was considered",
  unspecified: "no reason was recorded",
};
const GENERIC_REASON = "a reason this version of the app does not describe";

/** What each component is called to a reader. A component not listed is shown under its own name. */
const COMPONENT_WORDS: Record<string, string> = {
  CitedSummary: "Answer",
  SourceList: "Source list",
  GraphView: "Connection graph",
  TraversalView: "Search path",
  ComparisonGrid: "Document comparison",
  ConceptMap: "Connection path",
};

const OUTCOME_WORDS: Record<TurnOutcome, string> = {
  answered: "answered",
  empty: "no answer found",
  error: "ended with an error",
};

export function TracePanel({ turnId, fetchImpl }: { turnId: string; fetchImpl?: typeof fetch }) {
  const [open, setOpen] = useState(false);
  const [load, setLoad] = useState<Load>({ state: "idle" });

  // Fetch once, the first time the panel is opened. A ref (not state) records that a request was made,
  // so the loading state set below cannot cancel the request that caused it. A new turn is a new
  // component: the parent mounts this with key={turnId}, which resets everything.
  const requested = useRef(false);
  useEffect(() => {
    if (!open || requested.current) return;
    requested.current = true;
    setLoad({ state: "loading" });
    void fetchTrace(turnId, { fetchImpl }).then((result) =>
      setLoad(
        result.ok
          ? { state: "ready", trace: result.trace }
          : { state: "error", message: result.error.message },
      ),
    );
  }, [open, turnId, fetchImpl]);

  const panelId = `trace-${turnId}`;
  return (
    <section aria-label="Trace" className="text-sm">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="text-stone-600 underline-offset-2 hover:underline"
      >
        {open ? "Hide how this was answered" : "Show how this was answered"}
      </button>
      {open && (
        <div id={panelId} className="mt-2 rounded-lg border border-stone-200 bg-white p-3">
          {load.state === "loading" && (
            <p role="status" className="text-stone-500">
              Loading the trace…
            </p>
          )}
          {load.state === "error" && (
            <p role="alert" className="text-red-700">
              {load.message}
            </p>
          )}
          {load.state === "ready" && <TraceSteps trace={load.trace} />}
        </div>
      )}
    </section>
  );
}

function TraceSteps({ trace }: { trace: TurnTrace }) {
  return (
    <div className="space-y-2">
      <p className="text-stone-700">
        {trace.hopsUsed} {trace.hopsUsed === 1 ? "step" : "steps"}, {trace.tokensUsed.toLocaleString("en-US")} tokens:{" "}
        {OUTCOME_WORDS[trace.outcome] ?? trace.outcome}
      </p>
      <ol aria-label="Steps" className="space-y-1">
        {trace.steps.map((step) => (
          <li key={step.hop} className="flex flex-wrap gap-x-3 text-stone-600">
            <span className="font-medium text-stone-800">
              {step.hop + 1}. {step.agent.replaceAll("_", " ")}
            </span>
            <span>{STATUS_WORDS[step.status] ?? step.status}</span>
            <span>{step.tokens.toLocaleString("en-US")} tokens</span>
            <span>{step.latencyMs} ms</span>
            {step.note && <span className="text-stone-500">({step.note})</span>}
          </li>
        ))}
      </ol>
      <Composition decisions={trace.composition} />
    </div>
  );
}

function reasonWords(code: string): string {
  return (REASON_WORDS as Record<string, string | undefined>)[code] ?? GENERIC_REASON;
}

const nameOf = (component: string) => COMPONENT_WORDS[component] ?? component;

/** What the Composer showed and what it left out, and why: the answer to "why is there no graph here?". */
function Composition({ decisions }: { decisions: ComponentDecision[] }) {
  const offered = decisions.filter((d) => d.offered);
  const refused = decisions.filter((d) => !d.offered);
  if (decisions.length === 0) return null;
  return (
    <div className="space-y-2 border-t border-stone-200 pt-2">
      <section aria-label="Offered">
        <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">Offered</h4>
        {offered.length === 0 ? (
          <p className="text-stone-500">Nothing was offered.</p>
        ) : (
          <ul className="list-disc pl-5 text-stone-700">
            {offered.map((d) => (
              <li key={d.component}>
                {nameOf(d.component)}
                {d.reasons.length > 0 && (
                  <span className="text-stone-500"> ({d.reasons.map(reasonWords).join("; ")})</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Not offered">
        <h4 className="text-xs font-medium uppercase tracking-wide text-stone-500">Not offered, and why</h4>
        {refused.length === 0 ? (
          <p className="text-stone-500">Everything that could be shown was shown.</p>
        ) : (
          <ul className="list-disc pl-5 text-stone-700">
            {refused.map((d) => (
              <li key={d.component}>
                {nameOf(d.component)}: {d.reasons.length ? d.reasons.map(reasonWords).join("; ") : "no reason was recorded"}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
