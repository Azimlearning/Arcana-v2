"use client";

// A collapsible record of what the agents did on one turn: each hop with its agent, outcome, tokens and
// time. It loads only when opened, and only shows what the server's trace says; it never infers anything.
// Status is written out in words, not left to colour.

import type { StepStatus, TurnOutcome, TurnTrace } from "@arcana/schema";
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
      <ol className="space-y-1">
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
    </div>
  );
}
