"""Templates and fences (D-31 stages 1 to 3): a template registers only if its validator rejects every planted defect,
its caps have one source of truth, and the guide states the same numbers."""

import copy
import pathlib

import pytest

from api.core.errors import ValidationFailed
from api.genui import templates
from api.genui.catalog import CATALOG, GRAPH_VIEW, Fences, PlacementHint, Result, Spec
from api.genui.templates import (
    PlantedDefect,
    TemplateRefused,
    ensure_builtin_registered,
    fence_mismatches,
    fixture_store,
    register_template,
)
from api.genui.validate import validate_block

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "refdocs" / "guides" / "catalog.md").read_text(encoding="utf-8")


def suite(name):
    return templates.SUITES[name]()


# ── registration ──────────────────────────────────────────────────────────────


def test_the_five_built_in_templates_each_reject_every_planted_defect():
    registry: dict = {}
    ensure_builtin_registered(registry)
    assert set(registry) == set(CATALOG) == set(templates.SUITES)
    for name, registration in registry.items():
        _, defects = suite(name)
        assert registration.rejected == tuple(d.name for d in defects)  # all of them, none skipped
        assert len(defects) >= 8, f"{name} declares too few planted defects"
        assert registration.version == CATALOG[name].version


def test_registering_twice_does_not_run_the_suites_again(monkeypatch):
    registry: dict = {}
    ensure_builtin_registered(registry)
    monkeypatch.setattr(templates, "fixture_store", lambda: pytest.fail("registered templates were re-registered"))
    assert ensure_builtin_registered(registry) is registry


def test_a_template_with_a_deliberate_validator_hole_is_refused_and_the_defect_is_named():
    docs = fixture_store()
    valid, defects = suite("GraphView")
    harmless = PlantedDefect("a_defect_the_validator_does_not_catch", lambda raw: raw.update(id="renamed"))
    registry: dict = {}
    with pytest.raises(TemplateRefused) as refused:
        register_template(GRAPH_VIEW, docs, valid, [*defects, harmless], registry)
    assert refused.value.defect == "a_defect_the_validator_does_not_catch" and "accepted" in refused.value.reason
    assert registry == {}  # nothing was registered


def test_a_cap_loosened_until_a_defect_slips_through_is_caught_at_registration(monkeypatch):
    monkeypatch.setitem(GRAPH_VIEW.fences.caps, "nodes", 10_000)  # now 31 nodes validates: a hole
    with pytest.raises(TemplateRefused) as refused:
        ensure_builtin_registered({})
    assert refused.value.template == "GraphView" and refused.value.defect == "over_cap_nodes"


def test_a_defect_that_changes_nothing_is_refused():
    docs = fixture_store()
    valid, defects = suite("SourceList")
    with pytest.raises(TemplateRefused) as refused:
        register_template(CATALOG["SourceList"], docs, valid, [*defects, PlantedDefect("noop", lambda raw: None)], {})
    assert refused.value.defect == "noop" and "changes nothing" in refused.value.reason


def test_a_template_without_defects_or_with_a_bad_fixture_is_refused():
    docs = fixture_store()
    valid, defects = suite("GraphView")
    with pytest.raises(TemplateRefused, match="no planted defects"):
        register_template(GRAPH_VIEW, docs, valid, [], {})
    broken = copy.deepcopy(valid)
    broken["data"]["citations"][0]["chunkId"] = "no-such-chunk"
    with pytest.raises(TemplateRefused, match="does not validate"):
        register_template(GRAPH_VIEW, docs, broken, defects, {})
    with pytest.raises(TemplateRefused, match="fixture is a"):
        register_template(CATALOG["SourceList"], docs, valid, defects, {})
    with pytest.raises(TemplateRefused, match="unique"):
        register_template(GRAPH_VIEW, docs, valid, [defects[0], defects[0]], {})


def test_a_catalog_entry_with_no_declared_suite_is_refused(monkeypatch):
    toy = Spec(
        name="Unsuited",
        precondition="p",
        supplied_by=("test",),
        fences=Fences(caps={}, grounding="none"),
        placement=PlacementHint(panel="chat", priority=1),
        check=lambda evidence: Result(True),
    )
    monkeypatch.setitem(CATALOG, "Unsuited", toy)
    with pytest.raises(TemplateRefused, match="no planted-defect suite"):
        ensure_builtin_registered({})


def test_the_application_does_not_start_on_a_template_with_a_hole(tmp_path, monkeypatch):
    from api.container import build_container
    from api.core.settings import Settings

    monkeypatch.setattr(templates, "REGISTRY", {})  # as on a fresh process
    monkeypatch.setitem(GRAPH_VIEW.fences.caps, "edges", 10_000)
    with pytest.raises(TemplateRefused):
        build_container(Settings(_env_file=None, arcana_data_dir=tmp_path / "data"))  # pyright: ignore[reportCallIssue]


# ── one source of truth for the caps ──────────────────────────────────────────


