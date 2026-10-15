"use client";

// A brief of one stored document (D-43, V3): its key points, its key terms and what to do next. New in v2; the Studio's counterpart
// of VERA AI's "Meetings" function, with a document in place of a transcript and no model behind it.
//
// Structural precondition (constraint 7): the vault holds a claim or a definition from the document that is a verbatim span of a stored
// passage. The server validator derives the brief again from the document, the vault and the learner's mastery and requires exactly
// this block, so nothing here is summarised, ranked or invented by the client. Every sentence is cited and rendered as text, never as
// markup. The next steps follow a fixed rule over the learner's mastery, and each says why it is there.

import type { BriefActionKind, Citation, DocBrief as DocBriefBlock } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { PageName } from "./notesNav";

const ACTION_WORDS: Record<BriefActionKind, string> = { review: "Review", learn: "Learn", quiz: "Quiz" };

export function DocBrief({ block }: { block: DocBriefBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Briefing the document…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No brief could be made."
          hint="The notes hold no claim or definition from this document yet. Claims come from a graph built with the atomic builder."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The brief could not be shown." />;
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

/** The brief as Markdown, from the block's own text: nothing is added. */
export function briefMarkdown(data: DocBriefBlock["data"]): string {
  const byId = new Map(data.citations.map((c) => [c.id, c]));
  const quote = (id: string) => byId.get(id)?.quote ?? "";
  const lines: string[] = [`# Brief: ${data.docTitle}`, "", "## Key points", ""];
  for (const p of data.keyPoints) lines.push(`- ${quote(p.citationId)}`);
  lines.push("", "## Key terms", "");
  for (const t of data.terms) lines.push(`- **${t.pageLabel}**: ${quote(t.citationId)}`);
  lines.push("", "## Next steps", "");
  for (const a of data.actions) lines.push(`- ${ACTION_WORDS[a.kind]} ${a.pageLabel}: ${a.reason}`);
  return lines.join("\n") + "\n";
}

function Where({ citation }: { citation: Citation }) {
  return (
    <span className="text-xs text-stone-500">
      {citation.docTitle}
      {citation.page != null && ` · page ${citation.page}`}
    </span>
  );
}

function Body({ block }: { block: DocBriefBlock }) {
  const { docTitle, keyPoints, terms, actions, citations, claimsInDocument, leftOut } = block.data;
  const byId = new Map(citations.map((c) => [c.id, c]));
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(briefMarkdown(block.data));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // a blocked clipboard is not worth a dialog: the text is on screen to select
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Document brief</p>
          <h2 className="font-serif text-xl font-semibold text-stone-900">{docTitle}</h2>
        </div>
        <button type="button" onClick={copy} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
          {copied ? "Copied" : "Copy as Markdown"}
        </button>
      </div>

      <section aria-label="Key points">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Key points</h3>
        {keyPoints.length === 0 ? (
          <p className="text-sm text-stone-600">The notes hold no claims from this document.</p>
        ) : (
          <ol className="space-y-3">
            {keyPoints.map((point) => {
              const citation = byId.get(point.citationId);
              if (!citation) return null; // the server guarantees it exists; never render a dead point
              return (
                <li key={point.citationId}>
                  <blockquote className="border-l-2 border-emerald-300 pl-2 text-stone-900">{citation.quote}</blockquote>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
                    <Where citation={citation} />
                    {point.pageLabels.length > 0 && <span className="text-xs text-stone-500">Names: {point.pageLabels.join(", ")}</span>}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section aria-label="Key terms">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Key terms</h3>
        {terms.length === 0 ? (
          <p className="text-sm text-stone-600">This document defines no concept the notes hold.</p>
        ) : (
          <dl className="space-y-2 text-sm">
            {terms.map((term) => {
              const citation = byId.get(term.citationId);
              if (!citation) return null;
              return (
                <div key={term.citationId}>
                  <dt className="font-medium text-stone-900">
                    <PageName id={term.pageId} label={term.pageLabel} />
                  </dt>
                  <dd className="text-stone-700">{citation.quote}</dd>
                </div>
              );
            })}
          </dl>
        )}
      </section>

      <section aria-label="Next steps">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">Next steps</h3>
        <ul className="space-y-1 text-sm">
          {actions.map((a, i) => (
            <li key={`${a.kind}-${a.pageId}-${i}`} className="flex flex-wrap items-baseline gap-2">
              <span className="rounded bg-stone-100 px-1.5 py-0.5 text-xs font-medium text-stone-700">{ACTION_WORDS[a.kind]}</span>
              <span className="font-medium text-stone-900">
                <PageName id={a.pageId} label={a.pageLabel} />
              </span>
              <span className="text-xs text-stone-500">{a.reason}</span>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-xs text-stone-500">
        Made from the {claimsInDocument} {claimsInDocument === 1 ? "claim" : "claims"} the notes hold for this document
        {leftOut > 0 ? `; ${leftOut} more ${leftOut === 1 ? "is" : "are"} not shown` : ""}. These are the document&apos;s own sentences, not a
        summary, so the brief is only as complete as the notes.
      </p>
    </div>
  );
}
