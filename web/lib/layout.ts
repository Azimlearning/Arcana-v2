// The client's side of LayoutSpec (level 2). The server validates a layout before it sends it; the client still
// checks the shape of whatever it receives, because it must never apply something it cannot read. A layout that
// fails the check is ignored and the client keeps the one it has, so a newer server cannot break an older client.

import type { LayoutSpec, PanelId, UIBlock } from "@arcana/schema";

/** The only layout version this client understands. */
export const SUPPORTED_LAYOUT_VERSION = 1;

/** The chat panel is never narrower than this (the server enforces the same). */
export const MIN_CHAT_WIDTH = 25;

const PANELS: readonly PanelId[] = ["sources", "chat", "studio"];
const isPanel = (value: unknown): value is PanelId => PANELS.includes(value as PanelId);
const isWhole = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value);

export function isLayoutSpec(value: unknown): value is LayoutSpec {
  if (typeof value !== "object" || value === null) return false;
  const layout = value as Record<string, unknown>;
  if (layout.version !== SUPPORTED_LAYOUT_VERSION) return false;
  if (layout.origin !== "prebuilt" && layout.origin !== "adaptive") return false;
  if (layout.mode !== "basic" && layout.mode !== "research" && layout.mode !== "exploration") return false;
  if ((layout.origin === "prebuilt") !== (layout.mode === "basic")) return false; // the two go together
  if (!Array.isArray(layout.panels) || !Array.isArray(layout.placements)) return false;

  const widths = new Map<string, number>();
  let total = 0;
  for (const panel of layout.panels as unknown[]) {
    if (typeof panel !== "object" || panel === null) return false;
    const { id, width } = panel as Record<string, unknown>;
    if (!isPanel(id) || widths.has(id) || !isWhole(width) || width < 0 || width > 100) return false;
    widths.set(id, width);
    total += width;
  }
  if (total !== 100 || (widths.get("chat") ?? 0) < MIN_CHAT_WIDTH) return false;

  const placed = new Set<string>();
  const positions = new Set<string>();
  for (const placement of layout.placements as unknown[]) {
    if (typeof placement !== "object" || placement === null) return false;
    const { blockId, panel, order } = placement as Record<string, unknown>;
    if (typeof blockId !== "string" || !blockId || placed.has(blockId)) return false;
    if (!isPanel(panel) || !isWhole(order) || order < 0) return false;
    if ((widths.get(panel) ?? 0) === 0) return false; // a hidden panel (or one not in the layout) holds nothing
    if (positions.has(`${panel}:${order}`)) return false;
    positions.add(`${panel}:${order}`);
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
  version: 1,
  origin: "prebuilt",
  mode: "basic",
  panels: [
    { id: "sources", width: 20 },
    { id: "chat", width: 60 },
    { id: "studio", width: 20 },
  ],
  placements: [{ blockId: WORKSPACE_SOURCES_ID, panel: "sources", order: 0 }],
};

export type PlacedBlocks = Record<PanelId, UIBlock[]>;

/**
 * Which blocks each panel shows. The rules (all tested):
 *  - a panel shows the blocks the layout places in it, in `order`;
 *  - a placement for a block the client does not have is ignored;
 *  - a turn block with no placement is shown in chat, after the placed ones, in arrival order;
 *  - a workspace block (the source list from `/workspace`) is shown only where a layout places it;
 *  - in the prebuilt (Basic) layout the turn's own source list is not shown: the workspace's is already in the
 *    sources panel and would only repeat it.
 */
export function placeBlocks(
  layout: LayoutSpec,
  turnBlocks: readonly UIBlock[],
  workspaceBlocks: readonly UIBlock[] = [],
): PlacedBlocks {
  const placed: PlacedBlocks = { sources: [], chat: [], studio: [] };
  const turn = layout.origin === "prebuilt" ? turnBlocks.filter((b) => b.type !== "SourceList") : turnBlocks;
  const byId = new Map<string, UIBlock>([...workspaceBlocks, ...turn].map((b) => [b.id, b]));

  const positions = new Map(layout.placements.map((p) => [p.blockId, p]));
  for (const placement of [...layout.placements].sort((a, b) => a.order - b.order)) {
    const block = byId.get(placement.blockId);
    if (block) placed[placement.panel].push(block);
  }
  for (const block of turn) {
    if (!positions.has(block.id)) placed.chat.push(block);
  }
  return placed;
}
