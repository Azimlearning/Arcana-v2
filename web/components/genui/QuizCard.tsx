"use client";

// A quiz made from the vault's claims (Q1, D-35 amendment A8): a sentence from the documents with one concept name blanked out
// and four names to choose from. New in v2; the Studio's quiz tool, with no model behind it.
//
// Structural precondition (constraint 7): the vault holds claims, and at least one names a page whose name occurs literally in the
// claim's sentence and has at least three fair wrong answers. The server validator derives the quiz again and requires exactly
// this block. THE BLOCK CARRIES NO ANSWER: the server checks a choice (`answer` from the notes screen) and replies with the right
// name, the sentence unblanked and the new mastery, so nothing here can reveal or forge a result.
//
// A cloze tests recognising a name in a sentence, not understanding it, and the wrong answers are chosen without a model; the
// block says so. Options are buttons that keep focus while a choice is being checked; the result is announced politely and says
// which option was right in words, never by colour alone. Document text renders as text, never as markup.

import type { QuizAnswerResponse, QuizCard as QuizCardBlock, QuizItem } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { BAND_WORDS, band } from "./mastery";
import { useNotesNav } from "./notesNav";

const BLANK = "_____";

export function QuizCard({ block }: { block: QuizCardBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Making questions…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No question could be made."
          hint={
            block.data.skipped > 0
              ? `${block.data.skipped} ${block.data.skipped === 1 ? "sentence was" : "sentences were"} looked at, and none could be turned into a fair question (a name to blank out, and three other concepts of its kind to choose from).`
              : "The notes hold no claims to ask about. Claims come from a graph built with the atomic builder."
          }
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The quiz could not be shown." />;
    case "partial":
      return (
        <PartialState>
          <Body key={quizKey(block)} block={block} />
        </PartialState>
      );
    case "ready":
      return (
        <Frame>
          <Body key={quizKey(block)} block={block} />
        </Frame>
      );
  }
}

/** A new quiz is a new set of items: the answers given to the last one are not carried over. */
const quizKey = (block: QuizCardBlock) => block.data.items.map((i) => i.id).join("|");

type Result = { state: "checking" } | { state: "failed" } | { state: "done"; chosenId: string; reply: QuizAnswerResponse };

/** The sentence with each blank drawn as a line (read out as "blank"), or with the right name in it once answered. */
function Sentence({ text, filled }: { text: string; filled: string | null }) {
  const parts = text.split(BLANK);
  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 &&
            (filled === null ? (
              <>
                <span aria-hidden="true" className="mx-1 inline-block w-16 border-b-2 border-stone-600" />
                <span className="sr-only">blank</span>
              </>
            ) : (
              <strong className="text-emerald-800">{filled}</strong>
            ))}
          {part}
        </span>
      ))}
    </>
  );
}

