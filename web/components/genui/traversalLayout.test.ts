import { describe, expect, it } from "vitest";

import { columnLayout } from "./traversalLayout";

describe("columnLayout", () => {
  it("puts the seeds in the left column and the others in the right, each top to bottom in the order given", () => {
    const layout = columnLayout(["a", "b"], ["x", "y", "z"]);
    const by = Object.fromEntries(layout.nodes.map((n) => [n.id, n]));
    expect(by.a!.column).toBe("left");
    expect(by.x!.column).toBe("right");
    expect(by.a!.x).toBeLessThan(by.x!.x);
    expect(by.a!.y).toBeLessThan(by.b!.y);
    expect(by.x!.y).toBeLessThan(by.y!.y);
    expect(by.y!.y).toBeLessThan(by.z!.y);
  });

  it("is deterministic: the same input draws the same picture", () => {
    expect(columnLayout(["a", "b"], ["x"])).toEqual(columnLayout(["a", "b"], ["x"]));
  });

  it("never lets two neighbours in a column touch, at the largest sizes a block may have (10 seeds, 40 nodes)", () => {
    const seeds = Array.from({ length: 10 }, (_, i) => `s${i}`);
    const others = Array.from({ length: 30 }, (_, i) => `o${i}`);
    const layout = columnLayout(seeds, others);
    for (const column of ["left", "right"] as const) {
      const ys = layout.nodes.filter((n) => n.column === column).map((n) => n.y);
      for (let i = 1; i < ys.length; i += 1) expect(ys[i]! - ys[i - 1]!).toBeGreaterThanOrEqual(2 * layout.nodeRadius + 4);
    }
    expect(layout.nodes.every((n) => n.y >= layout.nodeRadius && n.y <= layout.height - layout.nodeRadius)).toBe(true);
  });

  it("centres a short column against a tall one, and handles no nodes", () => {
    const layout = columnLayout(["a"], ["x", "y", "z"]);
    expect(layout.nodes.find((n) => n.id === "a")!.y).toBe(layout.height / 2);
    expect(columnLayout([], []).nodes).toEqual([]);
  });
});
