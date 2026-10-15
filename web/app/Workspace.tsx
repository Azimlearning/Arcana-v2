"use client";

// The workspace. It opens on the prebuilt Basic layout with the list of the user's sources (fetched from `/workspace`;
// a fixed fallback layout stands in until then, or if that fails), and an adaptive layout composed for the answer is
// layered on top of it (D-28). The frame, the panels and the switch are in `components/shell`; what each panel holds
// is decided by the layout (`placeBlocks`). Every block goes through the registry: this component never inspects a
// block's content.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ErrorEnvelope, PanelId, RegionId, UIBlock } from "@arcana/schema";

import { renderBlock } from "@/components/genui/registry";
import { LayoutSwitch } from "@/components/shell/LayoutSwitch";
import { SaveView, type SaveOutcome } from "@/components/shell/SaveView";
import { SavedViews, refusalWords } from "@/components/shell/SavedViews";
import { Shell } from "@/components/shell/Shell";
import { Studio } from "@/components/shell/Studio";
import { TracePanel } from "@/components/TracePanel";
import { deletePattern, fetchWorkspace, listPatterns, reverifyPattern, savePattern, uploadPdf } from "@/lib/api";
import { flattenPlaced, placeBlocksByRegion } from "@/lib/layout";
import { streamApply, streamChat } from "@/lib/stream";
import { activeLayout, useWorkspace } from "@/lib/store";

