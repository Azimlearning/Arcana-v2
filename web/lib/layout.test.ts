import type { LayoutSpec, UIBlock } from "@arcana/schema";
import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { isLayoutSpec, panelOf, readLayout, FALLBACK_LAYOUT } from "./layout";

const GOOD: LayoutSpec = {
  version: 2,
  origin: "adaptive",
  mode: "research",
  panels: [
    { id: "sources", width: 20, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    { id: "chat", width: 45, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    { id: "studio", width: 35, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
  ],
  placements: [
    { blockId: "a", panel: "chat", region: "main" as const, order: 0 },
    { blockId: "b", panel: "studio", region: "main" as const, order: 0 },
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
      (l) => (l.version = 3),
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
      (l) => ((l.panels as Array<{ regions: unknown }>)[1]!.regions = []), // a panel has at least one region
      (l) => ((l.panels as Array<{ direction: string }>)[1]!.direction = "diagonal"),
      (l) => ((l.panels as Array<{ regions: Array<{ size: number }> }>)[1]!.regions[0]!.size = 60), // sizes must sum to 100
      (l) => ((l.panels as Array<{ regions: Array<{ id: string }> }>)[1]!.regions[0]!.id = "side"),
      (l) =>
        ((l.panels as Array<{ regions: Array<{ id: string; size: number }> }>)[1]!.regions = [
          { id: "main", size: 50 },
          { id: "main", size: 50 },
        ]), // a repeated region id
      (l) => ((l.placements as Array<{ region: string }>)[0]!.region = "shelf"), // the panel has no such region
      (l) => delete (l.placements as Array<{ region?: string }>)[0]!.region,
      (l) => ((l.panels as Array<{ regions: Array<{ id: string }> }>)[1]!.regions[0]!.id = "secondary"), // chat has no main
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


describe("the fixed fallback layout", () => {
  it("equals the committed fixture the server's prebuilt layout is also tested against", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const { FALLBACK_LAYOUT } = await import("./layout");
    // vitest runs from the web package, so the shared fixture is one level up
    const path = resolve(process.cwd(), "../packages/schema/fixtures/prebuilt-layout.json");
    expect(JSON.parse(readFileSync(path, "utf-8"))).toEqual(FALLBACK_LAYOUT);
  });

  it("is itself a layout the client accepts", async () => {
    const { FALLBACK_LAYOUT } = await import("./layout");
    expect(isLayoutSpec(FALLBACK_LAYOUT)).toBe(true);
  });
});

describe("placeBlocks", () => {
  const item = (id: string, type: "CitedSummary" | "SourceList" | "GraphView" = "CitedSummary") =>
    ({ type, id, meta: { status: "ready", error: null }, data: {} }) as unknown as UIBlock;

  const adaptive = (placements: LayoutSpec["placements"]): LayoutSpec => ({ ...GOOD, placements });

  it("puts each block in its placed panel, in order within the panel", async () => {
    const { placeBlocks } = await import("./layout");
    const placed = placeBlocks(
      adaptive([
        { blockId: "b", panel: "chat", region: "main" as const, order: 1 },
        { blockId: "a", panel: "chat", region: "main" as const, order: 0 },
        { blockId: "g", panel: "studio", region: "main" as const, order: 0 },
      ]),
      [item("a"), item("b"), item("g", "GraphView")],
    );
    expect(placed.chat.map((x) => x.id)).toEqual(["a", "b"]);
    expect(placed.studio.map((x) => x.id)).toEqual(["g"]);
    expect(placed.sources).toEqual([]);
  });

  it("ignores a placement for a block it does not have", async () => {
    const { placeBlocks } = await import("./layout");
    const placed = placeBlocks(adaptive([{ blockId: "ghost", panel: "studio", region: "main" as const, order: 0 }]), [item("a")]);
    expect(placed.studio).toEqual([]);
    expect(placed.chat.map((x) => x.id)).toEqual(["a"]); // and the real block is unplaced, so it goes to chat
  });

  it("shows an unplaced turn block in chat after the placed ones, in arrival order", async () => {
    const { placeBlocks } = await import("./layout");
    const placed = placeBlocks(adaptive([{ blockId: "c", panel: "chat", region: "main" as const, order: 0 }]), [item("x"), item("c"), item("y")]);
    expect(placed.chat.map((b) => b.id)).toEqual(["c", "x", "y"]);
  });

  it("shows a workspace block only where a layout places it", async () => {
    const { placeBlocks, FALLBACK_LAYOUT } = await import("./layout");
    const workspace = item("workspace-sources", "SourceList");
    expect(placeBlocks(FALLBACK_LAYOUT, [], [workspace]).sources.map((b) => b.id)).toEqual(["workspace-sources"]);
    const unplaced = placeBlocks(adaptive([]), [], [workspace]);
    expect(unplaced.sources).toEqual([]);
    expect(unplaced.chat).toEqual([]);
  });

  it("in the prebuilt layout every turn block is stacked in chat, except the turn's own source list", async () => {
    const { placeBlocks, FALLBACK_LAYOUT } = await import("./layout");
    const placed = placeBlocks(FALLBACK_LAYOUT, [item("a"), item("l", "SourceList"), item("g", "GraphView")]);
    expect(placed.chat.map((b) => b.id)).toEqual(["a", "g"]);
  });
});

describe("regions", () => {
  const split = (sizes: Array<[string, number]>, placed = "secondary") => {
    type Raw = { panels: Array<{ regions: unknown; direction: string }>; placements: Array<Record<string, unknown>> };
    const copy = JSON.parse(JSON.stringify(GOOD)) as Raw;
    copy.panels[1]!.regions = sizes.map(([id, size]) => ({ id, size }));
    copy.panels[1]!.direction = "columns";
    copy.placements[0]!.region = placed;
    return copy;
  };

  it("accepts a panel split into regions and a placement in one of them", () => {
    expect(isLayoutSpec(split([["main", 60], ["secondary", 40]]))).toBe(true);
  });

  it("refuses a placement in a region of size 0, which holds nothing", () => {
    expect(isLayoutSpec(split([["main", 100], ["secondary", 0]]))).toBe(false);
  });

  it("allows the same order in two regions of a panel but not twice in one", () => {
    const both = split([["main", 50], ["secondary", 50]]);
    both.placements.push({ blockId: "c", panel: "chat", region: "main", order: 0 });
    expect(isLayoutSpec(both)).toBe(true);
    both.placements[2]!.region = "secondary";
    expect(isLayoutSpec(both)).toBe(false);
  });
});

describe("readLayout", () => {
  const v1 = () => JSON.parse(readFileSync(resolve(process.cwd(), "../packages/schema/fixtures/layout-v1.json"), "utf-8"));

  it("reads the committed version 1 layout as one main region per panel (the server test reads the same file)", () => {
    expect(v1().version).toBe(1);
    const upgraded = readLayout(v1());
    // every panel is one main region; the current prebuilt layout also gives the studio its shelf
    expect(upgraded).toEqual({
      ...FALLBACK_LAYOUT,
      panels: FALLBACK_LAYOUT.panels.map((p) => ({ ...p, direction: "rows", regions: [{ id: "main", size: 100 }] })),
    });
  });

  it("passes a current layout through and refuses anything unreadable", () => {
    expect(readLayout(GOOD)).toEqual(GOOD);
    const damagedV1 = v1();
    damagedV1.placements[0].panel = "sidebar";
    for (const bad of [damagedV1, { version: 1, panels: "x", placements: [] }, { ...GOOD, version: 3 }, null, "layout"]) {
      expect(readLayout(bad)).toBeNull();
    }
  });
});

describe("placeBlocksByRegion", () => {
  const item = (id: string) => ({ type: "CitedSummary", id, meta: { status: "ready", error: null }, data: {} }) as unknown as UIBlock;
  const twoRegionChat = (placements: LayoutSpec["placements"]): LayoutSpec => ({
    ...GOOD,
    panels: GOOD.panels.map((p) =>
      p.id === "chat"
        ? { ...p, direction: "columns", regions: [{ id: "main", size: 60 }, { id: "secondary", size: 40 }] }
        : p,
    ),
    placements,
  });

  it("groups blocks by panel and region, in order within a region", async () => {
    const { placeBlocksByRegion, placeBlocks } = await import("./layout");
    const layout = twoRegionChat([
      { blockId: "a", panel: "chat", region: "main", order: 0 },
      { blockId: "b", panel: "chat", region: "secondary", order: 1 },
      { blockId: "c", panel: "chat", region: "secondary", order: 0 },
    ]);
    const blocks = [item("a"), item("b"), item("c")];
    const placed = placeBlocksByRegion(layout, blocks);
    expect(placed.chat.main.map((x) => x.id)).toEqual(["a"]);
    expect(placed.chat.secondary.map((x) => x.id)).toEqual(["c", "b"]);
    expect(placed.studio.main).toEqual([]);
    expect(placeBlocks(layout, blocks).chat.map((x) => x.id)).toEqual(["a", "c", "b"]); // by panel: regions in drawing order
  });

  it("shows a block whose region its panel does not have in the panel's first region, and unplaced blocks in chat's main", async () => {
    const { placeBlocksByRegion } = await import("./layout");
    const layout = { ...GOOD, placements: [{ blockId: "a", panel: "chat", region: "shelf", order: 0 }] } as LayoutSpec;
    const placed = placeBlocksByRegion(layout, [item("a"), item("z")]);
    expect(placed.chat.main.map((x) => x.id)).toEqual(["a", "z"]);
  });
});
