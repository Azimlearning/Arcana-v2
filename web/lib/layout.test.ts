import type { LayoutSpec } from "@arcana/schema";
import { describe, expect, it } from "vitest";

import { isLayoutSpec, panelOf } from "./layout";

const GOOD: LayoutSpec = {
  version: 1,
  origin: "adaptive",
  mode: "research",
  panels: [
    { id: "sources", width: 20 },
    { id: "chat", width: 45 },
    { id: "studio", width: 35 },
  ],
  placements: [
    { blockId: "a", panel: "chat", order: 0 },
    { blockId: "b", panel: "studio", order: 0 },
  ],
};

const damaged = (change: (layout: Record<string, unknown>) => void) => {
  const copy = JSON.parse(JSON.stringify(GOOD)) as Record<string, unknown>;
  change(copy);
  return copy;
};

describe("isLayoutSpec", () => {
  it("accepts a well-formed layout", () => {
    expect(isLayoutSpec(GOOD)).toBe(true);
  });

  it("rejects what it cannot read: an unknown version, a bad shape, or widths that do not add up", () => {
    const bad: Array<(l: Record<string, unknown>) => void> = [
      (l) => (l.version = 2),
      (l) => (l.origin = "learned"),
      (l) => (l.mode = "dashboard"),
      (l) => (l.panels = "wide"),
      (l) => ((l.panels as Array<{ width: number }>)[0]!.width = 21),
      (l) => ((l.panels as Array<{ width: number }>)[0]!.width = 20.5),
      (l) => ((l.panels as Array<{ id: string }>)[0]!.id = "chat"), // a duplicate panel id
      (l) => ((l.panels as Array<{ id: string }>)[1]!.id = "sidebar"),
      (l) => (l.panels = (l.panels as unknown[]).filter((_, i) => i !== 1)), // no chat panel
      (l) => ((l.placements as Array<{ panel: string }>)[0]!.panel = "nowhere"),
      (l) => ((l.placements as Array<{ blockId: string }>)[1]!.blockId = "a"), // a block placed twice
      (l) => ((l.placements as Array<{ order: number }>)[0]!.order = -1),
      (l) => (l.placements = [null]),
    ];
    for (const change of bad) expect(isLayoutSpec(damaged(change))).toBe(false);
    expect(isLayoutSpec(null)).toBe(false);
    expect(isLayoutSpec("layout")).toBe(false);
    expect(isLayoutSpec({})).toBe(false);
  });

  it("rejects what the server would: a narrow chat, a block in a hidden panel, a shared position, a mismatched origin", () => {
    const narrow = damaged((l) => {
      const panels = l.panels as Array<{ id: string; width: number }>;
      panels[0]!.width = 40;
      panels[1]!.width = 24;
      panels[2]!.width = 36;
    });
    expect(isLayoutSpec(narrow)).toBe(false);
    const inHidden = damaged((l) => {
      const panels = l.panels as Array<{ id: string; width: number }>;
      panels[2]!.width = 0;
      panels[1]!.width = 80; // studio hidden, but "b" is still placed there
    });
    expect(isLayoutSpec(inHidden)).toBe(false);
    const sharedPosition = damaged((l) => {
      (l.placements as Array<{ panel: string; order: number }>)[1]!.panel = "chat";
    });
    expect(isLayoutSpec(sharedPosition)).toBe(false);
    expect(isLayoutSpec(damaged((l) => (l.origin = "prebuilt")))).toBe(false); // prebuilt with research
    expect(isLayoutSpec(damaged((l) => (l.mode = "basic")))).toBe(false); // adaptive with basic
  });

  it("rejects a layout whose chat panel is hidden", () => {
    const hidden = damaged((l) => {
      (l.panels as Array<{ id: string; width: number }>).forEach((p) => (p.width = p.id === "chat" ? 0 : 50));
    });
    expect(isLayoutSpec(hidden)).toBe(false);
  });
});

describe("panelOf", () => {
  it("is where the layout places the block, and chat for anything unplaced or with no layout", () => {
    expect(panelOf(GOOD, "b")).toBe("studio");
    expect(panelOf(GOOD, "a")).toBe("chat");
    expect(panelOf(GOOD, "never-placed")).toBe("chat");
    expect(panelOf(null, "b")).toBe("chat");
  });
});
