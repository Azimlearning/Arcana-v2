// Adapted from Azimlearning/Arcana (v1), web/components/shell/Shell.tsx @ 9a3d67f. Read in full. Kept: the stable
// three-panel frame whose panels take their widths as flex-grow values and whose collapsed panels are `aria-hidden` and
// `inert`. Rewritten for v2: the widths come from the server's `LayoutSpec` (D-27), not a client-side per-mode table;
// there is no resizer, mode indicator or notebook id; the panel contents are passed in, so the frame knows no
// component; and Tailwind 4 utility classes are used (v1's token classes such as `bg-paper` are not carried over).
// Added for D-32: each panel is divided into the layout's regions (`Panel`), and a change of width or size is animated
// with a CSS transition on `flex-grow` (Synapse's adaptive layout animates its column template the same way), switched
// off for `prefers-reduced-motion`. Whether the browser interpolates `flex-grow` is checked in the real browser (P2b F5).

import type { LayoutSpec, PanelId, RegionId } from "@arcana/schema";
import type { ReactNode } from "react";

import { Panel } from "./Panel";

const TAGS: Record<PanelId, "aside" | "main" | "section"> = { sources: "aside", chat: "main", studio: "section" };

export function Shell({
  layout,
  header,
  panels,
  widenChat = false,
}: {
  layout: LayoutSpec;
  header: ReactNode;
  /** True while panes are open: the centre panel takes twice its share, the others keep theirs (a viewer's arrangement, D-44). */
  widenChat?: boolean;
  /** What each region of each panel holds. A panel the layout does not list is not rendered. */
  panels: Record<PanelId, Partial<Record<RegionId, ReactNode>>>;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900 md:h-screen">
      <header className="flex items-center justify-between gap-4 border-b border-stone-200 bg-white px-6 py-3">
        {header}
      </header>
      {/* Below the md breakpoint the panels stack (chat first, then the studio, then the sources) and the page scrolls: three
          side by side panels at phone width are columns a few characters wide (seen in the real browser, P5 S5). */}
      <div
        className="flex min-h-0 flex-1 gap-4 p-4 max-md:flex-col"
        data-layout-origin={layout.origin}
        data-layout-mode={layout.mode}
      >
        {layout.panels.map((panel) => (
          <Panel
            key={panel.id}
            spec={widenChat && panel.id === "chat" ? { ...panel, width: panel.width * 2 } : panel}
            regions={panels[panel.id]}
            as={TAGS[panel.id]}
          />
        ))}
      </div>
    </div>
  );
}