def test_changing_a_cap_in_one_place_changes_the_validator_and_the_guide_check_fails_until_the_guide_is_updated(
    monkeypatch,
):
    docs = fixture_store()
    valid, _ = suite("GraphView")
    four_nodes = copy.deepcopy(valid)
    four_nodes["data"]["nodes"] += [{"id": f"x{i}", "label": "Alpha Method"} for i in range(2)]
    four_nodes["data"]["edges"] += [
        {"source": "alpha", "target": f"x{i}", "relation": "builds on", "citationId": "c1"} for i in range(2)
    ]
    assert validate_block(copy.deepcopy(four_nodes), docs).type == "GraphView"  # 4 nodes: allowed at 30
    assert fence_mismatches(GUIDE) == []

    monkeypatch.setitem(GRAPH_VIEW.fences.caps, "nodes", 3)
    with pytest.raises(ValidationFailed) as exc:
        validate_block(copy.deepcopy(four_nodes), docs)
    assert "data.nodes" in [i.path for i in exc.value.issues]  # the validator now refuses it
    mismatches = fence_mismatches(GUIDE)
    assert len(mismatches) == 1 and mismatches[0].startswith("GraphView: caps in the guide")  # until the guide changes


def test_the_guide_states_exactly_the_registered_fences():
    assert fence_mismatches(GUIDE) == []


def test_the_guide_check_notices_a_missing_line_a_changed_grounding_rule_and_a_changed_requirement():
    broken = GUIDE.replace("grounding `citation_verbatim_quote`", "grounding `something_else`")
    assert any(p.startswith("CitedSummary: grounding rule") for p in fence_mismatches(broken))
    broken = GUIDE.replace("a11y `region:Documents`", "a11y `region:Sources`")
    assert any(p.startswith("SourceList: accessibility") for p in fence_mismatches(broken))
    broken = "\n".join(
        line for line in GUIDE.splitlines() if "**Fences:** caps `steps" not in line and "min_steps=2" not in line
    )
    assert any(p.startswith("ConceptMap: the guide has no Fences line") for p in fence_mismatches(broken))


def test_the_components_expose_the_roles_and_labels_their_fences_require():
    """A static check against each component's source (the component tests assert them at run time)."""
    for name, template in CATALOG.items():
        source = (ROOT / "web" / "components" / "genui" / f"{name}.tsx").read_text(encoding="utf-8")
        for requirement in template.fences.a11y:
            assert requirement.label in source, f"{name}: no {requirement.role} labelled {requirement.label!r}"


# ── slots ─────────────────────────────────────────────────────────────────────


def test_slots_are_typed_strings_and_only_graph_supplied_templates_are_reusable_without_research():
    for name, template in CATALOG.items():
        for slot in template.slots:
            assert slot.kind in ("entity", "document_id") and 0 <= slot.min_count <= slot.max_count
        if name in ("CitedSummary", "WritingDraft"):
            assert template.slots == () and not template.reusable  # the answer and a draft need Research or Studio: not reusable
        else:
            assert template.reusable
    assert [s.name for s in CATALOG["ConceptMap"].slots] == ["entities"] and CATALOG["ConceptMap"].slots[
        0
    ].min_count == 2
    assert CATALOG["SourceList"].slots == ()


# ── the pipeline section of the guide ─────────────────────────────────────────


def test_the_guide_names_the_same_five_pipeline_stages_as_the_code():
    import re

    section = GUIDE.split("## UI generation pipeline", 1)[1]
    table_stages = re.findall(r"^\| \*\*(\w+)\*\* \|", section, flags=re.M)
    assert [s.lower() for s in table_stages] == list(templates.PIPELINE_STAGES)
    assert "### Where P4 plugs in" in section and "### Re-verification" in section
    for stage in ("Template", "Fences", "Checking", "Save", "Reuse"):
        assert f"**{stage}:**" in section, f"the guide does not say where P4 plugs into {stage}"


# ── a loosened cap must be caught for the intended rule, whichever cap it is ──


def _all_caps():
    return [(name, key) for name, template in CATALOG.items() for key in template.fences.caps]


@pytest.mark.parametrize(("name", "key"), _all_caps())
def test_loosening_any_single_cap_is_refused_at_registration(name, key, monkeypatch):
    """Every cap of every template is guarded by a planted defect that fires only that cap's own rule (the defect names
    the issue path it expects), so a validator that stops enforcing a cap cannot register."""
    loosened = 1 if key == "min_steps" else 10_000  # a minimum is loosened downwards, a maximum upwards
    monkeypatch.setitem(CATALOG[name].fences.caps, key, loosened)
    with pytest.raises(TemplateRefused) as refused:
        ensure_builtin_registered({})
    assert refused.value.template == name and refused.value.defect, f"{name}.{key} was not guarded"


def test_a_defect_rejected_for_the_wrong_reason_is_refused():
    docs = fixture_store()
    valid, defects = suite("GraphView")
    wrong = PlantedDefect("a_defect_with_a_wrong_expectation", _set_missing_chunk, expects="data.nodes")
    with pytest.raises(TemplateRefused, match="not for the intended rule"):
        register_template(GRAPH_VIEW, docs, valid, [*defects, wrong], {})


def _set_missing_chunk(raw):
    raw["data"]["citations"][0]["chunkId"] = "no-such-chunk"