export function Workspace() {
  const { documents, order, blocks, workspaceBlocks, layouts, layoutChoice, turn, turnError, patterns } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ErrorEnvelope | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [staleId, setStaleId] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const loadWorkspace = useCallback(async () => {
    const result = await fetchWorkspace();
    if (result.ok) useWorkspace.getState().setWorkspace(result.workspace);
    // If it fails the fallback layout stays and the sources panel shows only what was uploaded in this session.
  }, []);

  const loadPatterns = useCallback(async () => {
    const result = await listPatterns();
    if (result.ok) useWorkspace.getState().setPatterns(result.patterns);
  }, []);

  useEffect(() => {
    void loadWorkspace();
    void loadPatterns();
  }, [loadWorkspace, loadPatterns]);

  // Show a saved view again. It streams like an answer (so it goes through the same block and layout path) but asks
  // no question and calls no model; a refusal arrives as an error and shows nothing.
  const showView = useCallback(async (id: string) => {
    if (useWorkspace.getState().turn === "streaming") return;
    setSavedMessage(null);
    setStaleId(null);
    abort.current?.abort();
    abort.current = new AbortController();
    useWorkspace.getState().startTurn();
    await streamApply(
      id,
      {
        onBlock: (block) => useWorkspace.getState().upsertBlock(block),
        onLayout: (next) => useWorkspace.getState().setLayout(next),
        onError: (error) => {
          useWorkspace.getState().finishTurn();
          setSavedMessage(refusalWords(error));
          // A view whose layout moved on can be checked again; any other refusal is final until the documents change.
          if (error.code === "pattern_refused" && error.issues[0]?.path === "template_changed") setStaleId(id);
        },
        onDone: () => {
          useWorkspace.getState().finishTurn();
          void loadPatterns(); // its use count moved
        },
      },
      { signal: abort.current.signal },
    );
  }, [loadPatterns]);

  const checkAgain = useCallback(
    async (id: string) => {
      setSavedMessage(null);
      setStaleId(null);
      const result = await reverifyPattern(id);
      if (!result.ok) {
        setSavedMessage(refusalWords(result.error));
        return;
      }
      await loadPatterns();
      await showView(id); // it is current now: show it
    },
    [loadPatterns, showView],
  );

  const removeView = useCallback(
    async (id: string) => {
      setSavedMessage(null);
      const result = await deletePattern(id);
      if (!result.ok) setSavedMessage(result.error.message);
      await loadPatterns();
    },
    [loadPatterns],
  );

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

  const ask = useCallback(async (override?: string) => {
    const message = (override ?? question).trim();
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
  const byRegion = useMemo(
    () =>
      placeBlocksByRegion(
        layout,
        order.map((id) => blocks[id]).filter((b): b is UIBlock => b !== undefined),
        Object.values(workspaceBlocks),
      ),
    [layout, order, blocks, workspaceBlocks],
  );
  const placed = useMemo(() => flattenPlaced(byRegion), [byRegion]);

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

  // A view can be saved from a finished, answered turn (its id is the answer block's id) and not from a view that was itself
  // applied from a saved one. Which kinds the server will accept is the server's decision; it says why if it refuses.
  const turnId = turn === "idle" ? placed.chat.find((b) => b.type === "CitedSummary")?.id : undefined;
  const SAVEABLE = ["GraphView", "TraversalView", "ComparisonGrid", "ConceptMap"];
  const KIND_NAMES: Record<string, string> = {
    GraphView: "Connection graph",
    TraversalView: "Search path",
    ComparisonGrid: "Document comparison",
    ConceptMap: "Connection path",
  };
  const withSave = (block: UIBlock) => (
    <div key={block.id}>
      {renderBlock(block)}
      {turnId && block.meta.status === "ready" && SAVEABLE.includes(block.type) && block.id.startsWith(turnId) && (
        <SaveView
          defaultName={KIND_NAMES[block.type] ?? block.type}
          onSave={async (name): Promise<SaveOutcome> => {
            const result = await savePattern({ turnId, templateId: block.type, name });
            if (!result.ok) return { ok: false, message: result.error.message };
            await loadPatterns();
            return { ok: true };
          }}
        />
      )}
    </div>
  );

  // The studio shelf: the Studio's starters (they put a request in the question box), the saved views, and any block the layout places
  // there. A layout with no shelf region (a version 1 layout, or one from an older server) would leave these nowhere to
  // go, so they are shown after the graph area instead and the saved views stay reachable.
  const shelf = (
    <div className="space-y-4 p-1">
      <Studio
        onStart={(request, submit) => {
          setQuestion(request);
          if (submit) void ask(request);
          else requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[aria-label="Question"]')?.focus());
        }}
      />
      <SavedViews
        patterns={patterns}
        busy={turn === "streaming"}
        message={savedMessage}
        staleId={staleId}
        onApply={(id) => void showView(id)}
        onDelete={(id) => void removeView(id)}
        onReverify={(id) => void checkAgain(id)}
      />
      {byRegion.studio.shelf.map(withSave)}
    </div>
  );
  const studioHasShelf = layout.panels.some((p) => p.id === "studio" && p.regions.some((r) => r.id === "shelf"));

  const panels: Record<PanelId, Partial<Record<RegionId, React.ReactNode>>> = {
    sources: {
      main: (
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
    },
    chat: {
      main: (
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
            {byRegion.chat.main.map(withSave)}
            {traced && traced.meta.status !== "loading" && <TracePanel key={traced.id} turnId={traced.id} />}
            {turn === "failed" && placed.chat.length === 0 && turnError && (
              <p role="alert" className="text-sm text-red-700">
                {turnError.message}
              </p>
            )}
          </section>
        </div>
      ),
      secondary:
        byRegion.chat.secondary.length > 0 ? (
          <div className="space-y-4 p-1">{byRegion.chat.secondary.map(withSave)}</div>
        ) : undefined,
    },
    studio: {
      main: (
        <div className="space-y-4 p-1">
          {byRegion.studio.main.length === 0 ? (
            <p className="text-sm text-stone-500">
              {layout.origin === "prebuilt"
                ? "In Basic, graphs and connections appear below the answer. Adaptive gives them this space."
                : "Graphs and connections appear here when your question needs them."}
            </p>
          ) : (
            byRegion.studio.main.map(withSave)
          )}
          {!studioHasShelf && shelf}
        </div>
      ),
      shelf: studioHasShelf ? shelf : undefined,
    },
  };

  // A region this screen gives no content of its own (a component may ask for any region of any panel) still shows the
  // blocks placed in it, so a validated placement is never drawn nowhere.
  for (const panel of layout.panels) {
    for (const region of panel.regions) {
      const content = panels[panel.id];
      if (content[region.id] === undefined && byRegion[panel.id][region.id].length > 0) {
        content[region.id] = <div className="space-y-4 p-1">{byRegion[panel.id][region.id].map(withSave)}</div>;
      }
    }
  }

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
