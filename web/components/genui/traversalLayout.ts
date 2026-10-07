// A deterministic two-column layout for the TraversalView diagram: the concepts the question resolved to (the seeds) in a
// left column, the other concepts the followed edges reach in a right column, each column top to bottom in the order
// given. A pure function of the two id lists and the options: no randomness and no iteration, so the same block always
// draws the same picture and a re-render never makes the diagram jump.

export interface ColumnOptions {
  /** Radius of a drawn node. */
  nodeRadius?: number;
  /** Vertical distance between the centres of two neighbours in a column. */
  rowGap?: number;
  /** Room left of the left column and right of the right column for labels. */
  labelRoom?: number;
  /** Distance between the two columns. */
  columnGap?: number;
}

export interface PlacedNode {
  id: string;
  x: number;
  y: number;
  column: "left" | "right";
}

export interface ColumnLayout {
  width: number;
  height: number;
  nodeRadius: number;
  nodes: PlacedNode[];
}

const round = (value: number) => Math.round(value * 100) / 100;

export function columnLayout(
  seedIds: readonly string[],
  otherIds: readonly string[],
  options: ColumnOptions = {},
): ColumnLayout {
  const nodeRadius = options.nodeRadius ?? 10;
  const rowGap = options.rowGap ?? 30;
  const labelRoom = options.labelRoom ?? 130;
  const columnGap = options.columnGap ?? 160;

  const rows = Math.max(seedIds.length, otherIds.length, 1);
  const height = round(rows * rowGap + nodeRadius * 2);
  const leftX = labelRoom;
  const rightX = labelRoom + columnGap;
  const width = round(rightX + labelRoom);

  // Each column is centred on the other, so a short column sits in the middle of a tall one.
  const place = (ids: readonly string[], x: number, column: "left" | "right"): PlacedNode[] => {
    const top = (height - (ids.length - 1) * rowGap) / 2;
    return ids.map((id, i) => ({ id, x: round(x), y: round(ids.length === 1 ? height / 2 : top + i * rowGap), column }));
  };
  return { width, height, nodeRadius, nodes: [...place(seedIds, leftX, "left"), ...place(otherIds, rightX, "right")] };
}
