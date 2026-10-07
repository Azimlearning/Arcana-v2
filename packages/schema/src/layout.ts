// LayoutSpec: where the blocks of a turn go on the screen. Level 2 of the generative UI (D-27): the Composer, and
// only the Composer, decides it, and the client applies it. It is data, never code or markup.
//
// It is built to grow. Panels are a list, not fixed fields; `version` lets a later shape be refused by a client that
// does not know it; `origin` says whether the layout is the fixed starting one or one composed for a turn; and a
// component's placement is a hint kept on its catalog entry, so a new component needs no change here. A client that
// meets a spec it cannot read ignores it and keeps the layout it has.
//
// Version 2 (D-32) divides a panel into regions: one level of split, in one direction, over a closed list of region
// roles. A version 1 spec has no regions and is read as one `main` region in every panel.

/** The layout shapes the Composer chooses between. `basic` is the fixed starting layout. */
export type LayoutMode = "basic" | "research" | "exploration";

/** `prebuilt` is the fixed workspace shown before any question; `adaptive` is composed for a turn's blocks. */
export type LayoutOrigin = "prebuilt" | "adaptive";

/** The regions of the workspace. A new region is added here, in the Composer's width rules, and in the shell. */
export type PanelId = "sources" | "chat" | "studio";

/**
 * The roles a part of a panel can have. `main` is the panel's first area; `secondary` is the area a split opens
 * beside or below it (the middle section when a quiz or a study session sits next to the answer); `shelf` is the area
 * for saved outputs (the Studio shelf). A new role is added here, in the Composer's rules and in the shell.
 */
export type RegionId = "main" | "secondary" | "shelf";

/** How a panel's regions are laid out: `rows` stacks them top to bottom, `columns` puts them side by side. */
export type SplitDirection = "rows" | "columns";

/** One part of a panel and its share of the panel along the split direction, as a whole number of percent. */
export interface RegionSpec {
  id: RegionId;
  /** @int */
  size: number;
}

/** One panel and its share of the width, as a whole number of percent, divided into regions. */
export interface PanelSpec {
  id: PanelId;
  /** @int */
  width: number;
  direction: SplitDirection;
  regions: RegionSpec[];
}

/** A block's place: which panel and region, and its position in that region (0 first). */
export interface Placement {
  blockId: string;
  panel: PanelId;
  region: RegionId;
  /** @int */
  order: number;
}

/**
 * The whole layout. Server guarantees: `version` is 2; panel ids are unique; widths are whole numbers from 0 to
 * 100 that sum to 100; the chat panel is present, at least 25 wide and has a `main` region; a panel of width 0 has no placements; every
 * panel has at least one region, region ids are unique within a panel, sizes are whole numbers from 0 to 100 that sum
 * to 100, and a region of size 0 holds no placements; every placement names a distinct block of the turn and a region
 * its panel has; orders are unique within a region. A block with no placement is shown in the chat panel in arrival
 * order. The schema cannot say so; the server validator does.
 */
export interface LayoutSpec {
  /** @int */
  version: number;
  origin: LayoutOrigin;
  mode: LayoutMode;
  panels: PanelSpec[];
  placements: Placement[];
}
