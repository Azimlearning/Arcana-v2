// The client's side of LayoutSpec (level 2). The server validates a layout before it sends it; the client still
// checks the shape of whatever it receives, because it must never apply something it cannot read. A layout that
// fails the check is ignored and the client keeps the one it has, so a newer server cannot break an older client.

import type { LayoutMode, LayoutOrigin, LayoutSpec, PanelId, RegionId, SplitDirection, UIBlock } from "@arcana/schema";

/** The layout version this client draws. A version 1 layout (no regions) is read as this one (`readLayout`). */
export const SUPPORTED_LAYOUT_VERSION = 2;

/** The chat panel is never narrower than this (the server enforces the same). */
export const MIN_CHAT_WIDTH = 25;

// Records, not arrays, so a member added to the schema's union fails typecheck until it is added here.
const PANELS: Record<PanelId, true> = { sources: true, chat: true, studio: true };
const MODES: Record<LayoutMode, true> = { basic: true, research: true, exploration: true };
const ORIGINS: Record<LayoutOrigin, true> = { prebuilt: true, adaptive: true };
const REGIONS: Record<RegionId, true> = { main: true, secondary: true, shelf: true };
const DIRECTIONS: Record<SplitDirection, true> = { rows: true, columns: true };
const isKey = (set: Record<string, true>, value: unknown) => typeof value === "string" && Object.hasOwn(set, value);
const isPanel = (value: unknown): value is PanelId => isKey(PANELS, value);
const isWhole = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value);

/**
 * What a layout of this client's version (or version 1) must look like to be drawn. Version 1 has no regions; it is read
 * as one `main` region in every panel, which is what the server does too (a shared fixture is read by both tests).
 * Returns the layout, upgraded, or null when it cannot be read.
 */
export function readLayout(value: unknown): LayoutSpec | null {
  if (typeof value !== "object" || value === null) return null;
  const layout = value as Record<string, unknown>;
  if (layout.version === 1 && Array.isArray(layout.panels) && Array.isArray(layout.placements)) {
    const upgraded = {
      ...layout,
      version: SUPPORTED_LAYOUT_VERSION,
      panels: layout.panels.map((p) =>
        typeof p === "object" && p !== null ? { ...p, direction: "rows", regions: [{ id: "main", size: 100 }] } : p,
      ),
      placements: layout.placements.map((p) => (typeof p === "object" && p !== null ? { ...p, region: "main" } : p)),
    };
    return isLayoutSpec(upgraded) ? upgraded : null;
  }
  return isLayoutSpec(value) ? value : null;
}

export function isLayoutSpec(value: unknown): value is LayoutSpec {
  if (typeof value !== "object" || value === null) return false;
  const layout = value as Record<string, unknown>;
  if (layout.version !== SUPPORTED_LAYOUT_VERSION) return false;
  if (!isKey(ORIGINS, layout.origin) || !isKey(MODES, layout.mode)) return false;
  if ((layout.origin === "prebuilt") !== (layout.mode === "basic")) return false; // the two go together
  if (!Array.isArray(layout.panels) || !Array.isArray(layout.placements)) return false;

  const widths = new Map<string, number>();
  const regions = new Map<string, Map<string, number>>();
  let total = 0;
  for (const panel of layout.panels as unknown[]) {
    if (typeof panel !== "object" || panel === null) return false;
    const { id, width, direction, regions: parts } = panel as Record<string, unknown>;
    if (!isPanel(id) || widths.has(id) || !isWhole(width) || width < 0 || width > 100) return false;
    if (!isKey(DIRECTIONS, direction) || !Array.isArray(parts) || parts.length === 0) return false;
    const sizes = new Map<string, number>();
    let share = 0;
    for (const part of parts as unknown[]) {
      if (typeof part !== "object" || part === null) return false;
      const { id: regionId, size } = part as Record<string, unknown>;
      if (!isKey(REGIONS, regionId) || sizes.has(regionId as string) || !isWhole(size) || size < 0 || size > 100) {
        return false;
      }
      sizes.set(regionId as string, size);
      share += size;
    }
    if (share !== 100) return false;
    widths.set(id, width);
    regions.set(id, sizes);
    total += width;
  }
  if (total !== 100 || (widths.get("chat") ?? 0) < MIN_CHAT_WIDTH) return false;

  const placed = new Set<string>();
  const positions = new Set<string>();
  for (const placement of layout.placements as unknown[]) {
    if (typeof placement !== "object" || placement === null) return false;
    const { blockId, panel, region, order } = placement as Record<string, unknown>;
    if (typeof blockId !== "string" || !blockId || placed.has(blockId)) return false;
    if (!isPanel(panel) || !isKey(REGIONS, region) || !isWhole(order) || order < 0) return false;
    if ((widths.get(panel) ?? 0) === 0) return false; // a hidden panel (or one not in the layout) holds nothing
    if ((regions.get(panel)?.get(region as string) ?? 0) === 0) return false; // a missing or empty region holds nothing
    if (positions.has(`${panel}:${region}:${order}`)) return false;
    positions.add(`${panel}:${region}:${order}`);
    placed.add(blockId);
  }
  return true;
}

