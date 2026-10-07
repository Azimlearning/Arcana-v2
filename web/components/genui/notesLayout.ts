// A deterministic ring layout for the NotesGraph diagram: a focused graph has its page in the middle and the linked pages on a
// circle around it; an overview has all pages on one circle. A pure function of the ids and the options (no randomness, no
// iteration), so the same block always draws the same picture and a re-render never makes the diagram jump.

export interface RingOptions {
  width?: number;
  height?: number;
  /** Radius of a drawn node. */
  nodeRadius?: number;
}

export interface PlacedPage {
  id: string;
  x: number;
  y: number;
  /** Which side of the diagram the label sits on, so labels point away from the middle. */
  side: "start" | "end" | "middle";
  /** On the inner circle of a crowded ring: its label is shown only when the page is chosen (the list names every page). */
  inner: boolean;
}

export interface RingLayout {
  width: number;
  height: number;
  nodeRadius: number;
  pages: PlacedPage[];
}

const round = (value: number) => Math.round(value * 100) / 100;

/** More pages than this on the ring and every second one sits on the inner circle. */
export const CROWDED = 14;
const INNER = 0.82;

export function ringLayout(focusId: string | null, ids: readonly string[], options: RingOptions = {}): RingLayout {
  const width = options.width ?? 640;
  const height = options.height ?? 440;
  const nodeRadius = options.nodeRadius ?? 9;
  const cx = width / 2;
  const cy = height / 2;
  const ring = ids.filter((id) => id !== focusId);
  // Leave room for labels on the left and right and a little above and below.
  const rx = width / 2 - 120;
  const ry = height / 2 - 28;
  const pages: PlacedPage[] = [];
  if (focusId !== null && ids.includes(focusId)) pages.push({ id: focusId, x: round(cx), y: round(cy), side: "middle", inner: false });
  // A crowded ring alternates between two radii, so neighbouring labels do not sit on top of each other.
  const crowded = ring.length > CROWDED;
  ring.forEach((id, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ring.length, 1);
    const scale = crowded && i % 2 === 1 ? INNER : 1;
    const x = cx + rx * scale * Math.cos(angle);
    const y = cy + ry * scale * Math.sin(angle);
    const side = Math.abs(x - cx) < 6 ? "middle" : x < cx ? "end" : "start";
    pages.push({ id, x: round(x), y: round(y), side, inner: scale !== 1 });
  });
  return { width, height, nodeRadius, pages };
}
