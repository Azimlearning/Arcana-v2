// The Studio's cited draft (P5 S1, D-42). New in v2.
//
// Structural precondition (constraint 7): a WritingDraft needs sections whose every passage stands on a verbatim quote of a stored
// chunk, and a bibliography with one reference per cited document built from the stored record. Retrieval and the Fact Checker satisfy
// it; the server validator enforces it, so the client never has to guess. The references are copied exactly as the server sent them:
// this component formats nothing and invents nothing.

"use client";

import type { WritingDraft as WritingDraftBlock } from "@arcana/schema";
import { useState } from "react";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { safeId } from "./ids";

type Style = "apa" | "ieee" | "bibtex";
const STYLES: { id: Style; label: string }[] = [
  { id: "apa", label: "APA" },
  { id: "ieee", label: "IEEE" },
  { id: "bibtex", label: "BibTeX" },
];

export function WritingDraft({ block }: { block: WritingDraftBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Drafting from your documents…" rows={5} />;
    case "empty":
      return (
        <EmptyState
          title="Nothing could be drafted from your documents."
          hint="The draft only says what a stored passage supports. Ask about something your documents cover."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="This draft could not be produced." />;
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

/** The bibliography as one text, in the chosen style: BibTeX entries separated by a blank line, others one per line. */
export function bibliographyText(entries: WritingDraftBlock["data"]["bibliography"], style: Style): string {
  return entries.map((e) => e[style]).join(style === "bibtex" ? "\n\n" : "\n");
}

/** The whole draft as Markdown: title, sections with their citation markers, the sources and the references. */
export function draftMarkdown(data: WritingDraftBlock["data"], style: Style): string {
  const lines: string[] = [`# ${data.title}`, ""];
  for (const section of data.sections) {
    lines.push(`## ${section.heading}`, "");
    for (const segment of section.segments) {
      lines.push(`${segment.text} ${segment.citationIds.map((id) => `[${id}]`).join("")}`, "");
    }
  }
  lines.push("## Sources", "");
  for (const c of data.citations) {
    lines.push(`- [${c.id}] ${c.docTitle}${c.page != null ? `, page ${c.page}` : ""}: "${c.quote}"`);
  }
  lines.push("", "## References", "", bibliographyText(data.bibliography, style));
  return lines.join("\n") + "\n";
}

function Body({ block }: { block: WritingDraftBlock }) {
  const { title, sections, citations, bibliography } = block.data;
  const [style, setStyle] = useState<Style>("apa");
  const [copied, setCopied] = useState(false);
  const byId = new Map(citations.map((c) => [c.id, c]));
  const anchor = (citationId: string) => `${safeId(block.id)}-${safeId(citationId)}`;
  const text = bibliographyText(bibliography, style);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // a blocked clipboard is not an error worth a dialog: the text is on screen to select
    }
  };

  const download = (kind: "bib" | "md") => {
    const body = kind === "bib" ? text + "\n" : draftMarkdown(block.data, style);
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = kind === "bib" ? "references.bib" : "draft.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <h2 className="font-serif text-xl font-semibold text-stone-900">{title}</h2>

      <section aria-label="Draft" className="space-y-5">
        {sections.map((section, i) => (
          <div key={i}>
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-stone-600">{section.heading}</h3>
            <p className="font-serif text-base leading-relaxed text-stone-900">
              {section.segments.map((segment, j) => (
                <span key={j}>
                  {segment.text}{" "}
                  {segment.citationIds.map((id) => {
                    const citation = byId.get(id);
                    if (!citation) return null; // the server guarantees it exists; never render a dead pill
                    const where = citation.page != null ? `, page ${citation.page}` : "";
                    return (
                      <a
                        key={id}
                        href={`#${anchor(id)}`}
                        title={citation.quote}
                        aria-label={`Source ${id}: ${citation.docTitle}${where}`}
                        className="mr-1 inline-block rounded bg-emerald-100 px-1.5 text-xs font-medium text-emerald-800 no-underline hover:bg-emerald-200"
                      >
                        {id}
                      </a>
                    );
                  })}{" "}
                </span>
              ))}
            </p>
          </div>
        ))}
      </section>

      {citations.length > 0 && (
        <section className="border-t border-stone-200 pt-3" aria-label="Sources">
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
      )}

      {bibliography.length > 0 && (
        <section className="border-t border-stone-200 pt-3" aria-label="Bibliography">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">Bibliography</h3>
            <div role="group" aria-label="Reference style" className="flex gap-1">
              {STYLES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  aria-pressed={style === s.id}
                  onClick={() => setStyle(s.id)}
                  className={`rounded border px-2 py-0.5 text-xs ${
                    style === s.id ? "border-emerald-600 bg-emerald-50 text-emerald-800" : "border-stone-300 text-stone-600"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <div className="ml-auto flex gap-1">
              <button type="button" onClick={copy} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
                {copied ? "Copied" : "Copy references"}
              </button>
              <button type="button" onClick={() => download("bib")} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
                Download .bib
              </button>
              <button type="button" onClick={() => download("md")} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
                Download draft (.md)
              </button>
            </div>
          </div>
          <ol className="list-decimal space-y-2 pl-5 text-sm text-stone-800">
            {bibliography.map((entry) => (
              <li key={entry.docId}>
                {style === "bibtex" ? <pre className="whitespace-pre-wrap font-mono text-xs">{entry.bibtex}</pre> : entry[style]}
              </li>
            ))}
          </ol>
          <p className="mt-2 text-xs text-stone-500">
            References are built from your stored document records. Nothing is added that the record does not hold.
          </p>
        </section>
      )}
    </div>
  );
}
