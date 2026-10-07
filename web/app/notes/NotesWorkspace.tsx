"use client";

// The notes view: an Obsidian-style way into the vault (D-35). The server composes it: a page for the chosen concept and the graph
// of pages around it (or the most linked pages across the vault), with the layout that places them (`/vault/notes`). This screen
// holds only what the user chose (a page, a search, a quiz) and what the server last sent; every block goes through the registry, so
// it never inspects a block's content. Choosing a page name anywhere (the graph, a link, a claim) opens that page.
//
// A quiz (Q1, D-35 A8) is the same screen in another mode: `/vault/quiz` composes a QuizCard and the graph beside it. Answering a
// question asks the server to check it (the quiz carries no answer) and then replaces only the graph block with the graph around the
// concept just answered (its colour is the new mastery), while the questions stay as they are; "More questions" fetches a new quiz.

import type { ErrorEnvelope, LayoutSpec, PanelId, QuizAnswerResponse, RegionId, UIBlock } from "@arcana/schema";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { renderBlock } from "@/components/genui/registry";
import { NotesNav } from "@/components/genui/notesNav";
import { Shell } from "@/components/shell/Shell";
import type { LearnerSignal } from "@arcana/schema";

import { answerQuiz, fetchNotes, fetchQuiz, recordLearnerEvent } from "@/lib/api";
import { placeBlocksByRegion } from "@/lib/layout";

/** What the server last sent, and the choice (`key`) it answered. An answer to an earlier choice is not shown. */
type Answer = { key: string } & ({ ok: false; error: ErrorEnvelope } | { ok: true; layout: LayoutSpec; blocks: UIBlock[] });
type View =
  | { state: "loading" }
  | { state: "error"; error: ErrorEnvelope }
  | { state: "ready"; layout: LayoutSpec; blocks: UIBlock[] };

