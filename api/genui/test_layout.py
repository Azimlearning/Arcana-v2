"""LayoutSpec: composed from catalog hints with no component names, validated, and never able to fail a turn."""

import itertools
import pathlib
from dataclasses import replace

import pytest

from api.agents import compose as compose_module
from api.agents.compose import _block_id, compose
from api.agents.graph import run_turn
from api.agents.test_agents import GRAPH, QUESTION, make_ctx
from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS
from api.genui.catalog import CATALOG, ComposerEvidence, Fences, PlacementHint, Result, Spec
from api.genui.generated import (
    BlockEvent,
    DoneEvent,
    LayoutEvent,
    LayoutSpec,
    PanelSpec,
    Placement,
    RegionId,
    RegionSpec,
    SplitDirection,
)
from api.genui.layout import WIDTHS, compose_layout, prebuilt_layout
from api.genui.validate import validate_layout

NAMES = list(CATALOG)
OPTIONAL = [n for n in NAMES if not CATALOG[n].terminal]
TERMINAL = next(n for n in NAMES if CATALOG[n].terminal)


def panel(
    panel_id, width, regions: tuple[tuple[RegionId, int], ...] = (("main", 100),), direction: SplitDirection = "rows"
) -> PanelSpec:
    return PanelSpec(
        id=panel_id, width=width, direction=direction, regions=[RegionSpec(id=r, size=n) for r, n in regions]
    )


def widths(layout: LayoutSpec) -> dict[str, int]:
    return {p.id: p.width for p in layout.panels}


def admitted(*components: str) -> list[tuple[str, str]]:
    return [(f"b-{c}", c) for c in components]


