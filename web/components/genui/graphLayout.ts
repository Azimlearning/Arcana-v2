// A deterministic radial layout for the GraphView diagram. A pure function of the node order and the options:
// no randomness, no iteration, no dependence on edges, so the same block always draws the same picture and a
// re-render never makes the diagram jump. Nodes sit on one circle, the first at the top, going clockwise.
//
// The circle grows with the node count so that neighbours never touch: the chord between adjacent nodes is
// always at least a node's diameter plus the gap (see graphLayout.test.ts, which checks the 30-node cap).

export interface LayoutOptions {
  /** Radius of a drawn node. */
  nodeRadius?: number;
  /** Clear space kept between two neighbouring nodes. */
  gap?: number;
  /** The smallest circle, so a two-node graph is not drawn as a dot. */
  minRadius?: number;
  /** Room left around the circle for labels. */
  padding?: number;
}

export interface PlacedNode {
  id: string;
  x: number;
  y: number;
}

export interface Layout {
  width: number;
  height: number;
  nodeRadius: number;
  nodes: PlacedNode[];
}

const round = (value: number) => Math.round(value * 100) / 100;

export function radialLayout(ids: readonly string[], options: LayoutOptions = {}): Layout {
  const nodeRadius = options.nodeRadius ?? 14;
  const gap = options.gap ?? 14;
  const minRadius = options.minRadius ?? 90;
  const padding = options.padding ?? 130;
  const count = ids.length;

  // Adjacent nodes are 2R sin(pi / n) apart: solve for the R that keeps that at least a diameter plus the gap.
  const needed = count > 1 ? (2 * nodeRadius + gap) / (2 * Math.sin(Math.PI / count)) : 0;
  const radius = round(Math.max(minRadius, needed));

  const width = round(2 * (radius + padding));
  const height = round(2 * (radius + padding * 0.5));
  const cx = width / 2;
  const cy = height / 2;

  const nodes = ids.map((id, i) => {
    if (count === 1) return { id, x: round(cx), y: round(cy) };
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / count;
    return { id, x: round(cx + radius * Math.cos(angle)), y: round(cy + radius * Math.sin(angle)) };
  });
  return { width, height, nodeRadius, nodes };
}
