"use client";

// One concept across every document: its names, the sentences that define it, how it is linked to other concepts, the claims that
// name it and the passages that mention it. New in v2 (D-35): a page of the vault, the Obsidian-style "note" for a concept.
//
// Structural precondition (constraint 7): the vault holds a page with this id and at least one stored passage mentions it. The
// server validator derives the page again from the vault and requires exactly this block, so every name, count, link and
// sentence here is the vault's. Every sentence is a verbatim span of a stored passage and is shown with its source.
//
// Honesty about links: a link the documents STATE (a relation a model found and the builder checked against a sentence) and a
// link that is only a CO-MENTION (the two names occur in one sentence, which says nothing about how they are related) are listed
// apart and worded differently, so they are never read as the same thing.
//
// Keyboard order: the page's own name, then each section's items; another page's name is a button when the screen can open it
// (`PageName`). Document text renders as text, never as markup.

import type { Citation, ConceptPage as ConceptPageBlock, PageLinkItem } from "@arcana/schema";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { PageName } from "./notesNav";

export function ConceptPage({ block }: { block: ConceptPageBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Opening the page…" rows={4} />;
    case "empty":
      return <EmptyState title="No page to show." hint="Choose a concept in the graph, or search for one." />;
    case "error":
      return <ErrorState error={meta.error} fallback="This page could not be shown." />;
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

function Source({ citation }: { citation: Citation | undefined }) {
  if (!citation) return null;
  return (
    <span className="text-xs text-stone-500">
      {citation.docTitle}
      {citation.page != null && ` · page ${citation.page}`}
    </span>
  );
}

function Quote({ citation }: { citation: Citation | undefined }) {
  if (!citation) return null;
  return (
    <figure className="mt-1">
      <blockquote className="border-l-2 border-stone-300 pl-2 text-sm text-stone-700">{citation.quote}</blockquote>
      <figcaption>
        <Source citation={citation} />
      </figcaption>
    </figure>
  );
}

const words = (relation: string) => relation.replaceAll("_", " ");

function LinkLine({ link, self }: { link: PageLinkItem; self: { id: string; label: string } }) {
  if (link.kind === "co_mention") {
    return (
      <>
        <PageName id={link.other.id} label={link.other.label} />
        <span className="text-stone-500"> is named in the same sentence</span>
      </>
    );
  }
  const relation = <span className="text-stone-600">{words(link.relation ?? "")}</span>;
  return link.direction === "in" ? (
    <>
      <PageName id={link.other.id} label={link.other.label} /> {relation} <PageName id={self.id} label={self.label} current />
    </>
  ) : (
    <>
      <PageName id={self.id} label={self.label} current /> {relation} <PageName id={link.other.id} label={link.other.label} />
    </>
  );
}

function Body({ block }: { block: ConceptPageBlock }) {
  const d = block.data;
  const cite = new Map(d.citations.map((c) => [c.id, c]));
  const stated = d.links.filter((l) => l.kind === "asserted");
  const together = d.links.filter((l) => l.kind === "co_mention");
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

  return (
    <article aria-label={d.page.label} className="space-y-5">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-stone-900">{d.page.label}</h2>
        <p className="text-sm text-stone-600">
          {d.kind && <span className="mr-2 rounded bg-stone-100 px-1.5 py-0.5 text-xs uppercase tracking-wide">{d.kind}</span>}
          Mentioned in {plural(d.passages, "passage", "passages")} across {plural(d.documents, "document", "documents")}.
        </p>
        {d.aliases.length > 0 && <p className="text-sm text-stone-600">Also written: {d.aliases.join(", ")}.</p>}
      </header>

      <section aria-label="Definitions">
        <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">Definitions</h3>
        {d.definitions.length === 0 ? (
          <p className="mt-1 text-sm text-stone-500">No sentence that defines this concept was stored.</p>
        ) : (
          <ul className="space-y-2">
            {d.definitions.map((item) => (
              <li key={item.citationId}>
                <Quote citation={cite.get(item.citationId)} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Links" className="space-y-3">
        <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">Links</h3>
        {d.links.length === 0 && <p className="text-sm text-stone-500">This concept is not linked to another one.</p>}
        {stated.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-stone-800">What the documents state</h4>
            <ul className="mt-1 space-y-2 text-sm">
              {stated.map((link, i) => (
                <li key={`${link.other.id}-${link.relation}-${i}`}>
                  <LinkLine link={link} self={d.page} />
                  <Quote citation={cite.get(link.citationId)} />
                </li>
              ))}
            </ul>
          </div>
        )}
        {together.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-stone-800">Named together</h4>
            <p className="text-xs text-stone-500">Both names occur in one sentence. That does not say how they are related.</p>
            <ul className="mt-1 space-y-2 text-sm">
              {together.map((link, i) => (
                <li key={`${link.other.id}-${i}`}>
                  <LinkLine link={link} self={d.page} />
                  <span className="text-xs text-stone-500"> · {plural(link.passages, "passage", "passages")}</span>
                  <Quote citation={cite.get(link.citationId)} />
                </li>
              ))}
            </ul>
          </div>
        )}
        {d.linksLeftOut > 0 && (
          <p className="text-xs text-stone-500">
            {plural(d.linksLeftOut, "more link is", "more links are")} not shown (over the limit, or with no sentence to cite).
          </p>
        )}
      </section>

      {d.claims.length > 0 && (
        <section aria-label="Claims">
          <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">Claims</h3>
          <ul className="space-y-2 text-sm">
            {d.claims.map((claim) => (
              <li key={claim.citationId}>
                <Quote citation={cite.get(claim.citationId)} />
                <p className="text-xs text-stone-500">
                  Names:{" "}
                  {claim.pages.map((p, i) => (
                    <span key={p.id}>
                      {i > 0 && ", "}
                      <PageName id={p.id} label={p.label} current={p.id === d.page.id} />
                    </span>
                  ))}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Mentions">
        <h3 className="text-xs font-medium uppercase tracking-wide text-stone-500">Mentions</h3>
        {d.mentions.length === 0 && <p className="mt-1 text-sm text-stone-500">No sentence could be shown.</p>}
        <ul className="space-y-2 text-sm">
          {d.mentions.map((item) => (
            <li key={item.citationId}>
              <Quote citation={cite.get(item.citationId)} />
            </li>
          ))}
        </ul>
        {d.mentionsLeftOut > 0 && (
          <p className="mt-1 text-xs text-stone-500">{plural(d.mentionsLeftOut, "more passage mentions", "more passages mention")} it.</p>
        )}
      </section>
    </article>
  );
}
