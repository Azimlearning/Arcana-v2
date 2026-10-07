// UIBlock: the typed payload an agent emits and a component renders. The wire carries data only, with ONE declared exception: `VerifiedLab.source`,
// a function's text that only the verifier can mint (D-10, D-36), inert until the web host places it in a sandboxed iframe.
//
// Adding a variant is a fixed sequence (preflight 5):
//   1. Add its *Data interface to payloads.ts and a variant interface here.
//   2. Add the variant to the UIBlock union below.
//   3. `pnpm codegen`, then `pnpm codegen:check` must pass.
//   4. Server validator handles it; web registry gets an entry and a component with all four states.
//   5. Write the component's structural precondition down (constraint 7).

import type { ErrorEnvelope } from "./errors";
import type {
  CitedSummaryData,
  ComparisonGridData,
  ConceptMapData,
  ConceptPageData,
  GraphViewData,
  NotesGraphData,
  QuizCardData,
  VerifiedLabData,
  SourceListData,
  TraversalViewData,
} from "./payloads";

/**
 * Lifecycle of a block on the wire. `empty`, `loading`, `partial`, `error` are the states every
 * component must render; `ready` is a complete block (the execution doc names only the four
 * render states, but a finished block needs a status too).
 *
 * Branch on `meta.status`, never on whether the arrays are empty. The server guarantees:
 *   - `empty`, `loading`, `error`: `data` has no segments and no citations (a placeholder), and
 *     `meta.error` is non-null if and only if the status is `error`;
 *   - `ready`: at least one segment, every segment cites at least one citation of this block, every
 *     citation resolves to a stored chunk, and `docTitle`, `page` and `quote` match that chunk;
 *   - `partial` (not emitted in P0): whatever is present is grounded the same way, but it may be short.
 * `empty` means nothing was found or the model declined: render "nothing found", not a failure.
 */
export type BlockStatus = "empty" | "loading" | "partial" | "ready" | "error";

export interface BlockMeta {
  status: BlockStatus;
  /** Why the block failed. Non-null if and only if status is "error". */
  error: ErrorEnvelope | null;
}

export interface CitedSummary {
  type: "CitedSummary";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: CitedSummaryData;
}

export interface SourceList {
  type: "SourceList";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: SourceListData;
}

export interface GraphView {
  type: "GraphView";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: GraphViewData;
}

export interface ComparisonGrid {
  type: "ComparisonGrid";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: ComparisonGridData;
}

export interface ConceptMap {
  type: "ConceptMap";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: ConceptMapData;
}

export interface TraversalView {
  type: "TraversalView";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: TraversalViewData;
}

// Codegen emits a discriminated union (Field(discriminator='type')) once there are 2+ variants.
/** One concept's page (M2, D-35): names, definitions, links, claims and backlinks, derived from the vault. */
export interface ConceptPage {
  type: "ConceptPage";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: ConceptPageData;
}

/** Pages and the links among them (M2, D-35): the vault's graph, local to a page or across the whole vault. */
export interface NotesGraph {
  type: "NotesGraph";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: NotesGraphData;
}

/** A quiz made from the vault's claims (Q1, D-35 A8): fill in the blanked concept name; the server checks the answer. */
export interface QuizCard {
  type: "QuizCard";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: QuizCardData;
}

/** A generated, verified lab (P4, D-36): the only block that carries code, and only code the verifier minted. */
export interface VerifiedLab {
  type: "VerifiedLab";
  /** Non-empty. Stable across updates: a later block with the same id replaces this one. */
  id: string;
  meta: BlockMeta;
  data: VerifiedLabData;
}

export type UIBlock =
  | CitedSummary
  | SourceList
  | GraphView
  | ComparisonGrid
  | ConceptMap
  | TraversalView
  | ConceptPage
  | NotesGraph
  | QuizCard
  | VerifiedLab;
