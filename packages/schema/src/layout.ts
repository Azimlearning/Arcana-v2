// LayoutSpec: where the blocks of a turn go on the screen. Level 2 of the generative UI (D-27): the Composer, and
// only the Composer, decides it, and the client applies it. It is data, never code or markup.
//
// It is built to grow. Panels are a list, not fixed fields; `version` lets a later shape be refused by a client that
// does not know it; `origin` says whether the layout is the fixed starting one or one composed for a turn; and a
// component's placement is a hint kept on its catalog entry, so a new component needs no change here. A client that
// meets a spec it cannot read ignores it and keeps the layout it has.

/** The layout shapes the Composer chooses between. `basic` is the fixed starting layout. */
export type LayoutMode = "basic" | "research" | "exploration";

/** `prebuilt` is the fixed workspace shown before any question; `adaptive` is composed for a turn's blocks. */
export type LayoutOrigin = "prebuilt" | "adaptive";

/** The regions of the workspace. A new region is added here, in the Composer's width rules, and in the shell. */
export type PanelId = "sources" | "chat" | "studio";

/** One region and its share of the width, as a whole number of percent. */
export interface PanelSpec {
  id: PanelId;
  /** @int */
  width: number;
}

/** A block's place: which panel, and its position in that panel (0 first). */
export interface Placement {
  blockId: string;
  panel: PanelId;
  /** @int */
  order: number;
}

/**
 * The whole layout. Server guarantees: `version` is 1; panel ids are unique; widths are whole numbers from 0 to
 * 100 that sum to 100; the chat panel is present and at least 25 wide; a panel of width 0 has no placements;
 * every placement names a distinct block of the turn; orders are unique within a panel. A block with no placement
 * is shown in the chat panel in arrival order. The schema cannot say so; the server validator does.
 */
export interface LayoutSpec {
  /** @int */
  version: number;
  origin: LayoutOrigin;
  mode: LayoutMode;
  panels: PanelSpec[];
  placements: Placement[];
}
