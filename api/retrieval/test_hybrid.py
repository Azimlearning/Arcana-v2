"""hybrid_retrieve over the ingested fixture PDF: arms, degradation, fusion consistency."""

from typing import TypedDict

import pytest

from api.retrieval.arms import ARMS
from api.retrieval.dense import DenseRetriever
from api.retrieval.fusion import reciprocal_rank_fusion
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever
from api.retrieval.types import Retriever, RetrieverResult

# All three signals have something to say about this question on the fixture: the entities
# "Dense Retrieval" and "BM25" are graph nodes, and both phrases occur in the text.
QUERY = "How does Dense Retrieval compare with BM25?"


class Spy:
    """Wraps a retriever and counts calls, to prove a disabled signal is never invoked."""

    def __init__(self, inner: Retriever):
        self.inner, self.calls = inner, 0

    async def retrieve(self, query: str, top_k: int = 10) -> RetrieverResult:
        self.calls += 1
        return await self.inner.retrieve(query, top_k)


class Broken:
    async def retrieve(self, query: str, top_k: int = 10) -> RetrieverResult:
        raise RuntimeError("index is corrupt")


class Wired(TypedDict):
    dense: Spy
    sparse: Spy
    graph: Spy


def wire(deps) -> Wired:
    return {
        "dense": Spy(DenseRetriever(vectors=deps.vectors, docs=deps.docs, embedder=deps.embedder)),
        "sparse": Spy(SparseRetriever(docs=deps.docs)),
        "graph": Spy(GraphRetriever(graph=deps.graph, docs=deps.docs)),
    }


@pytest.mark.parametrize("arm", ["dense", "sparse", "graph", "flat", "hybrid"])
async def test_each_arm_uses_only_its_enabled_signals(ingested, arm: str):
    deps, _ = ingested
    r = wire(deps)
    enabled = ARMS[arm]
    result = await hybrid_retrieve(QUERY, **r, signals=enabled)

    assert result.signals == enabled and set(result.per_signal) == set(enabled)
    for signal in enabled:
        assert result.per_signal[signal], f"{signal} found nothing for the arm's own query"
    assert result.chunks and not result.failed
    for chunk in result.chunks:
        assert set(chunk.sources) <= enabled  # nothing else contributed
    for signal, spy in (("dense", r["dense"]), ("sparse", r["sparse"]), ("graph", r["graph"])):
        assert spy.calls == (1 if signal in enabled else 0)  # a disabled retriever is never called


async def test_hybrid_actually_blends_signals(ingested):
    deps, _ = ingested
    result = await hybrid_retrieve(QUERY, **wire(deps))
    seen = {s for c in result.chunks for s in c.sources}
    assert seen == {"dense", "sparse", "graph"}
    assert any(len(c.sources) > 1 for c in result.chunks)  # at least one chunk several signals agree on


async def test_fused_order_matches_a_manual_fusion_of_the_per_signal_rankings(ingested):
    deps, _ = ingested
    result = await hybrid_retrieve(QUERY, **wire(deps))
    manual = reciprocal_rank_fusion([result.per_signal[s] for s in ("dense", "sparse", "graph")])
    assert [c.id for c in result.chunks] == [c.id for c in manual][: len(result.chunks)]
    assert [c.score for c in result.chunks] == sorted((c.score for c in result.chunks), reverse=True)


async def test_a_raising_retriever_degrades_instead_of_failing(ingested):
    deps, _ = ingested
    r = wire(deps)
    result = await hybrid_retrieve(QUERY, dense=Broken(), sparse=r["sparse"], graph=r["graph"])
    assert result.failed == ("dense",) and result.per_signal["dense"] == []
    assert result.chunks  # sparse and graph still produced fused results
    assert {s for c in result.chunks for s in c.sources} <= {"sparse", "graph"}


async def test_every_retriever_failing_gives_an_empty_result_not_an_exception(ingested):
    result = await hybrid_retrieve(QUERY, dense=Broken(), sparse=Broken(), graph=Broken())
    assert result.chunks == [] and result.failed == ("dense", "sparse", "graph")


async def test_a_signal_with_no_evidence_is_empty_not_a_failure(ingested):
    deps, _ = ingested
    result = await hybrid_retrieve("zebra giraffe", **wire(deps), signals={"sparse", "graph"})
    assert result.per_signal["sparse"] == [] and result.per_signal["graph"] == []
    assert result.chunks == [] and result.failed == ()


async def test_top_k_caps_every_signal_and_the_fused_list(ingested):
    deps, _ = ingested
    result = await hybrid_retrieve(QUERY, **wire(deps), top_k=2)
    assert len(result.chunks) <= 2 and all(len(v) <= 2 for v in result.per_signal.values())


async def test_the_resolution_report_and_latency_are_returned(ingested):
    deps, _ = ingested
    result = await hybrid_retrieve(QUERY, **wire(deps))
    assert result.resolution is not None and result.resolution.any_resolved
    assert {e.node_id for e in result.resolution.entities} >= {"dense_retrieval", "bm25"}
    assert 0.0 < result.resolution.hit_rate <= 1.0 and result.latency_ms > 0
    without_graph = await hybrid_retrieve(QUERY, **wire(deps), signals={"dense", "sparse"})
    assert without_graph.resolution is None  # only the graph signal produces one


async def test_signals_must_not_be_empty(ingested):
    deps, _ = ingested
    with pytest.raises(ValueError):
        await hybrid_retrieve(QUERY, **wire(deps), signals=set())


async def test_results_are_identical_across_runs(ingested):
    deps, _ = ingested
    a = await hybrid_retrieve(QUERY, **wire(deps))
    b = await hybrid_retrieve(QUERY, **wire(deps))
    assert [(c.id, c.score) for c in a.chunks] == [(c.id, c.score) for c in b.chunks]


async def test_retriever_result_type_is_what_the_protocol_promises(ingested):
    deps, _ = ingested
    out = await SparseRetriever(docs=deps.docs).retrieve("Louvain")
    assert isinstance(out, RetrieverResult) and out.resolution is None
    assert out.chunks and out.chunks[0].sources == ("sparse",)