/** The panel a block is shown in: where the layout places it, else the chat panel (arrival order). */
export function panelOf(layout: LayoutSpec | null, blockId: string): PanelId {
  return layout?.placements.find((p) => p.blockId === blockId)?.panel ?? "chat";
}

/** The id of the source list the server shows before any question (the prebuilt layout places it in `sources`). */
export const WORKSPACE_SOURCES_ID = "workspace-sources";

/**
 * The layout used until `/workspace` answers, and whenever it cannot be reached or read. It must equal the server's
 * `prebuilt_layout("workspace-sources")`: a test compares it with the committed fixture the server's test also reads
 * (`packages/schema/fixtures/prebuilt-layout.json`), so the two cannot drift apart.
 */
export const FALLBACK_LAYOUT: LayoutSpec = {
  version: 2,
  origin: "prebuilt",
  mode: "basic",
  panels: [
    { id: "sources", width: 20, direction: "rows", regions: [{ id: "main", size: 100 }] },
    { id: "chat", width: 60, direction: "columns", regions: [{ id: "main", size: 100 }] },
    {
      id: "studio",
      width: 20,
      direction: "rows",
      regions: [
        { id: "main", size: 60 },
        { id: "shelf", size: 40 },
      ],
    },
  ],
  placements: [{ blockId: WORKSPACE_SOURCES_ID, panel: "sources", region: "main", order: 0 }],
};

export type PlacedBlocks = Record<PanelId, UIBlock[]>;
export type PlacedByRegion = Record<PanelId, Record<RegionId, UIBlock[]>>;

/** The regions in the order they are drawn and flattened (the schema's closed list). */
export const REGION_ORDER: readonly RegionId[] = ["main", "secondary", "shelf"];

/**
 * Which blocks each region of each panel shows. The rules (all tested):
 *  - a region shows the blocks the layout places in it, in `order`;
 *  - a placement whose region its panel does not have is shown in the panel's first region (a validated layout never
 *    does this; it keeps a block visible if one ever arrives);
 *  - a placement for a block the client does not have is ignored;
 *  - a turn block with no placement is shown in chat, after the placed ones, in arrival order;
 *  - a workspace block (the source list from `/workspace`) is shown only where a layout places it;
 *  - in the prebuilt (Basic) layout the turn's own source list is not shown: the workspace's is already in the
 *    sources panel and would only repeat it.
 */
export function placeBlocksByRegion(
  layout: LayoutSpec,
  turnBlocks: readonly UIBlock[],
  workspaceBlocks: readonly UIBlock[] = [],
): PlacedByRegion {
  const empty = (): Record<RegionId, UIBlock[]> => ({ main: [], secondary: [], shelf: [] });
  const placed: PlacedByRegion = { sources: empty(), chat: empty(), studio: empty() };
  const turn = layout.origin === "prebuilt" ? turnBlocks.filter((b) => b.type !== "SourceList") : turnBlocks;
  const byId = new Map<string, UIBlock>([...workspaceBlocks, ...turn].map((b) => [b.id, b]));
  const specs = new Map(layout.panels.map((p) => [p.id, p]));

  const positions = new Map(layout.placements.map((p) => [p.blockId, p]));
  for (const placement of [...layout.placements].sort((a, b) => a.order - b.order)) {
    const block = byId.get(placement.blockId);
    if (!block) continue;
    const regions = specs.get(placement.panel)?.regions ?? [];
    const region = regions.some((r) => r.id === placement.region) ? placement.region : (regions[0]?.id ?? "main");
    placed[placement.panel][region].push(block);
  }
  for (const block of turn) {
    if (!positions.has(block.id)) placed.chat.main.push(block);
  }
  return placed;
}

/** The same blocks by panel only: every region of a panel in drawing order. */
export function placeBlocks(
  layout: LayoutSpec,
  turnBlocks: readonly UIBlock[],
  workspaceBlocks: readonly UIBlock[] = [],
): PlacedBlocks {
  return flattenPlaced(placeBlocksByRegion(layout, turnBlocks, workspaceBlocks));
}

/** A panel's blocks with its regions in drawing order. */
export function flattenPlaced(byRegion: PlacedByRegion): PlacedBlocks {
  const flat = (panel: PanelId) => REGION_ORDER.flatMap((region) => byRegion[panel][region]);
  return { sources: flat("sources"), chat: flat("chat"), studio: flat("studio") };
}
