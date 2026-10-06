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
from api.genui.catalog import CATALOG, CITED_SUMMARY, SOURCE_LIST, ComposerEvidence
from api.llm.providers.fake import FakeProvider
from api.stores.doc_store import Document

CATALOG_DOC = Path(__file__).resolve().parents[2] / "refdocs" / "guides" / "catalog.md"
PLANNED = {"GraphView", "ComparisonGrid", "ConceptMap", "InsightCard"}
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
    assert [b.type for b in composition.blocks] == ["CitedSummary", "SourceList"]  # the answer first
    assert composition.blocks[0].meta.status == "ready"
    assert state["block"] is composition.primary
    assert [(r.component, r.outcome) for r in composition.records] == [
        ("CitedSummary", "admitted"),
        ("SourceList", "admitted"),
    ]
    assert [r.block_id for r in composition.records] == [b.id for b in composition.blocks]
    listing = composition.blocks[1]
    assert listing.meta.panel == "sources" and listing.id != composition.primary.id  # its own id: no replacing


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
    ]


def test_a_block_type_with_no_content_rules_is_refused_not_passed(ingested):
    """Fail closed for the next component: a variant added to the schema but not to the validator cannot ship."""
    deps, _ = ingested

    class Unknown:
        id = "x"
        meta = type("Meta", (), {"status": "ready", "error": None, "order": 0})()

    issues = validate._content_issues(Unknown(), deps.docs)  # type: ignore[arg-type]
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
    assert tags == set(CATALOG) == set(BUILDERS)
    assert all(CATALOG[name].name == name for name in CATALOG)
    assert _doc_sections() == tags | PLANNED, "catalog.md and the built set disagree: update PLANNED or the guide"
    assert not tags & PLANNED


def test_every_spec_states_its_precondition_and_a_placement_hint():
    for spec in CATALOG.values():
        assert spec.precondition.strip() and spec.supplied_by
        assert spec.placement.panel and spec.placement.priority >= 0
    assert sum(spec.terminal for spec in CATALOG.values()) == 1  # exactly one answer component per turn
