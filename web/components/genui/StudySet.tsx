"use client";

// A study set made from the vault (P5 S2, D-42): flashcards, blurting, Cornell notes or a Socratic turn. New in v2; the Studio's
// learning tools, with no model behind them.
//
// Structural precondition (constraint 7): the vault holds a concept page with a stored definition or claim (a Socratic set: an
// asserted link with a cited sentence). The server validator derives the set again and requires exactly this block, which includes
// the withholding: a prompt or hint never holds the sentence it keeps back. What is revealed is a verbatim, cited sentence of the
// learner's own documents, rendered as text, never as markup. Nothing here grades free text; the three self-ratings are the same
// events a concept page records, so the mastery colouring moves.

import type { Citation, LearnerSignal, StudyItem, StudyKind, StudySet as StudySetBlock } from "@arcana/schema";
import { useState } from "react";

import { recordLearnerEvent } from "@/lib/api";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { useNotesNav } from "./notesNav";

const KIND_WORDS: Record<StudyKind, { title: string; reveal: string }> = {
  flashcard: { title: "Flashcards", reveal: "Show the definition" },
  blurt: { title: "Blurting", reveal: "Check against your documents" },
  cornell: { title: "Cornell notes", reveal: "Show the notes" },
  socratic: { title: "Socratic questions", reveal: "Check against your documents" },
};

const RATINGS: { signal: LearnerSignal; label: string }[] = [
  { signal: "know", label: "I knew this" },
  { signal: "unsure", label: "I was unsure" },
  { signal: "dont_know", label: "I didn't know this" },
];

export function StudySet({ block }: { block: StudySetBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Making study items…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="No study items could be made."
          hint={
            block.data.skipped > 0
              ? `${block.data.skipped} ${block.data.skipped === 1 ? "page was" : "pages were"} looked at, and none had a sentence to build an item from.`
              : "The notes hold no definitions or claims to study yet."
          }
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The study set could not be shown." />;
    case "partial":
      return (
        <PartialState>
          <Body key={setKey(block)} block={block} />
        </PartialState>
      );
    case "ready":
      return (
        <Frame>
          <Body key={setKey(block)} block={block} />
        </Frame>
      );
  }
}

/** A new set is a new set of items: what was revealed or rated for the last one is not carried over. */
const setKey = (block: StudySetBlock) => `${block.data.kind}:${block.data.items.map((i) => i.id).join("|")}`;

function Body({ block }: { block: StudySetBlock }) {
  const { kind, items, citations, summary } = block.data;
  const byId = new Map(citations.map((c) => [c.id, c]));
  const words = KIND_WORDS[kind];
  const summaryCitation = summary ? byId.get(summary.citationId) : undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">{words.title}</h2>
        <p className="text-xs text-stone-500">
          {items.length} {items.length === 1 ? "item" : "items"}
        </p>
      </div>
      <section aria-label="Study items">
        <ol className="space-y-4">
          {items.map((item) => (
            <Item key={item.id} item={item} kind={kind} byId={byId} />
          ))}
        </ol>
      </section>
      {summaryCitation && (
        <section className="border-t border-stone-200 pt-3" aria-label="Summary">
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Summary</h3>
          <blockquote className="border-l-2 border-stone-300 pl-2 text-sm text-stone-700">{summaryCitation.quote}</blockquote>
        </section>
      )}
      <p className="text-xs text-stone-500">
        These are prompts for your own recall: nothing here marks your answer. Every sentence shown is from your documents.
      </p>
    </div>
  );
}

type Rated = "idle" | "saving" | "saved" | "failed";

function Item({ item, kind, byId }: { item: StudyItem; kind: StudyKind; byId: Map<string, Citation> }) {
  const nav = useNotesNav();
  const [hintShown, setHintShown] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [rated, setRated] = useState<Rated>("idle");

  const rate = async (signal: LearnerSignal) => {
    setRated("saving");
    const ok = await (nav?.rate ? nav.rate(item.pageId, signal) : recordLearnerEvent(item.pageId, signal));
    setRated(ok ? "saved" : "failed");
  };

  return (
    <li className="rounded-md border border-stone-200 p-3">
      <p className={kind === "flashcard" ? "text-lg font-semibold text-stone-900" : "text-base text-stone-900"}>{item.prompt}</p>
      {item.hint && (
        <div className="mt-2">
          {hintShown ? (
            <p className="text-sm text-stone-600">{item.hint}</p>
          ) : (
            <button type="button" onClick={() => setHintShown(true)} className="text-xs text-emerald-800 underline">
              Show a hint
            </button>
          )}
        </div>
      )}
      {!revealed ? (
        <button
          type="button"
          onClick={() => setRevealed(true)}
          className="mt-3 rounded border border-stone-300 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
        >
          {KIND_WORDS[kind].reveal}
        </button>
      ) : (
        <div className="mt-3 space-y-2">
          <ul className="space-y-2 text-sm">
            {item.notes.map((note, i) => {
              const citation = byId.get(note.citationId);
              if (!citation) return null; // the server guarantees it exists; never render a dead note
              const where = citation.page != null ? ` · page ${citation.page}` : "";
              return (
                <li key={`${note.citationId}-${i}`}>
                  <blockquote className="border-l-2 border-emerald-300 pl-2 text-stone-800">{citation.quote}</blockquote>
                  <span className="text-xs text-stone-500">
                    {citation.docTitle}
                    {where}
                  </span>
                </li>
              );
            })}
          </ul>
          <div role="group" aria-label="Rate yourself" className="flex flex-wrap items-center gap-1">
            {RATINGS.map((r) => (
              <button
                key={r.signal}
                type="button"
                disabled={rated === "saving" || rated === "saved"}
                onClick={() => void rate(r.signal)}
                className="rounded border border-stone-300 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50 disabled:opacity-50"
              >
                {r.label}
              </button>
            ))}
            <span role="status" className="text-xs text-stone-500">
              {rated === "saved" && "Saved."}
              {rated === "failed" && "Could not save your rating."}
            </span>
          </div>
        </div>
      )}
    </li>
  );
}
