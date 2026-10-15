"use client";

// The panes of the centre area (D-44): outputs the learner has opened beside the conversation, as in an assistant's side canvas. A pane
// holds a block the server already composed and validated, rendered through the registry like any other, with a Table view for blocks
// that have tabular facts. This is the viewer's arrangement only: the server's layout is still the default and the source of truth,
// the client never chooses or creates a component here, and closing every pane gives back exactly the layout the server sent.

import type { UIBlock } from "@arcana/schema";
import { useState } from "react";

import { renderBlock } from "@/components/genui/registry";
import { blockTitle, tablesOf } from "@/lib/tables";

import { TableView } from "./TableView";

export const MIN_SHARE = 30;
export const MAX_SHARE = 70;

function Pane({ block, onClose }: { block: UIBlock; onClose: (id: string) => void }) {
  const tables = tablesOf(block);
  const [view, setView] = useState<"block" | "table">("block");
  const title = blockTitle(block);
  return (
    <section aria-label={`Pane: ${title}`} data-pane={block.id} className="flex min-h-0 min-w-0 flex-col rounded-lg border border-stone-300 bg-white">
      <header className="flex flex-wrap items-center gap-2 border-b border-stone-200 px-3 py-1.5">
        <h2 className="min-w-0 flex-1 truncate text-sm font-medium text-stone-800">{title}</h2>
        {tables.length > 0 && (
          <div role="group" aria-label="View" className="flex gap-1">
            {(["block", "table"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={view === v}
                onClick={() => setView(v)}
                className={`rounded border px-2 py-0.5 text-xs ${view === v ? "border-emerald-600 bg-emerald-50 text-emerald-800" : "border-stone-300 text-stone-600"}`}
              >
                {v === "block" ? "Document" : "Table"}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={() => onClose(block.id)}
          aria-label={`Close pane: ${title}`}
          className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700 hover:bg-stone-50"
        >
          Close
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">{view === "table" && tables.length > 0 ? <TableView tables={tables} /> : renderBlock(block)}</div>
    </section>
  );
}

/** A draggable and keyboard-operable divider between the conversation and the panes. Its value is the panes' share of the width, in percent. */
export function PaneSeparator({ share, onShare, container }: { share: number; onShare: (n: number) => void; container: React.RefObject<HTMLElement | null> }) {
  const clamp = (n: number) => Math.min(MAX_SHARE, Math.max(MIN_SHARE, Math.round(n)));
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = container.current;
    if (!el) return;
    e.preventDefault();
    const rect = el.getBoundingClientRect();
    const move = (ev: PointerEvent) => onShare(clamp(((rect.right - ev.clientX) / rect.width) * 100));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the panes"
      aria-valuemin={MIN_SHARE}
      aria-valuemax={MAX_SHARE}
      aria-valuenow={share}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") {
          e.preventDefault();
          onShare(clamp(share + 5)); // moving the divider left gives the panes more room
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          onShare(clamp(share - 5));
        }
      }}
      className="hidden w-2 shrink-0 cursor-col-resize self-stretch rounded bg-stone-200 hover:bg-stone-400 focus:bg-emerald-500 focus:outline-none md:block"
    />
  );
}

export function Panes({
  panes,
  onClose,
  onCloseAll,
  focused,
  onToggleFocus,
}: {
  panes: UIBlock[];
  onClose: (id: string) => void;
  onCloseAll: () => void;
  focused: boolean;
  onToggleFocus: () => void;
}) {
  return (
    <aside aria-label="Panes" className="flex min-h-0 min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-stone-500" role="status">
          {panes.length} {panes.length === 1 ? "pane" : "panes"} open
        </p>
        <div className="flex gap-1">
          <button type="button" aria-pressed={focused} onClick={onToggleFocus} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
            {focused ? "Back to the conversation" : "Expand"}
          </button>
          <button type="button" onClick={onCloseAll} className="rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700">
            Close all
          </button>
        </div>
      </div>
      {panes.map((block) => (
        <Pane key={block.id} block={block} onClose={onClose} />
      ))}
    </aside>
  );
}
