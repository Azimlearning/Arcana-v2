"use client";

// The vault review screen (M2.11): what a person should look at in the notes (D-35, M2.8), in words. The vault never merges two pages
// or settles a disagreement by judgement, so this screen reports and has no button that changes anything: orphans (a concept no link
// reaches), near-duplicate pages (two names that may be one concept), concepts that several papers define (their definitions side by
// side, not compared) and hub pages (named almost everywhere, so they say little). Each list is capped by the server with an exact
// total; the screen says how many are not shown. Document text renders as text, never as markup.

import type { ErrorEnvelope, LintDuplicateReason, LintPageRef, VaultLintResponse } from "@arcana/schema";
import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchLint } from "@/lib/api";

type State = { state: "loading" } | { state: "error"; error: ErrorEnvelope } | { state: "ready"; report: VaultLintResponse };

export const REASON_WORDS: Record<LintDuplicateReason, string> = {
  same_name: "the same words once plurals and hyphens are ignored",
  one_more_word: "one name is the other with one more word",
  initials: "one name is the initials of the other",
};

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function Page({ page }: { page: LintPageRef }) {
  return (
    <span>
      <span className="font-medium text-stone-900">{page.label}</span>
      <span className="text-xs text-stone-500"> · {plural(page.passages, "passage", "passages")}</span>
    </span>
  );
}

function Section({ title, why, total, shown, children }: { title: string; why: string; total: number; shown: number; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-stone-900">
        {title} <span className="text-sm font-normal text-stone-500">({total})</span>
      </h2>
      <p className="mt-1 text-sm text-stone-600">{why}</p>
      {total === 0 ? <p className="mt-2 text-sm text-stone-500">Nothing to look at here.</p> : <div className="mt-2">{children}</div>}
      {total > shown && (
        <p className="mt-2 text-xs text-stone-500">
          {plural(total - shown, "more is", "more are")} not shown (the list stops at {shown}).
        </p>
      )}
    </section>
  );
}

function Report({ report }: { report: VaultLintResponse }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-600">
        {plural(report.pages, "page", "pages")} in the notes. This is a report: nothing here is changed for you, and no two pages are merged unless a person does it.
      </p>
      <Section
        title="Concepts that two names may describe"
        why="Two pages whose names suggest one concept. The notes keep them apart; only a person can say whether they are the same."
        total={report.duplicatesTotal}
        shown={report.duplicates.length}
      >
        <ul className="space-y-2 text-sm">
          {report.duplicates.map((d) => (
            <li key={`${d.a.id}|${d.b.id}`}>
              <Page page={d.a} /> and <Page page={d.b} />
              <span className="block text-xs text-stone-500">Why they were listed: {REASON_WORDS[d.reason]}.</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Concepts several papers define"
        why="The definitions are side by side, with the paper each comes from. They are not compared: whether they agree is for you to read."
        total={report.tensionsTotal}
        shown={report.tensions.length}
      >
        <ul className="space-y-4 text-sm">
          {report.tensions.map((t) => (
            <li key={t.page.id}>
              <Page page={t.page} />
              <ul className="mt-1 space-y-2">
                {t.definitions.map((def, i) => (
                  <li key={i}>
                    <blockquote className="border-l-2 border-stone-300 pl-2 text-stone-700">{def.text}</blockquote>
                    <span className="text-xs text-stone-500">{def.docTitle}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Concepts no link reaches"
        why="Pages mentioned in the documents but not linked to any other page. They may be real but isolated, or a name the builder should not have kept."
        total={report.orphansTotal}
        shown={report.orphans.length}
      >
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {report.orphans.map((p) => (
            <li key={p.id}>
              <Page page={p} />
            </li>
          ))}
        </ul>
      </Section>
      <Section
        title="Pages named almost everywhere"
        why="A page mentioned in a quarter or more of all passages. It says little on its own, and links through it can mislead."
        total={report.hubs.length}
        shown={report.hubs.length}
      >
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {report.hubs.map((p) => (
            <li key={p.id}>
              <Page page={p} />
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

export function ReviewScreen() {
  const [view, setView] = useState<State>({ state: "loading" });

  useEffect(() => {
    const abort = new AbortController();
    void fetchLint({ signal: abort.signal }).then((result) => {
      if (abort.signal.aborted) return;
      setView(result.ok ? { state: "ready", report: result.report } : { state: "error", error: result.error });
    });
    return () => abort.abort();
  }, []);

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="flex items-center gap-4 border-b border-stone-200 bg-white px-6 py-3">
        <span className="text-lg font-semibold">Arcana</span>
        <nav aria-label="Views" className="flex gap-3 text-sm">
          <Link href="/" className="text-stone-600 hover:text-stone-900">
            Chat
          </Link>
          <Link href="/notes" className="text-stone-600 hover:text-stone-900">
            Notes
          </Link>
          <Link href="/notes/review" aria-current="page" className="font-medium text-stone-900 underline underline-offset-4">
            Review
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">Review the notes</h1>
        {view.state === "loading" && (
          <p role="status" aria-busy="true" className="text-sm text-stone-500">
            Reading the notes…
          </p>
        )}
        {view.state === "error" && (
          <p role="alert" className="text-sm text-red-700">
            {view.error.message}
          </p>
        )}
        {view.state === "ready" && view.report.pages === 0 && (
          <p role="status" className="text-sm text-stone-600">
            There are no pages yet, so nothing to review. Add a document and the notes will appear.
          </p>
        )}
        {view.state === "ready" && view.report.pages > 0 && <Report report={view.report} />}
      </main>
    </div>
  );
}