function Question({ item, index, total, result, onChoose }: {
  item: QuizItem;
  index: number;
  total: number;
  result: Result | undefined;
  onChoose: ((chosenId: string) => void) | null;
}) {
  const nav = useNotesNav();
  const done = result?.state === "done" ? result : null;
  const right = done?.reply.answer ?? null;
  const m = done?.reply.mastery ?? null;
  return (
    <li className="space-y-2 rounded border border-stone-200 p-3">
      <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">
        Question {index + 1} of {total}
      </h3>
      <p className="text-sm text-stone-900">
        <Sentence text={item.text} filled={right?.label ?? null} />
      </p>
      <p className="text-xs text-stone-500">
        From {item.docTitle || "a document"}
        {item.page != null && ` · page ${item.page}`}
      </p>
      <div role="group" aria-label="Answer choices" className="flex flex-wrap gap-2">
        {item.options.map((option) => {
          const mark = done === null ? "" : option.id === right?.id ? " (the answer)" : option.id === done.chosenId ? " (your choice)" : "";
          return onChoose === null ? (
            <span key={option.id} className="rounded border border-stone-200 px-2 py-1 text-sm text-stone-700">
              {option.label}
            </span>
          ) : (
            <button
              key={option.id}
              type="button"
              aria-disabled={result !== undefined && result.state !== "failed"}
              onClick={() => {
                if (result !== undefined && result.state !== "failed") return; // answered, or being checked: the button keeps focus
                onChoose(option.id);
              }}
              className={`rounded border px-2 py-1 text-sm ${
                done !== null && option.id === right?.id
                  ? "border-emerald-600 bg-emerald-50 text-emerald-900"
                  : done !== null && option.id === done.chosenId
                    ? "border-rose-500 bg-rose-50 text-rose-900"
                    : "border-stone-300 bg-white text-stone-800 hover:bg-stone-100"
              } ${result?.state === "checking" ? "opacity-60" : ""}`}
            >
              {option.label}
              {mark}
            </button>
          );
        })}
      </div>
      <div role="status" aria-live="polite" className="text-sm">
        {result?.state === "checking" && <span className="text-stone-500">Checking…</span>}
        {done !== null && (
          <div className="space-y-1">
            <p className={done.reply.correct ? "font-medium text-emerald-800" : "font-medium text-rose-800"}>
              {done.reply.correct ? "Correct." : `Not quite. The answer is ${done.reply.answer.label}.`}
            </p>
            <figure>
              <blockquote className="border-l-2 border-stone-300 pl-2 text-stone-700">{done.reply.citation.quote}</blockquote>
              <figcaption className="text-xs text-stone-500">
                {done.reply.citation.docTitle}
                {done.reply.citation.page != null && ` · page ${done.reply.citation.page}`}
              </figcaption>
            </figure>
            {m !== null && (
              <p className="text-xs text-stone-600">
                Your mastery of {done.reply.answer.label}: {BAND_WORDS[band(m.score)]} ({Math.round(m.score * 100)} percent, from {m.events}{" "}
                {m.events === 1 ? "rating or answer" : "ratings and answers"}).
              </p>
            )}
          </div>
        )}
      </div>
      {result?.state === "failed" && (
        <div role="alert" className="space-y-1 text-xs text-red-700">
          <p>Your answer could not be checked. Choose again, or, if the documents changed, ask for more questions.</p>
          {nav?.moreQuestions && (
            <button type="button" onClick={nav.moreQuestions} className="rounded border border-red-300 bg-white px-2 py-1 text-red-800">
              More questions
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function Body({ block }: { block: QuizCardBlock }) {
  const nav = useNotesNav();
  const [results, setResults] = useState<Record<string, Result>>({});
  const d = block.data;
  const answer = nav?.answer;

  const choose = async (item: QuizItem, chosenId: string) => {
    if (!answer) return;
    setResults((r) => ({ ...r, [item.id]: { state: "checking" } }));
    const reply = await answer(item.id, chosenId);
    setResults((r) => ({ ...r, [item.id]: reply ? { state: "done", chosenId, reply } : { state: "failed" } }));
  };

  const answered = d.items.filter((i) => results[i.id]?.state === "done");
  const right = answered.filter((i) => {
    const r = results[i.id];
    return r?.state === "done" && r.reply.correct;
  }).length;
  const finished = answered.length === d.items.length;

  return (
    <section aria-label="Quiz questions" className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-stone-900">Quiz</h2>
        <p className="text-sm text-stone-600">
          {d.focusId === null ? "Choose the concept that fills each blank, starting with the ones you know least." : "Choose the concept that fills each blank."}{" "}
          Every sentence is from your documents.
        </p>
        {!answer && <p className="text-xs text-stone-500">Open the notes screen to answer these questions.</p>}
      </header>
      <ol className="space-y-3">
        {d.items.map((item, i) => (
          <Question
            key={item.id}
            item={item}
            index={i}
            total={d.items.length}
            result={results[item.id]}
            onChoose={answer ? (chosenId) => void choose(item, chosenId) : null}
          />
        ))}
      </ol>
      {finished && d.items.length > 0 && (
        <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-medium text-stone-800">
            You got {right} of {d.items.length}.
          </span>
          {nav?.moreQuestions && (
            <button type="button" onClick={nav.moreQuestions} className="rounded bg-stone-900 px-3 py-1.5 text-sm text-white">
              More questions
            </button>
          )}
        </div>
      )}
      {d.skipped > 0 && (
        <p className="text-xs text-stone-500">
          {d.skipped} {d.skipped === 1 ? "sentence was" : "sentences were"} passed over (no name to blank out, or no fair wrong answers).
        </p>
      )}
      <p className="text-xs text-stone-500">
        A fill-in-the-blank question tests recognising a name in a sentence, not understanding it. The wrong answers are other concepts of the same kind, chosen
        without a model, so some can be too easy.
      </p>
    </section>
  );
}
