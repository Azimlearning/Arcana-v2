"""The catalog spine: one Composer decision per component, no provider call, and four lists kept in step."""

import re
import typing
from pathlib import Path

from api.agents.compose import compose
from api.agents.test_agents import GRAPH, QUESTION, make_ctx
from api.core.budget import TokenBudget
from api.fakes import fake_llm_responder
from api.genui import generated, validate
from api.genui.builders import BUILDERS
from api.genui.catalog import CATALOG, CITED_SUMMARY, GRAPH_VIEW, SOURCE_LIST, ComposerEvidence
from api.genui.lab_catalog import LAB_CATALOG
from api.genui.notes_catalog import NOTES_CATALOG
from api.llm.providers.fake import FakeProvider
from api.stores.doc_store import Document

CATALOG_DOC = Path(__file__).resolve().parents[2] / "refdocs" / "guides" / "catalog.md"
PLANNED = {"InsightCard"}
"""Components written up in catalog.md but not built yet. Each task B1 to B5 moves one name out of this set."""


def _variants(tp) -> list[type]:
    """Every model class inside the UIBlock alias: one class now, a discriminated union (Annotated) from B1."""
    if hasattr(tp, "model_fields"):
        return [tp]
    return [v for arg in typing.get_args(tp) for v in _variants(arg)]


def _union_tags() -> set[str]:
    return {typing.get_args(v.model_fields["type"].annotation)[0] for v in _variants(generated.UIBlock)}


def _doc_sections() -> set[str]:
    text = CATALOG_DOC.read_text(encoding="utf-8")
    names = {re.sub(r" \(stretch\)$", "", m) for m in re.findall(r"^## (\w+(?: \(stretch\))?)\s*$", text, re.M)}
    return {n for n in names if n[0].isupper() and n not in {"The", "Conventions", "Layout", "How", "UI", "Not"}}


async def _composed(ingested, tmp_path):
    deps, _ = ingested
    provider = FakeProvider(fake_llm_responder)
    ctx = make_ctx(deps, tmp_path, provider=provider)
    state = await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    return deps, ctx, provider, state


async def test_a_turn_yields_one_cited_summary_and_one_source_list_with_two_admitted_records(ingested, tmp_path):
    _, _, _, state = await _composed(ingested, tmp_path)
    composition = state["composition"]
    assert [b.type for b in composition.blocks] == ["CitedSummary", "SourceList"]  # the answer first; no graph on ctx
    assert composition.blocks[0].meta.status == "ready"
    assert state["block"] is composition.primary
    assert [(r.component, r.outcome) for r in composition.records] == [
        ("CitedSummary", "admitted"),
        ("SourceList", "admitted"),
        ("GraphView", "refused"),  # this ctx has no graph store, so the Graph agent had nothing to draw
        ("TraversalView", "refused"),
        ("ComparisonGrid", "refused"),
        ("ConceptMap", "refused"),
    ]
    assert [r.block_id for r in composition.records if r.outcome == "admitted"] == [b.id for b in composition.blocks]
    listing = composition.blocks[1]
    assert listing.id != composition.primary.id  # its own id: no replacing


async def test_a_comparison_with_a_graph_adds_a_grounded_graph_view(ingested, tmp_path):
    deps, _ = ingested
    ctx = make_ctx(deps, tmp_path)
    ctx.graph = deps.graph
    state = await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    composition = state["composition"]
    assert [b.type for b in composition.blocks] == ["CitedSummary", "SourceList", "GraphView", "TraversalView"]
    # One paper is not a comparison: the grid is refused, with its reason on record.
    assert [r.outcome for r in composition.records] == [
        "admitted",
        "admitted",
        "admitted",
        "admitted",
        "refused",
        "refused",
    ]
    assert composition.records[4].reasons == ("no_shared_entities",)
    assert composition.records[5].reasons == (
        "single_hop",
    )  # Dense Retrieval to BM25 is one hop: the graph view's case
    view = composition.blocks[2]
    assert view.id == "blk-graph-view"
    assert {n.label for n in view.data.nodes} == {"Dense Retrieval", "BM25"}  # type: ignore[union-attr]
    (edge,) = view.data.edges  # type: ignore[union-attr]
    quote = next(c.quote for c in view.data.citations if c.id == edge.citationId)  # type: ignore[union-attr]
    assert "Dense Retrieval" in quote and "BM25" in quote  # the cited words name both ends


async def test_composing_issues_no_provider_call(ingested, tmp_path):
    _, ctx, provider, _ = await _composed(ingested, tmp_path)
    calls = len(provider.calls)
    assert calls > 0  # the agents did call the model; the Composer must add nothing to that
    first, second = compose(ctx), compose(ctx)
    assert len(provider.calls) == calls
    assert first.records == second.records  # a pure function of what the agents returned


