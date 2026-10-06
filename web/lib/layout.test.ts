import type { LayoutSpec, UIBlock } from "@arcana/schema";
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
        { blockId: "b", panel: "chat", order: 1 },
        { blockId: "a", panel: "chat", order: 0 },
        { blockId: "g", panel: "studio", order: 0 },
      ]),
      [item("a"), item("b"), item("g", "GraphView")],
    );
    expect(placed.chat.map((x) => x.id)).toEqual(["a", "b"]);
    expect(placed.studio.map((x) => x.id)).toEqual(["g"]);
    expect(placed.sources).toEqual([]);
  });

  it("ignores a placement for a block it does not have", async () => {
    const { placeBlocks } = await import("./layout");
    const placed = placeBlocks(adaptive([{ blockId: "ghost", panel: "studio", order: 0 }]), [item("a")]);
    expect(placed.studio).toEqual([]);
    expect(placed.chat.map((x) => x.id)).toEqual(["a"]); // and the real block is unplaced, so it goes to chat
  });

  it("shows an unplaced turn block in chat after the placed ones, in arrival order", async () => {
    const { placeBlocks } = await import("./layout");
    const placed = placeBlocks(adaptive([{ blockId: "c", panel: "chat", order: 0 }]), [item("x"), item("c"), item("y")]);
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
