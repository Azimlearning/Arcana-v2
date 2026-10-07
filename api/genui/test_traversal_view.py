"""TraversalView (P2c T2): a block of what the search followed, re-derived from the stores by the validator.

The registration suite in templates.py plants every defect; these tests check the Composer's own block on a real turn,
the refusals the suite cannot express (no graph store, a placeholder), the saved-view slots, and the paths that
keep the cap defects distinct from the re-derivation ones.
"""

import copy

import pytest

from api.agents.test_agents import GRAPH, QUESTION, make_ctx
from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS
from api.genui.catalog import CATALOG, TRAVERSAL_VIEW, ComposerEvidence, component_params
from api.genui.templates import SUITES, fixture_graph, fixture_store
from api.genui.validate import validate_block
from api.stores.graph_store import GraphStore

DOCS, GRAPH_STORE = fixture_store(), fixture_graph()


def valid() -> dict:
    return copy.deepcopy(SUITES["TraversalView"]()[0])


def paths(raw, graph: GraphStore | None = GRAPH_STORE, docs=DOCS) -> set[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs, graph)
    return {i.path for i in exc.value.issues}


def test_the_fixture_block_validates_and_says_what_the_graph_signal_does():
    block = validate_block(valid(), DOCS, GRAPH_STORE)
    assert block.type == "TraversalView"
    data = block.data  # type: ignore[union-attr]
    assert [(r.rank, r.via) for r in data.reached] == [
        (1, "mentions"),
        (2, "mentions"),
        (3, "neighbour"),
        (4, "neighbour"),
    ]
    assert [(s.source, s.target, s.relation) for s in data.steps] == [("alpha", "beta", "builds_on")]
    assert data.stepsLeftOut == 0


def test_without_a_graph_store_a_traversal_cannot_be_checked_so_it_is_refused():
    assert paths(valid(), graph=None) == {"data"}


def test_placeholders_may_carry_nothing_and_need_no_graph():
    for status in ("loading", "empty"):
        raw = BUILDERS["TraversalView"]("x", status)
        assert validate_block(raw, DOCS, None).meta.status == status
        filled = valid()
        filled["meta"]["status"] = status
        assert paths(filled) == {"data"}


def test_the_re_derivation_paths_are_distinct_from_the_cap_paths():
    """A cap loosened until a defect slips through must not be masked by the re-derivation rejecting the same block at the
    cap's own path: the count and node-set mismatches have their own paths."""
    many = valid()
    many["data"]["steps"] = many["data"]["steps"] * 3
    assert "data.steps.(count)" in paths(many) and "data.steps" not in paths(many)
    fewer = valid()
    fewer["data"]["reached"].pop()
    fewer["data"]["citations"].pop()
    assert paths(fewer) == {"data.reached.(count)"}
    more = valid()
    more["data"]["nodes"].append({"id": "gamma", "label": "Gamma Cache"})
    assert paths(more) == {"data.nodes.(set)"}


def test_a_stored_node_with_another_label_a_missing_seed_and_a_foreign_chunk_are_each_refused():
    renamed = valid()
    renamed["data"]["nodes"][0]["label"] = "Alpha"
    assert "data.nodes.0.label" in paths(renamed)
    foreign = valid()
    foreign["data"]["seeds"][0]["nodeId"] = "beta"  # a real node, but the block says alpha's passages
    foreign["data"]["nodes"][0] = {"id": "beta", "label": "Beta Index"}
    got = paths(foreign)
    assert got and "data.seeds" not in got  # refused by what the re-derivation finds, not by a plain rule


def test_the_slot_is_the_concepts_the_traversal_started_from_not_the_questions_first_entities():
    (slot,) = TRAVERSAL_VIEW.slots
    assert (slot.name, slot.kind, slot.min_count, slot.max_count, slot.source) == (
        "entities",
        "entity",
        1,
        10,
        "traversal",
    )
    graph = {
        "seeds": [{"id": "x", "label": "Question Entity"}],
        "traversal": {"seeds": [{"id": "a", "label": "Alpha Method"}, {"id": "b", "label": "Beta Index"}]},
    }
    assert component_params("TraversalView", graph) == {"entities": ["Alpha Method", "Beta Index"]}
    assert component_params("TraversalView", {"seeds": [{"id": "x", "label": "Q"}], "traversal": {}}) is None
    assert component_params("GraphView", graph) == {"entities": ["Question Entity"]}  # the others still read the seeds


def evidence(traversal) -> ComposerEvidence:
    return ComposerEvidence(answer=None, graph={"traversal": traversal}, documents=(), intent="x")


def test_the_precondition_refuses_each_unmet_case_with_its_own_closed_reason():
    check = TRAVERSAL_VIEW.check
    assert check(ComposerEvidence(answer=None, graph=None, documents=(), intent="x")).reasons == ("no_graph_result",)
    assert check(evidence({})).reasons == ("nothing_resolved",)
    seed = {"id": "a", "label": "A", "match": "exact"}
    assert check(evidence({"seeds": [seed], "steps": []})).reasons == ("no_edge_followed",)
    assert check(evidence({"seeds": [seed] * 11, "steps": [{}]})).reasons == ("too_many_seeds",)
    assert check(evidence({"seeds": [seed] * 10, "steps": [{}]})).satisfied


async def test_a_real_turn_composes_a_traversal_that_validates_and_matches_the_graph_agents_own_result(
    ingested, tmp_path
):
    deps, _ = ingested
    ctx = make_ctx(deps, tmp_path)
    ctx.graph = deps.graph
    state = await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    block = next(b for b in state["composition"].blocks if b.type == "TraversalView")
    data = block.data  # type: ignore[union-attr]
    assert block.id == "blk-traversal-view" and block.meta.status == "ready"
    labels = {n.id: n.label for n in data.nodes}
    assert {labels[s.nodeId] for s in data.seeds} == {"Dense Retrieval", "BM25"}
    assert [r.rank for r in data.reached] == list(range(1, len(data.reached) + 1))
    cited = {c.id: c for c in data.citations}
    assert all(cited[r.citationId].quote and cited[r.citationId].chunkId for r in data.reached)
    # every step cites the passage its edge was extracted from
    stored = {(e.src, e.dst, e.relation): e.chunk_id for e in deps.graph.edges()}
    for step in data.steps:
        assert stored[(step.source, step.target, step.relation)] == cited[step.citationId].chunkId


async def test_composing_a_traversal_makes_no_model_call(ingested, tmp_path):
    from api.agents.compose import compose
    from api.fakes import fake_llm_responder
    from api.llm.providers.fake import FakeProvider

    deps, _ = ingested
    provider = FakeProvider(fake_llm_responder)
    ctx = make_ctx(deps, tmp_path, provider=provider)
    ctx.graph = deps.graph
    await GRAPH.ainvoke({"question": QUESTION}, context=ctx)
    before = len(provider.calls)
    composition = compose(ctx)
    assert any(b.type == "TraversalView" for b in composition.blocks)
    assert len(provider.calls) == before  # the traversal was built and validated with no provider call


def test_the_catalog_names_the_component_and_its_fences_are_the_validators_caps():
    assert "TraversalView" in CATALOG
    assert set(TRAVERSAL_VIEW.fences.caps) == {"seeds", "nodes", "steps", "reached", "label_chars"}