async def test_no_evidence_is_an_empty_record_and_still_one_block(ingested, tmp_path):
    deps, _ = ingested
    for doc in deps.docs.list_documents():
        deps.docs.delete_document(doc.id)
    ctx = make_ctx(deps, tmp_path, budget=TokenBudget())
    state = await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    composition = state["composition"]
    assert len(composition.blocks) == 1 and composition.primary.meta.status == "empty"  # no SourceList either
    assert [(r.component, r.outcome, r.reasons) for r in composition.records] == [
        ("CitedSummary", "empty", ("no_grounded_answer",)),
        ("SourceList", "refused", ("no_ready_document",)),
        ("GraphView", "refused", ("no_grounded_edge",)),
        ("TraversalView", "refused", ("nothing_resolved",)),
        ("ComparisonGrid", "refused", ("no_shared_entities",)),
        ("ConceptMap", "refused", ("not_a_path",)),
    ]


def test_a_block_type_with_no_content_rules_is_refused_not_passed(ingested):
    """Fail closed for the next component: a variant added to the schema but not to the validator cannot ship."""
    deps, _ = ingested

    class Unknown:
        id = "x"
        meta = type("Meta", (), {"status": "ready", "error": None})()

    issues = validate._content_issues(Unknown(), deps.docs, None)  # type: ignore[arg-type]
    assert [i.path for i in issues] == ["type"]


def test_the_source_list_check_needs_a_ready_document():
    def with_docs(*statuses):
        docs = tuple(Document(f"d{i}", "T", "p.pdf", s, 1, None, "t") for i, s in enumerate(statuses))
        return ComposerEvidence(answer=None, graph=None, documents=docs, intent="single")

    assert SOURCE_LIST.check(with_docs("failed", "ready")).satisfied
    refused = SOURCE_LIST.check(with_docs("failed", "pending"))
    assert not refused.satisfied and refused.reasons == ("no_ready_document",)
    assert not SOURCE_LIST.check(with_docs()).satisfied


def test_the_cited_summary_check_is_a_pure_function_of_the_evidence():
    def evidence(answer):
        return ComposerEvidence(answer=answer, graph=None, documents=(), intent="single")

    assert CITED_SUMMARY.check(evidence({"segments": [{"text": "x"}], "citations": []})).satisfied
    refused = CITED_SUMMARY.check(evidence(None))
    assert not refused.satisfied and refused.reasons == ("no_grounded_answer",)
    assert not CITED_SUMMARY.check(evidence({"segments": [], "citations": []})).satisfied


def test_schema_catalog_builders_and_guide_list_the_same_components():
    tags = _union_tags()
    assert tags == set(CATALOG) | set(NOTES_CATALOG) | set(LAB_CATALOG) == set(BUILDERS)
    assert not set(CATALOG) & set(NOTES_CATALOG)
    assert not (set(CATALOG) | set(NOTES_CATALOG)) & set(LAB_CATALOG)
    assert all(CATALOG[name].name == name for name in CATALOG)
    assert _doc_sections() == tags | PLANNED, "catalog.md and the built set disagree: update PLANNED or the guide"
    assert not tags & PLANNED


def test_every_spec_states_its_precondition_and_a_placement_hint():
    for spec in CATALOG.values():
        assert spec.precondition.strip() and spec.supplied_by
        assert spec.placement.panel and spec.placement.priority >= 0
    assert sum(spec.terminal for spec in CATALOG.values()) == 1  # exactly one answer component per turn


def test_the_graph_view_check_names_why_it_refuses():
    def evidence(graph):
        return ComposerEvidence(answer=None, graph=graph, documents=(), intent="relate")

    assert GRAPH_VIEW.check(evidence(None)).reasons == ("no_graph_result",)
    assert GRAPH_VIEW.check(evidence({"edges": [], "labels": {}})).reasons == ("no_grounded_edge",)
    assert GRAPH_VIEW.check(
        evidence(
            {
                "edges": [{"src": "a", "dst": "b", "relation": "uses", "quote": None}],
                "labels": {"a": "Alpha", "b": "Beta"},
            }
        )
    ).reasons == ("no_grounded_edge",)
    good = {
        "src": "a",
        "dst": "b",
        "relation": "uses",
        "quote": "A verbatim quote naming Alpha and Beta.",
        "doc_title": "P",
    }
    assert GRAPH_VIEW.check(evidence({"edges": [good], "labels": {"a": "Alpha", "b": "Beta"}})).satisfied


def test_a_reason_outside_the_closed_list_is_recorded_as_unspecified_never_as_free_text():
    from api.genui.catalog import ComponentRecord, component_decisions

    records = [ComponentRecord("GraphView", "refused", ("no_grounded_edge", "a quote from the document"))]
    graph_view = next(d for d in component_decisions(records) if d.component == "GraphView")
    assert graph_view.reasons == ["no_grounded_edge", "unspecified"] and graph_view.offered is False
    others = [d for d in component_decisions(records) if d.component != "GraphView"]
    assert all(d.reasons == ["not_considered"] and d.offered is False for d in others)
    assert [d.component for d in component_decisions([])] == list(CATALOG)
