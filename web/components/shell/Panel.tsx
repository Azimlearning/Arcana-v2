// One region of the workspace. Its share of the width is the layout's number for it, applied as a flex-grow value
// (so the shares are proportions, not pixels). A panel of width 0 is collapsed: it is hidden from assistive technology
// (`aria-hidden`) and from the keyboard and pointer (`inert`), so nothing in it can be reached while it is invisible.

import type { PanelId } from "@arcana/schema";
import type { ReactNode } from "react";

const LABELS: Record<PanelId, string> = { sources: "Sources", chat: "Chat", studio: "Studio" };

export function Panel({
  id,
  width,
  as: Tag = "section",
  children,
}: {
  id: PanelId;
  width: number;
  as?: "section" | "aside" | "main";
  children: ReactNode;
}) {
  const collapsed = width === 0;
  return (
    <Tag
      aria-label={LABELS[id]}
      data-panel={id}
      aria-hidden={collapsed || undefined}
      inert={collapsed}
      className="min-w-0 overflow-y-auto"
      style={{ flexGrow: width, flexShrink: 0, flexBasis: 0 }}
    >
      {children}
    </Tag>
  );
}
