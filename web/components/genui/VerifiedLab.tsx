"use client";

// A generated, verified lab (P4, D-36): one pure function, made from a contract, checked by an AST allowlist and an isolated runner, and
// delivered only if the server's verified record matches it. New in v2; the only block that carries code.
//
// Structural precondition (constraint 7): a stored passage states the lab's formula, and a function written for the contract passed the
// checker and the verifier. The server validator re-derives this block from the stored record and requires equality; THIS component then
// refuses to render unless the function's SHA-256 equals the block's `sourceSha256` and the template version is the one it holds.
//
// The code runs only inside `<iframe sandbox="allow-scripts">` (exactly that token: an opaque origin, no storage, no parent access, no
// forms, popups or navigation) with a Content-Security-Policy that forbids every load, built from our own fixed template (`labFrame.ts`).
// Everything about the lab outside the frame (its title, the cited sentence, what was checked) is text. The lab says it is generated and
// verified on stated cases, which is not a proof for every input.

import type { Citation, LabParameter, VerifiedLab as VerifiedLabBlock } from "@arcana/schema";
import { useEffect, useState } from "react";

import { buildFrame, LAB_SANDBOX } from "@/lib/labFrame";

import { EmptyState, ErrorState, Frame, LoadingState } from "./BlockStates";

export function VerifiedLab({ block }: { block: VerifiedLabBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Making and checking the lab…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No lab could be made."
          hint="None of the stored passages states this lab's formula, so there is nothing to ground it in."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The lab could not be shown." />;
    case "partial":
      // A lab is delivered whole: a partial one is never shown (the server refuses it too).
      return <ErrorState error={null} fallback="A lab is only shown when it is complete and verified." />;
    case "ready":
      return (
        <Frame>
          <Body block={block} />
        </Frame>
      );
  }
}

type Checked = { state: "checking" } | { state: "ready"; srcdoc: string } | { state: "refused"; reason: string };

function useFrame(data: VerifiedLabBlock["data"]): Checked {
  const [result, setResult] = useState<{ key: string; value: Checked } | null>(null);
  const key = `${data.labId}|${data.sourceSha256}|${data.templateVersion}`;
  useEffect(() => {
    let live = true;
    void buildFrame(data).then((built) => {
      if (live) setResult({ key, value: built.ok ? { state: "ready", srcdoc: built.srcdoc } : { state: "refused", reason: built.reason } });
    });
    return () => {
      live = false;
    };
    // `data` is identified by `key`: the same lab is not checked again
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return result !== null && result.key === key ? result.value : { state: "checking" };
}

function Source({ citation }: { citation: Citation | undefined }) {
  if (!citation) return null;
  return (
    <figure>
      <blockquote className="border-l-2 border-stone-300 pl-2 text-sm text-stone-700">{citation.quote}</blockquote>
      <figcaption className="text-xs text-stone-500">
        The formula is stated in {citation.docTitle}
        {citation.page != null && ` · page ${citation.page}`}
      </figcaption>
    </figure>
  );
}

const range = (p: LabParameter) => `${p.label}: from ${p.min} to ${p.max}${p.unit ? ` ${p.unit}` : ""}, starting at ${p.default}`;

function Body({ block }: { block: VerifiedLabBlock }) {
  const d = block.data;
  const frame = useFrame(d);
  const c = d.checked;
  return (
    <section aria-label="Lab" className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-stone-900">{d.title}</h2>
        <p className="text-sm text-stone-600">
          A function written for this formula, checked by rules that allow only arithmetic and verified in an isolated runner: on {c.referenceCases}{" "}
          reference {c.referenceCases === 1 ? "case" : "cases"}, on {c.properties} {c.properties === 1 ? "property" : "properties"}, on every one of the{" "}
          {c.gridPoints.toLocaleString("en-US")} settings the sliders can reach, and on {c.fuzzCases} other inputs. That is not a proof that it is right for every
          input, only for these.
        </p>
      </header>
      <Source citation={d.citations[0]} />
      <div role="group" aria-label="Parameters" className="text-xs text-stone-500">
        <ul className="list-disc pl-5">
          {d.parameters.map((p) => (
            <li key={p.name}>{range(p)}</li>
          ))}
        </ul>
      </div>
      {frame.state === "checking" && (
        <p role="status" aria-busy="true" className="text-sm text-stone-500">
          Checking the lab&apos;s code against its hash…
        </p>
      )}
      {frame.state === "refused" && (
        <p role="alert" className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800">
          {frame.reason}
        </p>
      )}
      {frame.state === "ready" && (
        <iframe
          title={`Lab: ${d.title}`}
          sandbox={LAB_SANDBOX}
          srcDoc={frame.srcdoc}
          referrerPolicy="no-referrer"
          className="h-[34rem] w-full rounded border border-stone-300 bg-white"
        />
      )}
    </section>
  );
}
