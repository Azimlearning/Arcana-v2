"use client";

// The workspace. It opens on the prebuilt Basic layout with the list of the user's sources (fetched from `/workspace`;
// a fixed fallback layout stands in until then, or if that fails), and an adaptive layout composed for the answer is
// layered on top of it (D-28). The frame, the panels and the switch are in `components/shell`; what each panel holds
// is decided by the layout (`placeBlocks`). Every block goes through the registry: this component never inspects a
// block's content.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorEnvelope, PanelId, UIBlock } from "@arcana/schema";

import { renderBlock } from "@/components/genui/registry";
import { LayoutSwitch } from "@/components/shell/LayoutSwitch";
import { Shell } from "@/components/shell/Shell";
import { TracePanel } from "@/components/TracePanel";
import { fetchWorkspace, uploadPdf } from "@/lib/api";
import { placeBlocks } from "@/lib/layout";
import { streamChat } from "@/lib/stream";
import { activeLayout, useWorkspace } from "@/lib/store";

export function Workspace() {
  const { documents, order, blocks, workspaceBlocks, layouts, layoutChoice, turn, turnError } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ErrorEnvelope | null>(null);
  const abort = useRef<AbortController | null>(null);

  const loadWorkspace = useCallback(async () => {
    const result = await fetchWorkspace();
    if (result.ok) useWorkspace.getState().setWorkspace(result.workspace);
    // If it fails the fallback layout stays and the sources panel shows only what was uploaded in this session.
  }, []);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const onFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setUploading(true);
      setUploadError(null);
      const result = await uploadPdf(file);
      if (result.ok) {
        useWorkspace.getState().addDocument(result.document);
        await loadWorkspace(); // the source list now includes it
      } else setUploadError(result.error);
      setUploading(false);
    },
    [loadWorkspace],
  );

  const ask = useCallback(async () => {
    const message = question.trim();
    if (!message || useWorkspace.getState().turn === "streaming") return;
    abort.current?.abort();
    abort.current = new AbortController();
    const store = useWorkspace.getState();
    store.startTurn();
    await streamChat(
      { message, history: [] },
      {
        onBlock: (block) => useWorkspace.getState().upsertBlock(block),
        onLayout: (next) => useWorkspace.getState().setLayout(next),
        onError: (error) => useWorkspace.getState().failTurn(error),
        onDone: () => useWorkspace.getState().finishTurn(),
      },
      { signal: abort.current.signal },
    );
  }, [question]);

  const layout = activeLayout({ layouts, layoutChoice });
  const placed = useMemo(
    () =>
      placeBlocks(
        layout,
        order.map((id) => blocks[id]).filter((b): b is UIBlock => b !== undefined),
        Object.values(workspaceBlocks),
      ),
    [layout, order, blocks, workspaceBlocks],
  );

  // Uploads this session that the source list does not show: a document that failed to ingest (with its reason), and a
  // ready one the list has not caught up with (or when `/workspace` could not be reached).
  const listed = new Set(
    placed.sources.flatMap((b) => (b.type === "SourceList" ? b.data.documents.map((d) => d.docId) : [])),
  );
  const localDocs = documents.filter((d) => !listed.has(d.docId));

  // The answer block's id is the turn's id (other blocks of the turn have derived ids). Offer the trace once the turn
  // has ended, including a turn that ended in an error (the trace of a failure is the one most worth reading). A turn
  // whose connection died may have no trace on the server; opening the panel then shows the server's not-found message.
  const traced = turn !== "streaming" ? placed.chat.find((b) => b.type === "CitedSummary") : undefined;

  const panels: Record<PanelId, React.ReactNode> = {
    sources: (
      <div className="space-y-4 p-1">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Sources</h2>
        <label className="block cursor-pointer rounded-lg border-2 border-dashed border-stone-300 p-4 text-center text-sm text-stone-600 hover:border-stone-400">
          <span>{uploading ? "Reading the PDF…" : "Upload a PDF"}</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            aria-label="Upload a PDF"
            disabled={uploading}
            onChange={(e) => {
              void onFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        {uploadError && (
          <p role="alert" className="text-sm text-red-700">
            {uploadError.message}
          </p>
        )}
        {localDocs.length > 0 && (
          <ul className="space-y-2 text-sm">
            {localDocs.map((doc) => (
              <li key={doc.docId} className="rounded border border-stone-200 bg-white p-2">
                <div className="font-medium text-stone-800">{doc.title}</div>
                <div className={doc.status === "ready" ? "text-stone-500" : "text-red-700"}>
                  {doc.status === "ready" ? `${doc.chunkCount} passages` : (doc.error ?? "Failed")}
                </div>
              </li>
            ))}
          </ul>
        )}
        {placed.sources.map((block) => (
          <div key={block.id}>{renderBlock(block)}</div>
        ))}
      </div>
    ),
    chat: (
      <div className="space-y-4 p-1">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about your documents"
            aria-label="Question"
            maxLength={4000}
            className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-stone-900 outline-none focus:border-stone-500"
          />
          <button
            type="submit"
            disabled={turn === "streaming" || !question.trim()}
            className="rounded-lg bg-stone-900 px-4 py-2 text-white disabled:opacity-40"
          >
            Ask
          </button>
        </form>

        <section aria-label="Answer" className="space-y-4">
          {placed.chat.map((block) => (
            <div key={block.id}>{renderBlock(block)}</div>
          ))}
          {traced && traced.meta.status !== "loading" && <TracePanel key={traced.id} turnId={traced.id} />}
          {turn === "failed" && placed.chat.length === 0 && turnError && (
            <p role="alert" className="text-sm text-red-700">
              {turnError.message}
            </p>
          )}
        </section>
      </div>
    ),
    studio: (
      <div className="space-y-4 p-1">
        {placed.studio.length === 0 ? (
          <p className="text-sm text-stone-500">Graphs and connections appear here when your question needs them.</p>
        ) : (
          placed.studio.map((block) => <div key={block.id}>{renderBlock(block)}</div>)
        )}
      </div>
    ),
  };

  return (
    <Shell
      layout={layout}
      header={
        <>
          <span className="text-lg font-semibold text-stone-900">Arcana</span>
          <LayoutSwitch
            choice={layoutChoice}
            adaptiveAvailable={layouts.adaptive !== null}
            onChoose={(choice) => useWorkspace.getState().chooseLayout(choice)}
          />
        </>
      }
      panels={panels}
    />
  );
}