export function NotesWorkspace() {
  const [page, setPage] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [version, setVersion] = useState(0); // bumped after a rating: the same page is fetched again, quietly, with it
  const [quiz, setQuiz] = useState(false);
  const [round, setRound] = useState(0); // bumped by "More questions": a new quiz is fetched
  const key = `${quiz ? "quiz" : "notes"}|${page ?? ""}|${query}|${quiz ? round : 0}`;

  useEffect(() => {
    const abort = new AbortController();
    const asked = quiz ? fetchQuiz({ page }, { signal: abort.signal }) : fetchNotes({ page, query }, { signal: abort.signal });
    void asked.then((result) => {
      if (abort.signal.aborted) return; // a newer choice was made: this answer is stale
      setAnswer(
        result.ok
          ? { key, ok: true, layout: result.workspace.layout, blocks: result.workspace.blocks }
          : { key, ok: false, error: result.error },
      );
    });
    return () => abort.abort();
  }, [page, query, quiz, key, version]);

  const rate = useCallback(async (pageId: string, signal: LearnerSignal) => {
    const saved = await recordLearnerEvent(pageId, signal);
    if (saved) setVersion((v) => v + 1);
    return saved;
  }, []);

  /** Check a quiz choice on the server, then show the graph around the concept just answered (only that block changes), so its colour follows. */
  const checkChoice = useCallback(
    async (itemId: string, chosenId: string): Promise<QuizAnswerResponse | null> => {
      const reply = await answerQuiz(itemId, chosenId);
      if (reply === null) return null;
      const fresh = await fetchNotes({ page: reply.answer.id });
      if (fresh.ok) {
        const graph = fresh.workspace.blocks.find((b) => b.type === "NotesGraph");
        if (graph) {
          setAnswer((a) =>
            a !== null && a.ok && a.key === key ? { ...a, blocks: a.blocks.map((b) => (b.type === "NotesGraph" ? graph : b)) } : a,
          );
        }
      }
      return reply;
    },
    [key],
  );
  const moreQuestions = useCallback(() => setRound((r) => r + 1), []);

  const view = useMemo<View>(
    () =>
      answer === null || answer.key !== key
        ? { state: "loading" }
        : answer.ok
          ? { state: "ready", layout: answer.layout, blocks: answer.blocks }
          : { state: "error", error: answer.error },
    [answer, key],
  );

  const openPage = useCallback((id: string) => {
    setQuiz(false);
    setPage(id);
  }, []);
  const nav = useMemo(
    () => ({ openPage, rate, ...(quiz ? { answer: checkChoice, moreQuestions } : {}) }),
    [openPage, rate, quiz, checkChoice, moreQuestions],
  );

  const layout = view.state === "ready" ? view.layout : null;
  const byRegion = useMemo(
    () => (view.state === "ready" ? placeBlocksByRegion(view.layout, [], view.blocks) : null),
    [view],
  );

  const show = (blocks: UIBlock[]) =>
    blocks.map((block) => (
      <div key={block.id} className="space-y-4">
        {renderBlock(block)}
      </div>
    ));

  const message = (text: string, role?: "alert") => (
    <p role={role} className={`p-2 text-sm ${role === "alert" ? "text-red-700" : "text-stone-500"}`}>
      {text}
    </p>
  );

  const empty = (id: PanelId, region: RegionId) => byRegion === null || byRegion[id][region].length === 0;
  const panels: Record<PanelId, Partial<Record<RegionId, React.ReactNode>>> = {
    sources: { main: byRegion ? show(byRegion.sources.main) : undefined },
    chat: {
      main: (
        <div className="space-y-4 p-1">
          {view.state === "loading" && message("Opening the notes…")}
          {view.state === "error" && message(view.error.message, "alert")}
          {byRegion && show(byRegion.chat.main)}
          {byRegion && empty("chat", "main") && message("Choose a page in the graph, or search for a concept.")}
        </div>
      ),
      secondary: byRegion && byRegion.chat.secondary.length > 0 ? show(byRegion.chat.secondary) : undefined,
    },
    studio: {
      main: <div className="space-y-4 p-1">{byRegion && show(byRegion.studio.main)}</div>,
      shelf: byRegion && byRegion.studio.shelf.length > 0 ? show(byRegion.studio.shelf) : undefined,
    },
  };

  const fallback: LayoutSpec = layout ?? {
    version: 2,
    origin: "prebuilt",
    mode: "research",
    panels: [
      { id: "sources", width: 0, direction: "rows", regions: [{ id: "main", size: 100 }] },
      { id: "chat", width: 40, direction: "rows", regions: [{ id: "main", size: 100 }] },
      { id: "studio", width: 60, direction: "rows", regions: [{ id: "main", size: 100 }] },
    ],
    placements: [],
  };

  return (
    <NotesNav.Provider value={nav}>
      <Shell
        layout={fallback}
        header={
          <>
            <div className="flex items-center gap-4">
              <span className="text-lg font-semibold text-stone-900">Arcana</span>
              <nav aria-label="Views" className="flex gap-3 text-sm">
                <Link href="/" className="text-stone-600 hover:text-stone-900">
                  Chat
                </Link>
                <Link href="/notes" aria-current="page" className="font-medium text-stone-900 underline underline-offset-4">
                  Notes
                </Link>
              </nav>
            </div>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setQuiz(false);
                setPage(null);
                setQuery(draft.trim());
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Search pages"
                aria-label="Search pages"
                maxLength={120}
                className="w-64 rounded-lg border border-stone-300 px-3 py-1.5 text-sm text-stone-900 outline-none focus:border-stone-500"
              />
              <button type="submit" className="rounded-lg bg-stone-900 px-3 py-1.5 text-sm text-white">
                Search
              </button>
              <button
                type="button"
                onClick={() => {
                  setRound((r) => r + 1);
                  setQuiz(true);
                }}
                className="rounded-lg border border-stone-900 px-3 py-1.5 text-sm font-medium text-stone-900 hover:bg-stone-100"
              >
                {page !== null ? "Quiz me on this page" : "Quiz me"}
              </button>
              {(page !== null || query !== "" || quiz) && (
                <button
                  type="button"
                  onClick={() => {
                    setQuiz(false);
                    setPage(null);
                    setQuery("");
                    setDraft("");
                  }}
                  className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm text-stone-700"
                >
                  All pages
                </button>
              )}
            </form>
          </>
        }
        panels={panels}
      />
    </NotesNav.Provider>
  );
}
