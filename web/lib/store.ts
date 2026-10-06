// Client state for the workspace (Zustand). Blocks are stored by id: a block event whose id is
// already present REPLACES that block in place (loading -> ready), which is the wire's update model.

import type { ErrorEnvelope, IngestResponse, LayoutSpec, UIBlock } from "@arcana/schema";
import { create } from "zustand";

export type TurnStatus = "idle" | "streaming" | "failed";

/** The block as an error-state block carrying `error`. Used when the stream dies mid-turn. */
export function toErrorBlock(block: UIBlock, error: ErrorEnvelope): UIBlock {
  const meta = { ...block.meta, status: "error" as const, error };
  // An error block is a placeholder: it carries no content, whatever the type held before.
  switch (block.type) {
    case "CitedSummary":
      return { ...block, meta, data: { segments: [], citations: [] } };
    case "SourceList":
      return { ...block, meta, data: { documents: [] } };
    case "GraphView":
      return { ...block, meta, data: { nodes: [], edges: [], citations: [] } };
    case "ComparisonGrid":
      return { ...block, meta, data: { dimensions: [], rows: [], citations: [] } };
    case "ConceptMap":
      return { ...block, meta, data: { steps: [], citations: [] } };
  }
}

interface WorkspaceState {
  documents: IngestResponse[];
  /** Block ids in first-seen order, and the blocks themselves. */
  order: string[];
  blocks: Record<string, UIBlock>;
  /** The layout the server sent for this turn's blocks, or null before one arrives (then every block is in chat). */
  layout: LayoutSpec | null;
  turn: TurnStatus;
  turnError: ErrorEnvelope | null;

  addDocument: (doc: IngestResponse) => void;
  startTurn: () => void;
  upsertBlock: (block: UIBlock) => void;
  setLayout: (layout: LayoutSpec) => void;
  /** End the turn with an error: any block still loading or partial becomes an error block. */
  failTurn: (error: ErrorEnvelope) => void;
  finishTurn: () => void;
}

export const useWorkspace = create<WorkspaceState>()((set) => ({
  documents: [],
  order: [],
  blocks: {},
  layout: null,
  turn: "idle",
  turnError: null,

  addDocument: (doc) =>
    set((s) => ({ documents: [...s.documents.filter((d) => d.docId !== doc.docId), doc] })),

  // A new question starts a fresh answer panel; the documents stay.
  startTurn: () => set({ order: [], blocks: {}, layout: null, turn: "streaming", turnError: null }),

  upsertBlock: (block) =>
    set((s) => ({
      order: s.order.includes(block.id) ? s.order : [...s.order, block.id],
      blocks: { ...s.blocks, [block.id]: block },
    })),

  setLayout: (layout) => set({ layout }),

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
