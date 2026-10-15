// Client state for the workspace (Zustand). Blocks are stored by id: a block event whose id is
// already present REPLACES that block in place (loading -> ready), which is the wire's update model.

import type { ErrorEnvelope, IngestResponse, LayoutSpec, SavedPattern, UIBlock, WorkspaceResponse } from "@arcana/schema";
import { create } from "zustand";

import { FALLBACK_LAYOUT, isLayoutSpec } from "./layout";

export type TurnStatus = "idle" | "streaming" | "failed";
export type LayoutChoice = "basic" | "adaptive";

/** The layout in force: the adaptive one if it is chosen and exists, otherwise the prebuilt one. */
export function activeLayout(s: {
  layouts: { prebuilt: LayoutSpec; adaptive: LayoutSpec | null };
  layoutChoice: LayoutChoice;
}): LayoutSpec {
  return s.layoutChoice === "adaptive" && s.layouts.adaptive ? s.layouts.adaptive : s.layouts.prebuilt;
}

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
    case "TraversalView":
      return { ...block, meta, data: { seeds: [], nodes: [], steps: [], reached: [], citations: [], stepsLeftOut: 0 } };
    case "ComparisonGrid":
      return { ...block, meta, data: { dimensions: [], rows: [], citations: [] } };
    case "ConceptMap":
      return { ...block, meta, data: { steps: [], citations: [] } };
    case "ConceptPage":
      return {
        ...block,
        meta,
        data: {
          page: { id: "", label: "" },
          kind: null,
          aliases: [],
          passages: 0,
          documents: 0,
          definitions: [],
          links: [],
          linksLeftOut: 0,
          claims: [],
          mentions: [],
          mentionsLeftOut: 0,
          citations: [],
          mastery: null,
        },
      };
    case "NotesGraph":
      return { ...block, meta, data: { focusId: null, query: "", nodes: [], edges: [], nodesLeftOut: 0 } };
    case "QuizCard":
      return { ...block, meta, data: { focusId: null, items: [], skipped: 0 } };
    case "VerifiedLab":
      // An error block carries no code, whatever the lab held before.
      return {
        ...block,
        meta,
        data: {
          labId: "",
          contractId: "",
          title: "",
          parameters: [],
          sweep: "",
          gridSteps: 0,
          outputLabel: "",
          source: "",
          sourceSha256: "",
          templateVersion: 0,
          citations: [],
          checked: { referenceCases: 0, properties: 0, fuzzCases: 0, gridPoints: 0 },
        },
      };
    case "WritingDraft":
      return { ...block, meta, data: { title: "", sections: [], citations: [], bibliography: [] } };
    case "StudySet":
      return { ...block, meta, data: { kind: block.data.kind, focusId: null, items: [], summary: null, citations: [], skipped: 0 } };
    case "StudyPlan":
      return { ...block, meta, data: { asOf: block.data.asOf, items: [], ratedPages: 0, leftOut: 0 } };
    case "DocBrief":
      return {
        ...block,
        meta,
        data: { docId: "", docTitle: "", keyPoints: [], terms: [], actions: [], citations: [], claimsInDocument: 0, leftOut: 0 },
      };
  }
}

interface WorkspaceState {
  documents: IngestResponse[];
  /** Block ids in first-seen order, and the blocks themselves. */
  order: string[];
  blocks: Record<string, UIBlock>;
  /** The workspace's own blocks (the source list from `/workspace`), by id. They are not part of a turn. */
  workspaceBlocks: Record<string, UIBlock>;
  /**
   * The two layouts: the prebuilt (Basic) one, which is the fixed fallback until `/workspace` answers, and the
   * adaptive one the server composed for the current turn (null until it arrives, and cleared by a new question).
   */
  layouts: { prebuilt: LayoutSpec; adaptive: LayoutSpec | null };
  /** Which of the two is shown. Adaptive only while one exists. */
  layoutChoice: LayoutChoice;
  /** True once the user has chosen Basic: an adaptive layout then no longer takes over by itself. */
  pinned: boolean;
  turn: TurnStatus;
  turnError: ErrorEnvelope | null;
  /** The user's saved views, as the server last listed them. */
  patterns: SavedPattern[];

  addDocument: (doc: IngestResponse) => void;
  startTurn: () => void;
  upsertBlock: (block: UIBlock) => void;
  /** Apply `/workspace`: its prebuilt layout and blocks. A layout this client cannot read is ignored. */
  setPatterns: (patterns: SavedPattern[]) => void;
  setWorkspace: (workspace: WorkspaceResponse) => void;
  /** An adaptive layout from the stream. Anything that is not a readable adaptive layout is ignored. */
  setLayout: (layout: LayoutSpec) => void;
  /** The user's choice. Basic pins it; Adaptive un-pins it (and is a no-op while there is no adaptive layout). */
  chooseLayout: (choice: LayoutChoice) => void;
  /** End the turn with an error: any block still loading or partial becomes an error block. */
  failTurn: (error: ErrorEnvelope) => void;
  finishTurn: () => void;
}

export const useWorkspace = create<WorkspaceState>()((set) => ({
  documents: [],
  order: [],
  blocks: {},
  workspaceBlocks: {},
  layouts: { prebuilt: FALLBACK_LAYOUT, adaptive: null },
  layoutChoice: "basic",
  pinned: false,
  turn: "idle",
  turnError: null,
  patterns: [],

  addDocument: (doc) =>
    set((s) => ({ documents: [...s.documents.filter((d) => d.docId !== doc.docId), doc] })),

  // A new question starts a fresh answer panel and drops the previous turn's adaptive layout (back to Basic until the
  // next one arrives); the documents, the workspace and a pinned choice stay.
  startTurn: () =>
    set((s) => ({
      order: [],
      blocks: {},
      layouts: { ...s.layouts, adaptive: null },
      layoutChoice: "basic",
      turn: "streaming",
      turnError: null,
    })),

  upsertBlock: (block) =>
    set((s) => ({
      order: s.order.includes(block.id) ? s.order : [...s.order, block.id],
      blocks: { ...s.blocks, [block.id]: block },
    })),

  setPatterns: (patterns) => set({ patterns }),

  setWorkspace: (workspace) =>
    set((s) => ({
      workspaceBlocks: Object.fromEntries(workspace.blocks.map((b) => [b.id, b])),
      layouts: isLayoutSpec(workspace.layout) && workspace.layout.origin === "prebuilt"
        ? { ...s.layouts, prebuilt: workspace.layout }
        : s.layouts,
    })),

  setLayout: (layout) =>
    set((s) =>
      isLayoutSpec(layout) && layout.origin === "adaptive"
        ? { layouts: { ...s.layouts, adaptive: layout }, layoutChoice: s.pinned ? s.layoutChoice : "adaptive" }
        : {},
    ),

  chooseLayout: (choice) =>
    set((s) => {
      if (choice === "basic") return { layoutChoice: "basic", pinned: true };
      return s.layouts.adaptive ? { layoutChoice: "adaptive", pinned: false } : {};
    }),

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
