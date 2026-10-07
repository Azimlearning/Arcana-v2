// One panel of the workspace. Its share of the width is the layout's number for it, applied as a flex-grow value (so the
// shares are proportions, not pixels), and it is divided into the layout's regions: stacked (`rows`) or side by side
// (`columns`), each with its own share, also a flex-grow value (D-32). A panel or region of size 0 is collapsed: it is
// hidden from assistive technology (`aria-hidden`) and from the keyboard and pointer (`inert`), so nothing in it can be
// reached while it is invisible.
//
// The panel and each region are `relative` so that visually hidden (`sr-only`, absolutely positioned) text inside them
// stays inside: otherwise it escapes the scrolling and makes the whole page scroll (seen in the real browser, task D1).
// Text may break anywhere: a real document title is often a file name with no spaces, which would otherwise widen the
// panel (also D1). A change of share is animated; the animation is off for people who ask for reduced motion.

import type { PanelId, PanelSpec, RegionId } from "@arcana/schema";
import type { ReactNode } from "react";

const LABELS: Record<PanelId, string> = { sources: "Sources", chat: "Chat", studio: "Studio" };
/** What a region is called when it is a landmark of its own (only when a panel has more than one). */
const REGION_LABELS: Record<RegionId, string> = { main: "Main area", secondary: "Side area", shelf: "Outputs" };

const MOTION = "transition-[flex-grow] duration-300 motion-reduce:transition-none";

export function Panel({
  spec,
  regions,
  as: Tag = "section",
}: {
  spec: PanelSpec;
  /** What each region holds. A region the layout lists with no content is drawn empty; one it does not list is not drawn. */
  regions: Partial<Record<RegionId, ReactNode>>;
  as?: "section" | "aside" | "main";
}) {
  const collapsed = spec.width === 0;
  const split = spec.regions.length > 1;
  return (
    <Tag
      aria-label={LABELS[spec.id]}
      data-panel={spec.id}
      aria-hidden={collapsed || undefined}
      inert={collapsed}
      className={`relative flex min-h-0 min-w-0 overflow-y-auto [overflow-wrap:anywhere] ${
        spec.direction === "columns" ? "flex-row gap-4" : "flex-col gap-4"
      } ${MOTION}`}
      style={{ flexGrow: spec.width, flexShrink: 0, flexBasis: 0 }}
    >
      {spec.regions.map((region) => {
        const hidden = region.size === 0;
        return (
          <div
            key={region.id}
            data-region={region.id}
            role={split ? "region" : undefined}
            aria-label={split ? REGION_LABELS[region.id] : undefined}
            aria-hidden={hidden || undefined}
            inert={hidden}
            className={`relative min-h-0 min-w-0 overflow-y-auto [overflow-wrap:anywhere] ${MOTION}`}
            style={{ flexGrow: region.size, flexShrink: 0, flexBasis: 0 }}
          >
            {regions[region.id]}
          </div>
        );
      })}
    </Tag>
  );
}
