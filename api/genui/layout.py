"""Level 2 of the generative UI: choosing where a turn's blocks go (D-27, D-28, D-32).

Two pure functions, no model call and no component names. A component says where it would like to sit through the
placement hint on its catalog entry (a preferred panel, optionally a region of it and a split direction, and a
priority); this module only applies generic rules to those hints, so adding a component never means editing it:

  - blocks go to their preferred panel and region, ordered by priority (lower first), then by arrival;
  - a panel with nothing placed in it is hidden (width 0) and its width goes to chat, except a panel that always keeps
    a region (the studio panel keeps its shelf, so saved views stay reachable): that one keeps a narrow width;
  - a panel is divided into the regions that hold something (plus the ones it always keeps), in the direction its
    first hint that names one asks for (else the panel's default); region sizes are fixed shares of the panel;
  - the layout is `exploration` when the question is about how things relate and something is placed in the studio
    panel, otherwise `research`.

The tables below are judgement defaults (catalog.md, "Layout defaults and placement hints"); the validator asserts
invariants (whole numbers summing to 100, chat at least 25), not these exact values. Only the Composer imports this
module.
"""

from __future__ import annotations

from collections.abc import Sequence

from api.genui.catalog import CATALOG
from api.genui.generated import (
    LayoutSpec,
    PanelId,
    PanelSpec,
    Placement,
    RegionId,
    RegionSpec,
    SplitDirection,
)
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
"""The region every block goes to until a component asks for another."""
UNKNOWN_PRIORITY = 1000  # a component the catalog does not know goes last in chat rather than being dropped

# The regions a panel always has, whatever is placed in it, and the width it keeps when nothing is placed in it.
ALWAYS: dict[PanelId, tuple[RegionId, ...]] = {"studio": ("shelf",)}
KEPT_WIDTH: dict[PanelId, int] = {"studio": 20}

# How a panel is divided when its hints do not say: the answer and what is split from it sit side by side, the graph and
# the shelf stack.
DEFAULT_DIRECTION: dict[PanelId, SplitDirection] = {"sources": "rows", "chat": "columns", "studio": "rows"}
# Each region's weight; a panel's regions share it in these proportions (main 3 : secondary 2 : shelf 2).
WEIGHT: dict[RegionId, int] = {"main": 3, "secondary": 2, "shelf": 2}
REGION_ORDER: tuple[RegionId, ...] = ("main", "secondary", "shelf")
# The fixed Basic layout's studio is mostly shelf: its graph area only says where graphs show in Basic (seen in the browser,
# P2b F5: at 60 / 40 that area was a large empty block).
PREBUILT_SIZES: dict[PanelId, tuple[tuple[RegionId, int], ...]] = {"studio": (("main", 25), ("shelf", 75))}


def _shares(regions: Sequence[RegionId]) -> list[RegionSpec]:
    """The regions with whole-number sizes in proportion to their weights, summing to 100 (largest remainder)."""
    total = sum(WEIGHT[r] for r in regions)
    raw = [100 * WEIGHT[r] / total for r in regions]
    sizes = [int(x) for x in raw]
    for i in sorted(range(len(regions)), key=lambda i: (raw[i] - sizes[i], -i), reverse=True)[: 100 - sum(sizes)]:
        sizes[i] += 1
    return [RegionSpec(id=r, size=n) for r, n in zip(regions, sizes, strict=True)]


def _panel(
    panel: PanelId, width: int, regions: Sequence[RegionId] = (MAIN,), direction: SplitDirection | None = None
) -> PanelSpec:
    """A panel of the given width divided into the given regions, in the canonical order."""
    ordered: list[RegionId] = [r for r in REGION_ORDER if r in regions]
    return PanelSpec(
        id=panel,
        width=width,
        direction=direction or DEFAULT_DIRECTION.get(panel, "rows"),
        regions=_shares(ordered),
    )


def _prebuilt_panel(panel: PanelId, width: int) -> PanelSpec:
    """A panel of the fixed layout: the regions it always has beside `main`, in their fixed sizes if it has any."""
    spec = _panel(panel, width, (MAIN, *ALWAYS.get(panel, ())))
    if panel in PREBUILT_SIZES:
        spec = spec.model_copy(update={"regions": [RegionSpec(id=r, size=n) for r, n in PREBUILT_SIZES[panel]]})
    return spec


def prebuilt_layout(sources_block_id: str | None = None) -> LayoutSpec:
    """The fixed layout the workspace opens on. Every turn block is shown in chat, in arrival order (no placement);
    only the workspace's own source list, when its id is given, is placed in the sources panel. The studio panel is
    its graph area above its shelf: in Basic the graph shows below the answer, so the graph area explains that."""
    placements = (
        [Placement(blockId=sources_block_id, panel="sources", region=MAIN, order=0)] if sources_block_id else []
    )
    return LayoutSpec(
        version=LAYOUT_VERSION,
        origin="prebuilt",
        mode="basic",
        panels=[_prebuilt_panel(panel, width) for panel, width in WIDTHS["basic"]],
        placements=placements,
    )


def compose_layout(admitted: Sequence[tuple[str, str]], intent: str) -> LayoutSpec:
    """The adaptive layout for a turn. `admitted` is (block id, component name) in arrival order."""
    hinted: list[tuple[str, PanelId, RegionId, SplitDirection | None, int, int]] = []
    for arrival, (block_id, component) in enumerate(admitted):
        spec = CATALOG.get(component)
        if spec is None:
            hinted.append((block_id, CHAT, MAIN, None, UNKNOWN_PRIORITY, arrival))
        else:
            hint = spec.placement
            hinted.append((block_id, hint.panel, hint.region, hint.direction, hint.priority, arrival))

    exploring = intent == "relate" and any(panel == "studio" for _, panel, _, _, _, _ in hinted)
    mode = "exploration" if exploring else "research"

    placements: list[Placement] = []
    regions: dict[PanelId, set[RegionId]] = {}
    directions: dict[PanelId, SplitDirection] = {}
    for panel_id, _ in WIDTHS[mode]:
        in_panel = [h for h in hinted if h[1] == panel_id]
        for region_id in REGION_ORDER:
            in_region = sorted((h for h in in_panel if h[2] == region_id), key=lambda h: (h[4], h[5]))
            if in_region:
                regions.setdefault(panel_id, set()).add(region_id)
            placements += [
                Placement(blockId=h[0], panel=panel_id, region=region_id, order=i) for i, h in enumerate(in_region)
            ]
        # The direction comes from the highest-priority hint in the panel that names one.
        asked = sorted((h for h in in_panel if h[3] is not None), key=lambda h: (h[4], h[5]))
        if asked and asked[0][3] is not None:
            directions[panel_id] = asked[0][3]

    panels: list[PanelSpec] = []
    freed = 0
    for panel_id, width in WIDTHS[mode]:
        used = regions.get(panel_id, set())
        if panel_id != CHAT and not used:
            kept = KEPT_WIDTH.get(panel_id, 0)
            freed += width - kept
            width = kept
        shown: set[RegionId] = {*used, *ALWAYS.get(panel_id, ())} or {MAIN}
        if panel_id == CHAT:
            shown.add(MAIN)  # the answer's own area always exists
        panels.append(_panel(panel_id, width, tuple(shown), directions.get(panel_id)))
    panels = [p.model_copy(update={"width": p.width + freed}) if p.id == CHAT else p for p in panels]
    return LayoutSpec(version=LAYOUT_VERSION, origin="adaptive", mode=mode, panels=panels, placements=placements)
