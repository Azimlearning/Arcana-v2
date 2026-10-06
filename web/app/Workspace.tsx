"use client";

// The P0 shell: an upload box, a question box, and the panel the stream renders into. All blocks go
// through the registry; this component never inspects a block's content.

import { useCallback, useRef, useState } from "react";
import type { ErrorEnvelope } from "@arcana/schema";

import { renderBlock } from "@/components/genui/registry";
import { TracePanel } from "@/components/TracePanel";
import { uploadPdf } from "@/lib/api";
import { streamChat } from "@/lib/stream";
import { useWorkspace } from "@/lib/store";

export function Workspace() {
  const { documents, order, blocks, turn, turnError } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ErrorEnvelope | null>(null);
  const abort = useRef<AbortController | null>(null);

  const onFile = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    const result = await uploadPdf(file);
    if (result.ok) useWorkspace.getState().addDocument(result.document);
    else setUploadError(result.error);
    setUploading(false);
  }, []);

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
        onError: (error) => useWorkspace.getState().failTurn(error),
        onDone: () => useWorkspace.getState().finishTurn(),
      },
      { signal: abort.current.signal },
    );
  }, [question]);

  const chatBlocks = order.map((id) => blocks[id]).filter((b) => b?.meta.panel === "chat");
  // The block's id is the turn's id. Offer the trace once the turn has ended, including a turn that
  // ended in an error (the trace of a failure is the one most worth reading). A turn whose connection
  // died may have no trace on the server; opening the panel then shows the server's not-found message.
  const traced = turn !== "streaming" ? chatBlocks[chatBlocks.length - 1] : undefined;

  return (
    <div className="mx-auto grid max-w-5xl gap-6 p-6 md:grid-cols-[18rem_1fr]">
      <aside className="space-y-4" aria-label="Sources">
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
        <ul className="space-y-2 text-sm">
          {documents.map((doc) => (
            <li key={doc.docId} className="rounded border border-stone-200 bg-white p-2">
              <div className="font-medium text-stone-800">{doc.title}</div>
              <div className={doc.status === "ready" ? "text-stone-500" : "text-red-700"}>
                {doc.status === "ready" ? `${doc.chunkCount} passages` : (doc.error ?? "Failed")}
              </div>
            </li>
          ))}
        </ul>
      </aside>

      <main className="space-y-4" aria-label="Chat">
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
          {chatBlocks.map((block) => block && <div key={block.id}>{renderBlock(block)}</div>)}
          {traced && traced.meta.status !== "loading" && <TracePanel key={traced.id} turnId={traced.id} />}
          {turn === "failed" && chatBlocks.length === 0 && turnError && (
            <p role="alert" className="text-sm text-red-700">
              {turnError.message}
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
