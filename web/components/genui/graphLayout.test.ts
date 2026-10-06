import { describe, expect, it } from "vitest";

import { radialLayout } from "./graphLayout";

const ids = (n: number) => Array.from({ length: n }, (_, i) => `n${i}`);

describe("radialLayout", () => {
  it("returns identical output for identical input", () => {
    expect(radialLayout(ids(9))).toEqual(radialLayout(ids(9)));
    expect(JSON.stringify(radialLayout(ids(9)))).toBe(JSON.stringify(radialLayout(ids(9))));
  });

  it("keeps the order it was given, first node at the top, going clockwise", () => {
    const { nodes, width } = radialLayout(["a", "b", "c", "d"]);
    expect(nodes.map((n) => n.id)).toEqual(["a", "b", "c", "d"]);
    expect(nodes[0]!.x).toBeCloseTo(width / 2);
    expect(nodes[0]!.y).toBeLessThan(nodes[2]!.y); // top before bottom
    expect(nodes[1]!.x).toBeGreaterThan(nodes[3]!.x); // clockwise: the second is on the right
  });

  it("never overlaps two nodes, at any size up to the 30-node cap", () => {
    for (let n = 2; n <= 30; n++) {
      const { nodes, nodeRadius } = radialLayout(ids(n));
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const distance = Math.hypot(nodes[i]!.x - nodes[j]!.x, nodes[i]!.y - nodes[j]!.y);
          expect(distance, `n=${n}, nodes ${i} and ${j}`).toBeGreaterThanOrEqual(2 * nodeRadius);
        }
      }
    }
  });

  it("keeps every node inside the drawing", () => {
    const { nodes, width, height, nodeRadius } = radialLayout(ids(30));
    for (const node of nodes) {
      expect(node.x).toBeGreaterThanOrEqual(nodeRadius);
      expect(node.x).toBeLessThanOrEqual(width - nodeRadius);
      expect(node.y).toBeGreaterThanOrEqual(nodeRadius);
      expect(node.y).toBeLessThanOrEqual(height - nodeRadius);
    }
  });

  it("handles one node and none without NaN", () => {
    const one = radialLayout(["only"]);
    expect(one.nodes).toHaveLength(1);
    expect(Number.isFinite(one.nodes[0]!.x) && Number.isFinite(one.nodes[0]!.y)).toBe(true);
    expect(radialLayout([]).nodes).toEqual([]);
  });
});
