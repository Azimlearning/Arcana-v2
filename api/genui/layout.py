"""Level 2 of the generative UI: choosing where a turn's blocks go (D-27, D-28).

Two pure functions, no model call and no component names. A component says where it would like to sit through the
placement hint on its catalog entry (a preferred panel and a priority); this module only applies generic rules to
those hints, so adding a component never means editing it:

  - blocks go to their preferred panel, ordered by priority (lower first), then by arrival;
  - a panel with nothing placed in it is hidden (width 0), except chat, and its width goes to chat;
  - the layout is `exploration` when the question is about how things relate and something is placed in the studio
    panel, otherwise `research`.

The width tables below are judgement defaults (catalog.md, "Layout defaults and placement hints"); the validator
asserts invariants (whole numbers summing to 100, chat at least 25), not these exact values. Only the Composer
imports this module.
"""

from __future__ import annotations

from collections.abc import Sequence

from api.genui.catalog import CATALOG
from api.genui.generated import LayoutSpec, PanelId, PanelSpec, Placement, RegionId, RegionSpec
from api.genui.validate import LAYOUT_VERSION

CHAT: PanelId = "chat"
"""The panel that is never hidden and that takes the width of any panel left empty."""

# Width in percent by mode, in panel order. `basic` is the fixed starting layout, shown before any question.
WIDTHS: dict[str, tuple[tuple[PanelId, int], ...]] = {
    "basic": (("sources", 20), ("chat", 60), ("studio", 20)),
    "research": (("sources", 20), ("chat", 45), ("studio", 35)),
    "exploration": (("sources", 10), ("chat", 30), ("studio", 60)),
}
MAIN: RegionId = "main"
"""The region every block goes to until a component asks for another (task F2)."""
UNKNOWN_PRIORITY = 1000  # a component the catalog does not know goes last in chat rather than being dropped


def _panel(panel: PanelId, width: int) -> PanelSpec:
    """A panel of the given width with a single `main` region."""
    return PanelSpec(id=panel, width=width, direction="rows", regions=[RegionSpec(id=MAIN, size=100)])


def prebuilt_layout(sources_block_id: str | None = None) -> LayoutSpec:
    """The fixed layout the workspace opens on. Every turn block is shown in chat, in arrival order (no placement);
    only the workspace's own source list, when its id is given, is placed in the sources panel."""
    placements = (
        [Placement(blockId=sources_block_id, panel="sources", region=MAIN, order=0)] if sources_block_id else []
    )
    return LayoutSpec(
        version=LAYOUT_VERSION,
        origin="prebuilt",
        mode="basic",
        panels=[_panel(panel, width) for panel, width in WIDTHS["basic"]],
        placements=placements,
    )


def compose_layout(admitted: Sequence[tuple[str, str]], intent: str) -> LayoutSpec:
    """The adaptive layout for a turn. `admitted` is (block id, component name) in arrival order."""
    hinted: list[tuple[str, PanelId, int, int]] = []
    for arrival, (block_id, component) in enumerate(admitted):
        spec = CATALOG.get(component)
        panel, priority = (CHAT, UNKNOWN_PRIORITY) if spec is None else (spec.placement.panel, spec.placement.priority)
        hinted.append((block_id, panel, priority, arrival))

    exploring = intent == "relate" and any(panel == "studio" for _, panel, _, _ in hinted)
    mode = "exploration" if exploring else "research"

    placements: list[Placement] = []
    used: set[str] = set()
    for panel_id, _ in WIDTHS[mode]:
        in_panel = sorted((h for h in hinted if h[1] == panel_id), key=lambda h: (h[2], h[3]))
        if in_panel:
            used.add(panel_id)
        placements += [Placement(blockId=h[0], panel=panel_id, region=MAIN, order=i) for i, h in enumerate(in_panel)]

    panels: list[PanelSpec] = []
    freed = 0
    for panel_id, width in WIDTHS[mode]:
        if panel_id != CHAT and panel_id not in used:
            freed += width
            width = 0
        panels.append(_panel(panel_id, width))
    panels = [_panel(p.id, p.width + freed) if p.id == CHAT else p for p in panels]
    return LayoutSpec(version=LAYOUT_VERSION, origin="adaptive", mode=mode, panels=panels, placements=placements)
