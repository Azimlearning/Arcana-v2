// Client state for the workspace (Zustand). Blocks are stored by id: a block event whose id is
// already present REPLACES that block in place (loading -> ready), which is the wire's update model.

import type { ErrorEnvelope, IngestResponse, UIBlock } from "@arcana/schema";
import { create } from "zustand";

export type TurnStatus = "idle" | "streaming" | "failed";

/** The block as an error-state block carrying `error`. Used when the stream dies mid-turn. */
export function toErrorBlock(block: UIBlock, error: ErrorEnvelope): UIBlock {
  return {
    ...block,
    meta: { ...block.meta, status: "error", error },
    data: { segments: [], citations: [] },
  };
}

interface WorkspaceState {
  documents: IngestResponse[];
  /** Block ids in first-seen order, and the blocks themselves. */
  order: string[];
  blocks: Record<string, UIBlock>;
  turn: TurnStatus;
  turnError: ErrorEnvelope | null;

  addDocument: (doc: IngestResponse) => void;
  startTurn: () => void;
  upsertBlock: (block: UIBlock) => void;
  /** End the turn with an error: any block still loading or partial becomes an error block. */
  failTurn: (error: ErrorEnvelope) => void;
  finishTurn: () => void;
}

export const useWorkspace = create<WorkspaceState>()((set) => ({
  documents: [],
  order: [],
  blocks: {},
  turn: "idle",
  turnError: null,

  addDocument: (doc) =>
    set((s) => ({ documents: [...s.documents.filter((d) => d.docId !== doc.docId), doc] })),

  // A new question starts a fresh answer panel; the documents stay.
  startTurn: () => set({ order: [], blocks: {}, turn: "streaming", turnError: null }),

  upsertBlock: (block) =>
    set((s) => ({
      order: s.order.includes(block.id) ? s.order : [...s.order, block.id],
      blocks: { ...s.blocks, [block.id]: block },
    })),

  failTurn: (error) =>
    set((s) => {
      const blocks = { ...s.blocks };
      for (const id of s.order) {
        const block = blocks[id];
        if (block && (block.meta.status === "loading" || block.meta.status === "partial")) {
          blocks[id] = toErrorBlock(block, error);
        }
      }
      return { blocks, turn: "failed", turnError: error };
    }),

  finishTurn: () => set((s) => (s.turn === "streaming" ? { turn: "idle" } : {})),
}));
