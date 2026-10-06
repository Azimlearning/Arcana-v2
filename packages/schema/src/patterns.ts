// Saved patterns: the user's own views, kept to be used again (D-31, stages 4 and 5). A pattern is a template and the
// parameters that re-bind its evidence, plus the layout it was shown in. It holds NO evidence: no block data, no
// quote, no document text. Applying one re-runs the template's preconditions on the evidence of the day, so a pattern
// can go stale (a document is gone, the template changed) and then refuses with a reason instead of showing anything.
// Strings only: there is no free-form JSON on the wire.

import type { LayoutMode } from "./layout";

/**
 * Where a pattern is in its life. `generated` and `verified` are for patterns that were produced and checked;
 * `saved` is one the user kept. The typed (data) UI of P2 only creates `saved` patterns (a pattern is saved from a
 * turn whose blocks all passed validation); `verified` is set again when a stale pattern is re-verified. Later phases
 * add states (cached, audited, promoted) behind the same field.
 */
export type PatternState = "generated" | "verified" | "saved";

/** One parameter: the name of one of the template's slots and its string values (entity labels or document ids). */
export interface PatternParam {
  key: string;
  values: string[];
}

export interface SavedPattern {
  /** A content hash of the template, its version, its parameters and the layout mode: the same view is one id. */
  id: string;
  /** The user's name for it. Plain text. */
  name: string;
  /** The catalog template this is a pattern of, for example "GraphView". */
  templateId: string;
  /** The template version the pattern was made with. When the template has moved on, the pattern is stale. */
  /** @int */
  templateVersion: number;
  params: PatternParam[];
  layoutMode: LayoutMode;
  state: PatternState;
  /** @int */
  useCount: number;
  createdAt: string;
  lastUsedAt: string | null;
}

/** POST /patterns: keep one view of a finished turn. `templateId` names which of the turn's views. */
export interface SavePatternRequest {
  turnId: string;
  templateId: string;
  name: string;
}

export interface PatternList {
  patterns: SavedPattern[];
}
