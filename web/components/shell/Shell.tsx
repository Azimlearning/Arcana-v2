// Adapted from Azimlearning/Arcana (v1), web/components/shell/Shell.tsx @ 9a3d67f. Read in full. Kept: the stable
// three-panel frame whose panels take their widths as flex-grow values and whose collapsed panels are `aria-hidden` and
// `inert`. Rewritten for v2: the widths come from the server's `LayoutSpec` (D-27), not a client-side per-mode table;
// there is no resizer, mode indicator or notebook id; the panel contents are passed in, so the frame knows no
// component; and Tailwind 4 utility classes are used (v1's token classes such as `bg-paper` are not carried over).
//
// Note: CSS `flex-grow` is not animatable, so a change of layout is an instant reflow.

import type { LayoutSpec, PanelId } from "@arcana/schema";
import type { ReactNode } from "react";

import { Panel } from "./Panel";

const TAGS: Record<PanelId, "aside" | "main" | "section"> = { sources: "aside", chat: "main", studio: "section" };

export function Shell({
  layout,
  header,
  panels,
}: {
  layout: LayoutSpec;
  header: ReactNode;
  /** What each panel holds. A panel the layout does not list is not rendered. */
  panels: Record<PanelId, ReactNode>;
}) {
  return (
    <div className="flex h-screen flex-col bg-stone-50 text-stone-900">
      <header className="flex items-center justify-between gap-4 border-b border-stone-200 bg-white px-6 py-3">
        {header}
      </header>
      <div className="flex min-h-0 flex-1 gap-4 p-4" data-layout-origin={layout.origin} data-layout-mode={layout.mode}>
        {layout.panels.map((panel) => (
          <Panel key={panel.id} id={panel.id} width={panel.width} as={TAGS[panel.id]}>
            {panels[panel.id]}
          </Panel>
        ))}
      </div>
    </div>
  );
}
