"""GraphRetriever scoring on a handmade graph, so every expected score can be computed by hand.

Graph:  alpha(c1) --[c2]-- beta(c2, c5) --[c3]-- gamma(c3, c4)      delta(c6) is unconnected.
Edge labels are the chunk each relation was extracted from.
"""

from pathlib import Path

import pytest

from api.retrieval.entities import APPROX_WEIGHT
from api.retrieval.graph import DIRECT_WEIGHT, NEIGHBOR_WEIGHT, GraphRetriever
from api.stores.doc_store import Chunk, Document
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

CHUNKS = ["c1", "c2", "c3", "c4", "c5", "c6"]


def build(tmp_path: Path, *, stored: list[str] = CHUNKS, extra_nodes: list[Node] | None = None):
    docs = SqliteDocStore(make_engine(tmp_path / "a.db"))
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-05"))
    docs.put_chunks([Chunk(c, "d", i, 1, f"text {c}") for i, c in enumerate(stored)])
    g = NetworkXGraphStore(tmp_path / "g.json")
    for id_, chunks in [("alpha", ("c1",)), ("beta", ("c2", "c5")), ("gamma", ("c3", "c4")), ("delta", ("c6",))]:
        g.upsert_node(Node(id=id_, label=id_, doc_ids=("d",), chunk_ids=chunks))
    for node in extra_nodes or []:
        g.upsert_node(node)
    g.upsert_edge(Edge("alpha", "beta", "r", "c2", "d"))
    g.upsert_edge(Edge("beta", "gamma", "r", "c3", "d"))
    return GraphRetriever(graph=g, docs=docs)


def scores(result) -> dict[str, float]:
    return {c.id: c.score for c in result.chunks}


async def test_direct_chunks_and_edge_chunks_score_full_neighbors_half(tmp_path: Path):
    result = await build(tmp_path).retrieve("alpha")
    # direct: alpha's own c1 and its edge's c2 -> 1.0.   neighbor beta adds c5 (c2 is already direct) -> 0.5
    assert scores(result) == {"c1": DIRECT_WEIGHT, "c2": DIRECT_WEIGHT, "c5": NEIGHBOR_WEIGHT}
    # c1 and c2 tie at 1.0. c2 leads: a relation touching alpha was extracted from it (edge support).
    assert [c.id for c in result.chunks] == ["c2", "c1", "c5"]
    assert all(c.sources == ("graph",) for c in result.chunks)


async def test_scores_add_across_query_entities(tmp_path: Path):
    result = await build(tmp_path).retrieve("alpha beta")
    # alpha: direct c1, c2; neighbor c5.   beta: direct c2, c5, c3; neighbors c1 and c4 at 0.5.
    assert scores(result) == {"c2": 2.0, "c1": 1.5, "c5": 1.5, "c3": 1.0, "c4": 0.5}
    # c1 and c5 tie at 1.5 with no edge support: document order decides (c1 comes first in the document)
    assert [c.id for c in result.chunks] == ["c2", "c1", "c5", "c3", "c4"]


async def test_two_hops_away_is_not_reached(tmp_path: Path):
    result = await build(tmp_path).retrieve("alpha")
    assert "c3" not in scores(result) and "c4" not in scores(result)  # gamma is 2 hops from alpha


async def test_an_approximate_match_scores_below_an_exact_one(tmp_path: Path):
    retriever = build(tmp_path, extra_nodes=[Node("dense_retrieval", "dense retrieval", doc_ids=("d",), chunk_ids=("c6",))])
    # "retrieval" is not a node, but shares half of dense_retrieval's tokens
    result = await retriever.retrieve("retrieval")
    assert scores(result) == {"c6": pytest.approx(APPROX_WEIGHT * DIRECT_WEIGHT)}
    assert result.resolution is not None and result.resolution.entities[0].match == "approximate"


async def test_nothing_resolved_returns_empty_with_a_zero_hit_rate(tmp_path: Path):
    result = await build(tmp_path).retrieve("zebra giraffe")
    assert result.chunks == []
    assert result.resolution is not None
    assert result.resolution.hit_rate == 0.0 and not result.resolution.any_resolved


async def test_the_resolution_report_rides_along_with_hits(tmp_path: Path):
    result = await build(tmp_path).retrieve("tell me about alpha and beta")
    assert result.resolution is not None
    assert {e.node_id for e in result.resolution.entities} == {"alpha", "beta"}
    assert result.resolution.hit_rate == 1.0


async def test_top_k_caps_the_ranking(tmp_path: Path):
    result = await build(tmp_path).retrieve("alpha beta", top_k=2)
    assert [c.id for c in result.chunks] == ["c2", "c1"]


async def test_a_graph_hit_whose_chunk_was_deleted_is_skipped(tmp_path: Path):
    result = await build(tmp_path, stored=["c1", "c3", "c4", "c5", "c6"]).retrieve("alpha")  # c2 gone
    assert "c2" not in scores(result) and scores(result)["c1"] == DIRECT_WEIGHT


async def test_an_empty_graph_returns_nothing(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "a.db"))
    result = await GraphRetriever(graph=NetworkXGraphStore(tmp_path / "g.json"), docs=docs).retrieve("alpha")
    assert result.chunks == [] and result.resolution is not None


async def test_ties_without_edge_support_follow_document_order_not_chunk_id(tmp_path: Path):
    # Names chosen so alphabetical id order is the OPPOSITE of document order: zz1 is ordinal 0.
    docs = SqliteDocStore(make_engine(tmp_path / "a.db"))
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-05"))
    docs.put_chunks([Chunk("zz1", "d", 0, 1, "x"), Chunk("aa2", "d", 1, 1, "y")])
    g = NetworkXGraphStore(tmp_path / "g.json")
    g.upsert_node(Node("alpha", "alpha", doc_ids=("d",), chunk_ids=("aa2", "zz1")))
    result = await GraphRetriever(graph=g, docs=docs).retrieve("alpha")
    assert [c.id for c in result.chunks] == ["zz1", "aa2"]


async def test_nothing_resolved_is_logged_loudly(tmp_path: Path):
    import structlog

    with structlog.testing.capture_logs() as logs:
        await build(tmp_path).retrieve("zebra giraffe")
    assert any(e["event"] == "graph_resolved_nothing" and e["log_level"] == "warning" for e in logs)