def fails(layout, known=()) -> list[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_layout(layout, known)
    return [i.path for i in exc.value.issues]


# ── composing ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("intent", ["single", "compare", "relate"])
def test_every_combination_of_components_gives_a_valid_adaptive_layout(intent):
    for size in range(len(OPTIONAL) + 1):
        for subset in itertools.combinations(OPTIONAL, size):
            blocks = admitted(TERMINAL, *subset)
            layout = compose_layout(blocks, intent)
            known = {b for b, _ in blocks}
            assert validate_layout(layout, known) == layout
            assert layout.origin == "adaptive" and sum(widths(layout).values()) == 100
            assert widths(layout)["chat"] >= 25
            placed = {p.panel for p in layout.placements}
            assert all(w == 0 for panel, w in widths(layout).items() if panel not in placed and panel != "chat")
            assert {p.blockId for p in layout.placements} <= known  # a layout names only the turn's blocks


def test_blocks_go_to_their_hinted_panel_in_priority_order_whatever_the_arrival_order():
    blocks = admitted(*reversed(NAMES))  # the answer arrives last
    layout = compose_layout(blocks, "compare")
    for panel in widths(layout):
        in_panel = [p for p in layout.placements if p.panel == panel]
        assert [p.order for p in in_panel] == list(range(len(in_panel)))
        hints = [CATALOG[next(c for b, c in blocks if b == p.blockId)].placement for p in in_panel]
        assert all(h.panel == panel for h in hints) and [h.priority for h in hints] == sorted(h.priority for h in hints)


def test_an_empty_panel_is_hidden_and_its_width_goes_to_chat():
    answer_only = compose_layout(admitted(TERMINAL), "single")
    assert widths(answer_only) == {"sources": 0, "chat": 100, "studio": 0}
    assert answer_only.placements == [Placement(blockId=f"b-{TERMINAL}", panel="chat", region="main", order=0)]


def test_a_studio_component_opens_the_studio_and_a_relating_question_makes_it_the_main_view():
    studio = next(n for n in OPTIONAL if CATALOG[n].placement.panel == "studio")
    sources = next(n for n in OPTIONAL if CATALOG[n].placement.panel == "sources")
    research = compose_layout(admitted(TERMINAL, sources, studio), "compare")
    assert research.mode == "research" and widths(research) == {"sources": 20, "chat": 45, "studio": 35}
    exploring = compose_layout(admitted(TERMINAL, sources, studio), "relate")
    assert exploring.mode == "exploration" and widths(exploring) == {"sources": 10, "chat": 30, "studio": 60}
    assert compose_layout(admitted(TERMINAL, sources), "relate").mode == "research"  # nothing in the studio


def test_the_prebuilt_layout_is_valid_and_fixed():
    layout = prebuilt_layout()
    assert validate_layout(layout, set()) == layout
    assert layout.origin == "prebuilt" and layout.mode == "basic" and layout.placements == []
    assert widths(layout) == {"sources": 20, "chat": 60, "studio": 20}
    assert prebuilt_layout() == layout
    with_sources = prebuilt_layout("workspace-sources")
    assert with_sources.placements == [Placement(blockId="workspace-sources", panel="sources", region="main", order=0)]
    assert validate_layout(with_sources, {"workspace-sources"}) == with_sources


def test_an_unknown_component_is_placed_last_in_chat_rather_than_dropped():
    layout = compose_layout([("x", "SomeFutureThing"), ("a", TERMINAL)], "single")
    chat = [p.blockId for p in sorted(layout.placements, key=lambda p: p.order) if p.panel == "chat"]
    assert chat == ["a", "x"]


# ── validating ────────────────────────────────────────────────────────────────


def good() -> LayoutSpec:
    return compose_layout(admitted(TERMINAL, *OPTIONAL), "compare")


def test_a_valid_layout_passes_with_the_blocks_it_names():
    layout = good()
    assert validate_layout(layout, {p.blockId for p in layout.placements}) == layout
    assert (
        validate_layout(layout.model_dump(), {p.blockId for p in layout.placements}) == layout
    )  # a plain mapping is accepted and re-checked


@pytest.mark.parametrize(
    ("change", "path"),
    [
        (lambda d: d.update(version=3), "version"),
        (lambda d: d.update(mode="basic"), "mode"),
        (lambda d: d["panels"][0].update(width=d["panels"][0]["width"] + 1), "panels"),
        (lambda d: d["panels"][0].update(width=-1), "panels.0.width"),
        (lambda d: d["panels"][1].update(width=101), "panels.1.width"),
        (lambda d: d["panels"].pop(1), "panels"),  # no chat panel (and widths no longer sum to 100)
        (lambda d: d["panels"].append(panel("chat", 0).model_dump()), "panels.3.id"),
        (lambda d: d["placements"][0].update(order=-1), "placements.0.order"),
        (lambda d: d["placements"].append(dict(d["placements"][0])), "placements.%d.blockId"),
        (lambda d: d["placements"][0].update(blockId="nobody"), "placements.0.blockId"),
    ],
)
def test_a_damaged_layout_is_rejected_with_its_field_path(change, path):
    layout = good()
    data = layout.model_dump()
    change(data)
    expected = path % (len(layout.placements)) if "%d" in path else path
    assert expected in fails(data, {p.blockId for p in layout.placements})


def test_chat_must_be_at_least_a_quarter_wide_and_a_hidden_panel_holds_nothing():
    narrow = LayoutSpec(
        version=2,
        origin="adaptive",
        mode="research",
        panels=[panel("sources", 40), panel("chat", 20), panel("studio", 40)],
        placements=[],
    )
    assert fails(narrow) == ["panels"]
    hidden = LayoutSpec(
        version=2,
        origin="adaptive",
        mode="research",
        panels=[panel("sources", 0), panel("chat", 100), panel("studio", 0)],
        placements=[Placement(blockId="a", panel="studio", region="main", order=0)],
    )
    assert fails(hidden, {"a"}) == ["placements.0.panel"]


def test_two_blocks_may_not_share_a_position():
    layout = good().model_dump()
    chat = [p for p in layout["placements"] if p["panel"] == "chat"]
    assert len(chat) >= 2
    chat[1]["order"] = chat[0]["order"]
    assert any(p.endswith(".order") for p in fails(layout))


def region_layout(regions, placement_region: RegionId = "main", width=100) -> LayoutSpec:
    return LayoutSpec(
        version=2,
        origin="adaptive",
        mode="research",
        panels=[panel("sources", 0), panel("chat", width, regions), panel("studio", 100 - width)],
        placements=[Placement(blockId="a", panel="chat", region=placement_region, order=0)],
    )


def test_regions_divide_a_panel_and_a_placement_must_name_one_the_panel_has():
    split = region_layout((("main", 60), ("secondary", 40)), "secondary", 100)
    assert validate_layout(split, {"a"}) == split
    assert fails(region_layout((("main", 100),), "secondary"), {"a"}) == ["placements.0.region"]


@pytest.mark.parametrize(
    ("regions", "path"),
    [
        ((), "panels.1.regions"),  # a panel has at least one region
        ((("main", 60), ("secondary", 30)), "panels.1.regions"),  # sizes must sum to 100
        ((("main", 50), ("main", 50)), "panels.1.regions.1.id"),  # ids unique within a panel
        ((("main", 101), ("secondary", -1)), "panels.1.regions.0.size"),  # whole numbers from 0 to 100
    ],
)
def test_a_damaged_region_list_is_rejected_with_its_field_path(regions, path):
    assert path in fails(region_layout(regions), {"a"})


def test_a_region_of_size_zero_holds_nothing_and_orders_are_unique_within_a_region():
    assert fails(region_layout((("main", 0), ("secondary", 100))), {"a"}) == ["placements.0.region"]
    both = region_layout((("main", 50), ("secondary", 50))).model_dump()
    both["placements"] = [
        {"blockId": "a", "panel": "chat", "region": "main", "order": 0},
        {"blockId": "b", "panel": "chat", "region": "secondary", "order": 0},  # same order, another region: fine
    ]
    assert validate_layout(both, {"a", "b"})
    both["placements"][1]["region"] = "main"  # same region and order: not fine
    assert fails(both, {"a", "b"}) == ["placements.1.order"]


def test_a_version_1_layout_is_read_as_one_main_region_in_every_panel():
    v1 = {
        "version": 1,
        "origin": "prebuilt",
        "mode": "basic",
        "panels": [{"id": "sources", "width": 20}, {"id": "chat", "width": 60}, {"id": "studio", "width": 20}],
        "placements": [{"blockId": "workspace-sources", "panel": "sources", "order": 0}],
    }
    layout = validate_layout(v1, {"workspace-sources"})
    assert layout.version == 2 and layout == prebuilt_layout("workspace-sources")
    v1["placements"][0]["panel"] = "sidebar"  # a damaged v1 is still refused
    assert fails(v1, {"workspace-sources"})
    assert fails({"version": 1, "panels": "x", "placements": []})  # and one that cannot be read at all
    assert fails({**v1, "version": True}, {"workspace-sources"})  # a boolean is not version 1 (the client agrees)


def test_an_unknown_panel_or_a_wrong_type_is_a_schema_failure():
    data = good().model_dump()
    data["placements"][0]["panel"] = "sidebar"
    assert fails(data)  # the schema's closed list of panels refuses it
    data = good().model_dump()
    data["panels"][0]["width"] = 20.5
    assert fails(data) == ["panels.0.width"]


# ── growing without editing the layout ────────────────────────────────────────


async def test_a_new_component_is_placed_by_its_hint_with_no_change_to_the_layout_code(ingested, tmp_path, monkeypatch):
    """The recipe in catalog.md: a Spec with a placement hint, a raw builder, a precondition over the evidence. The
    toy reuses an existing block type (the wire union is fixed) but is a new catalog entry the layout has never
    heard of; it is admitted, validated, placed in its preferred panel, and layout.py is untouched."""
    deps, _ = ingested
    ctx = make_ctx(deps, tmp_path)
    await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    ctx.intent = "single"
    baseline = compose(ctx).layout
    assert baseline is not None

    def toy_raw(spec, ctx, evidence, empty):
        listed = [
            {"docId": d.id, "title": d.title, "chunkCount": evidence.chunk_counts[d.id]} for d in evidence.documents[:1]
        ]
        return BUILDERS["SourceList"](_block_id(spec, ctx), "ready", documents=listed)

    toy = Spec(
        name="ToyShelf",
        precondition="The turn's intent is the toy intent (a test field of the evidence).",
        supplied_by=("test",),
        fences=Fences(caps={}, grounding="none"),
        placement=PlacementHint(panel="studio", priority=5),
        check=lambda evidence: Result(evidence.intent == "toy", () if evidence.intent == "toy" else ("not_toy",)),
    )
    monkeypatch.setitem(CATALOG, "ToyShelf", toy)
    monkeypatch.setitem(compose_module._RAW, "ToyShelf", toy_raw)

    ctx.intent = "toy"
    composition = compose(ctx)
    block = next(b for b in composition.blocks if b.id == "blk-toy-shelf")
    assert next(r for r in composition.records if r.component == "ToyShelf").outcome == "admitted"
    layout = composition.layout
    assert (
        layout is not None and Placement(blockId=block.id, panel="studio", region="main", order=0) in layout.placements
    )
    assert widths(layout)["studio"] > 0 and layout != baseline

    monkeypatch.delitem(CATALOG, "ToyShelf")  # remove it again: the layout is exactly what it was
    ctx.intent = "toy"
    assert compose(ctx).layout == baseline

    ctx.intent = "single"  # and with the toy registered but not admitted, nothing changes either
    monkeypatch.setitem(CATALOG, "ToyShelf", toy)
    assert compose(ctx).layout == baseline


def test_the_layout_module_names_no_component_and_only_the_composer_imports_it():
    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "genui" / "layout.py").read_text(encoding="utf-8")
    assert [n for n in NAMES if n in text] == []
    importers = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if not p.name.startswith("test_")
        and (
            "api.genui.layout" in p.read_text(encoding="utf-8")
            or "genui import layout" in p.read_text(encoding="utf-8")
        )
    ]
    assert sorted(importers) == ["agents/compose.py"]


