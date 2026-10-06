// The client's side of LayoutSpec (level 2). The server validates a layout before it sends it; the client still
// checks the shape of whatever it receives, because it must never apply something it cannot read. A layout that
// fails the check is ignored and the client keeps the one it has, so a newer server cannot break an older client.

import type { LayoutSpec, PanelId } from "@arcana/schema";

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
