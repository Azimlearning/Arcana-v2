// The documents the workspace can answer from. New in v2 (no v1 counterpart).
//
// Structural precondition (constraint 7): at least one stored document with status `ready`. It needs no
// retrieval, which is why the Composer can show it before any question has been asked. Titles come from the
// document store and are rendered as text, never as markup.

import type { SourceList as SourceListBlock } from "@arcana/schema";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";

export function SourceList({ block }: { block: SourceListBlock }) {
  const { meta } = block;

  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Listing your documents…" rows={2} />;
    case "empty":
      return <EmptyState title="No documents yet." hint="Upload a PDF to ask questions about it." />;
    case "error":
      return <ErrorState error={meta.error} fallback="Your documents could not be listed." />;
    case "partial":
      return (
        <PartialState>
          <Items block={block} />
        </PartialState>
      );
    case "ready":
      return (
        <Frame>
          <Items block={block} />
        </Frame>
      );
  }
}

function Items({ block }: { block: SourceListBlock }) {
  const { documents } = block.data;
  return (
    <section aria-label="Documents">
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500">
        Documents ({documents.length})
      </h3>
      <ul className="space-y-2 text-sm">
        {documents.map((doc) => (
          <li key={doc.docId}>
            <div className="font-medium text-stone-800">{doc.title}</div>
            <div className="text-stone-500">
              {doc.chunkCount} {doc.chunkCount === 1 ? "passage" : "passages"}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