# ── a layout that fails never fails the turn ──────────────────────────────────


async def test_an_invalid_layout_is_left_out_and_the_turn_still_ends_with_its_blocks_and_done(
    ingested, tmp_path, monkeypatch
):
    deps, _ = ingested
    broken = LayoutSpec(
        version=2,
        origin="adaptive",
        mode="research",
        panels=[panel("sources", 10), panel("chat", 10), panel("studio", 10)],
        placements=[],
    )
    monkeypatch.setattr(compose_module, "compose_layout", lambda blocks, intent: broken)
    ctx = make_ctx(deps, tmp_path)
    events = [e async for e in run_turn(GRAPH, QUESTION, ctx)]
    assert [type(e) for e in events if isinstance(e, LayoutEvent)] == []
    assert isinstance(events[-1], DoneEvent) and sum(isinstance(e, BlockEvent) for e in events) >= 3
    state = await GRAPH.ainvoke({"question": QUESTION}, context=make_ctx(deps, tmp_path))
    assert state["composition"].layout is None and set(state["composition"].layout_failure) == {"panels"}


async def test_a_layout_that_raises_is_also_left_out(ingested, tmp_path, monkeypatch):
    deps, _ = ingested

    def boom(blocks, intent):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(compose_module, "compose_layout", boom)
    state = await GRAPH.ainvoke({"question": QUESTION}, context=make_ctx(deps, tmp_path))
    assert state["composition"].layout is None and state["composition"].layout_failure == ("internal",)
    assert state["composition"].primary.meta.status == "ready"
    assert "secret" not in repr(state["composition"].layout_failure)


def test_the_evidence_type_still_carries_the_fields_a_check_may_read():
    assert {"answer", "graph", "documents", "intent", "chunk_counts"} <= set(ComposerEvidence.__dataclass_fields__)


async def test_a_layout_damaged_after_composition_is_stopped_at_the_last_gate(ingested, tmp_path, monkeypatch):
    """Like a block, the layout is re-validated from plain data just before the wire: a layout mutated or built around
    the validator (model_construct) is not streamed, and the turn still ends with its blocks and done."""
    deps, _ = ingested
    real = compose_module.compose

    def damaged(ctx):
        composition = real(ctx)
        bad = LayoutSpec.model_construct(
            version=2,
            origin="adaptive",
            mode="research",
            panels=[panel("sources", 50), panel("chat", 60), panel("studio", 0)],
            placements=[],
        )
        return replace(composition, layout=bad)

    monkeypatch.setattr(compose_module, "compose", damaged)
    events = [e async for e in run_turn(GRAPH, QUESTION, make_ctx(deps, tmp_path))]
    assert [e for e in events if isinstance(e, LayoutEvent)] == []  # widths sum to 110: never sent
    assert isinstance(events[-1], DoneEvent) and sum(isinstance(e, BlockEvent) for e in events) >= 3


async def test_a_layout_naming_a_block_the_turn_did_not_send_is_stopped_at_the_last_gate(
    ingested, tmp_path, monkeypatch
):
    deps, _ = ingested
    real = compose_module.compose

    def ghost(ctx):
        composition = real(ctx)
        layout = composition.layout
        assert layout is not None
        placements = [*layout.placements, Placement(blockId="ghost", panel="chat", region="main", order=99)]
        return replace(composition, layout=layout.model_copy(update={"placements": placements}))

    monkeypatch.setattr(compose_module, "compose", ghost)
    events = [e async for e in run_turn(GRAPH, QUESTION, make_ctx(deps, tmp_path))]
    assert [e for e in events if isinstance(e, LayoutEvent)] == [] and isinstance(events[-1], DoneEvent)


def test_every_hint_names_a_panel_the_layout_has():
    """A new component needs no edit to layout.py, but a hint for a panel the layout does not have would be silently
    unplaced; a new panel is a change to layout.py, layout.ts and the shell together."""
    panels = {panel for panel, _ in WIDTHS["research"]}
    assert {spec.placement.panel for spec in CATALOG.values()} <= panels
    assert all({p for p, _ in table} == panels for table in WIDTHS.values())


def test_the_prebuilt_layout_equals_the_committed_fixture_the_web_client_falls_back_to():
    """The web client keeps a constant copy (web/lib/layout.ts) for when /workspace cannot be reached, and its own test
    compares it with this same file, so the two cannot drift apart."""
    import json

    fixture = pathlib.Path(__file__).resolve().parents[2] / "packages" / "schema" / "fixtures" / "prebuilt-layout.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == prebuilt_layout("workspace-sources").model_dump()


def test_the_committed_version_1_fixture_is_read_as_the_current_prebuilt_layout():
    """The web client reads the same file in its own test, so both sides read a version 1 layout the same way."""
    import json

    fixtures = pathlib.Path(__file__).resolve().parents[2] / "packages" / "schema" / "fixtures"
    v1 = json.loads((fixtures / "layout-v1.json").read_text(encoding="utf-8"))
    assert v1["version"] == 1 and "regions" not in v1["panels"][0]
    assert validate_layout(v1, {"workspace-sources"}) == prebuilt_layout("workspace-sources")
