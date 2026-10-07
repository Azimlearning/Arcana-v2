"""The traversal record (P2c T1): it must describe exactly what the graph retriever does.

The retriever is frozen (D-20) and is not edited; these tests are what keeps this read-only second walk in step with it:
on handmade graphs and, when the pinned live stores are present, on every question of the frozen set, the chunks reached,
their scores and their order equal `GraphRetriever.retrieve`'s.

Handmade graph (as in test_graph_retriever.py):
    alpha(c1) --[c2]-- beta(c2, c5) --[c3]-- gamma(c3, c4)      delta(c6) is unconnected.
"""

from pathlib import Path

import pytest

from api.retrieval.graph import DIRECT_WEIGHT, NEIGHBOR_WEIGHT, GraphRetriever
from api.retrieval.traversal import GraphTraversal, steps_for_display, trace_graph_signal
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
    return g, docs


async def same_as_retriever(g, docs, query: str, top_k: int = 10) -> GraphTraversal:
    """Assert the traversal's reached chunks equal the retriever's (id, score, order) and return it."""
    expected = await GraphRetriever(graph=g, docs=docs).retrieve(query, top_k)
    traversal = trace_graph_signal(query, g, docs, top_k)
    assert [(r.chunk_id, r.score) for r in traversal.reached] == [(c.id, c.score) for c in expected.chunks]
    assert [r.rank for r in traversal.reached] == list(range(1, len(expected.chunks) + 1))
    assert traversal.resolution == expected.resolution
    return traversal


async def test_the_traversal_reproduces_the_retrievers_ranking_and_says_how_each_chunk_was_reached(tmp_path: Path):
    g, docs = build(tmp_path)
    t = await same_as_retriever(g, docs, "alpha")
    assert [(r.chunk_id, r.via, r.score) for r in t.reached] == [
        ("c2", "edge", DIRECT_WEIGHT),  # alpha's relation was extracted from c2, which does not mention alpha
        ("c1", "mentions", DIRECT_WEIGHT),
        ("c5", "neighbour", NEIGHBOR_WEIGHT),  # beta's own chunk, one hop away
    ]
    assert [(s.node_id, s.match, s.weight) for s in t.seeds] == [("alpha", "exact", 1.0)]
    assert [(s.seed_id, s.edge.src, s.edge.dst, s.hop) for s in t.steps] == [("alpha", "alpha", "beta", 1)]
    assert t.steps_total == 1 and all(r.seed_ids == ("alpha",) for r in t.reached)


async def test_scores_add_across_seeds_and_the_strongest_way_is_reported(tmp_path: Path):
    g, docs = build(tmp_path)
    t = await same_as_retriever(g, docs, "alpha beta")
    by_chunk = {r.chunk_id: r for r in t.reached}
    assert (
        by_chunk["c2"].score == 2.0 and by_chunk["c2"].via == "mentions"
    )  # beta mentions it; alpha's edge made it too
    assert set(by_chunk["c2"].seed_ids) == {"alpha", "beta"}
    assert by_chunk["c1"].via == "mentions" and set(by_chunk["c1"].seed_ids) == {"alpha", "beta"}  # alpha mentions it
    assert by_chunk["c4"].via == "neighbour" and by_chunk["c4"].score == 0.5
    assert len(t.steps) == 3 and t.steps_total == 3  # alpha-beta from each seed, beta-gamma from beta
    assert [s.seed_id for s in t.steps].count("beta") == 2


async def test_two_hops_away_is_not_followed(tmp_path: Path):
    g, docs = build(tmp_path)
    t = await same_as_retriever(g, docs, "alpha")
    assert {r.chunk_id for r in t.reached} == {"c1", "c2", "c5"} and all(s.hop == 1 for s in t.steps)


async def test_an_approximate_match_and_a_missing_chunk_and_top_k_match_the_retriever(tmp_path: Path):
    extra = [Node("dense_retrieval", "dense retrieval", doc_ids=("d",), chunk_ids=("c6",))]
    g, docs = build(tmp_path, extra_nodes=extra)
    t = await same_as_retriever(g, docs, "retrieval")
    assert t.seeds[0].match == "approximate" and t.seeds[0].weight < 1.0
    (tmp_path / "x").mkdir()
    g2, docs2 = build(tmp_path / "x", stored=["c1", "c3"])
    await same_as_retriever(g2, docs2, "alpha beta")  # chunks the graph names but the doc store lacks are skipped alike
    await same_as_retriever(g, docs, "alpha beta", top_k=2)


async def test_nothing_resolved_gives_an_empty_traversal_like_the_retriever(tmp_path: Path):
    g, docs = build(tmp_path)
    t = await same_as_retriever(g, docs, "zebra giraffe")
    assert (t.seeds, t.steps, t.reached, t.steps_total) == ((), (), (), 0)
    assert not t.resolution.any_resolved


async def test_a_seed_with_no_edge_reaches_only_its_own_chunks(tmp_path: Path):
    g, docs = build(tmp_path)
    t = await same_as_retriever(g, docs, "delta")
    assert [(r.chunk_id, r.via) for r in t.reached] == [("c6", "mentions")] and t.steps == ()


async def test_a_traversal_writes_nothing_and_is_repeatable(tmp_path: Path):
    g, docs = build(tmp_path)
    before = (g.nodes(), g.edges())
    assert trace_graph_signal("alpha beta", g, docs) == trace_graph_signal("alpha beta", g, docs)
    assert (g.nodes(), g.edges()) == before


def hub_graph(tmp_path: Path, spokes: int):
    docs = SqliteDocStore(make_engine(tmp_path / "h.db"))
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "t"))
    docs.put_chunks([Chunk(f"c{i}", "d", i, 1, f"text {i}") for i in range(spokes + 1)])
    g = NetworkXGraphStore(tmp_path / "h.json")
    g.upsert_node(Node("hub", "hub", doc_ids=("d",), chunk_ids=("c0",)))
    for i in range(1, spokes + 1):
        g.upsert_node(Node(f"s{i}", f"s{i}", doc_ids=("d",), chunk_ids=(f"c{i}",)))
        g.upsert_edge(Edge("hub", f"s{i}", "r", f"c{i}", "d"))
    return g, docs


async def test_steps_for_display_shows_edges_that_led_to_returned_passages_and_counts_the_rest(tmp_path: Path):
    g, docs = hub_graph(tmp_path, 25)
    t = await same_as_retriever(g, docs, "hub")
    assert t.steps_total == 25 and len(t.reached) == 10
    returned = {r.chunk_id for r in t.reached}
    shown, left_out = steps_for_display(t, 100)
    assert {s.edge.chunk_id for s in shown} == returned  # edge support ranks the edge chunks above the hub's own
    assert left_out == 25 - len(shown) == 15  # the other edges led to passages outside the top ten
    few, more = steps_for_display(t, 3)
    assert len(few) == 3 and more == 22
    rank = {r.chunk_id: r.rank for r in t.reached}
    assert [rank[s.edge.chunk_id] for s in few] == sorted(rank[s.edge.chunk_id] for s in few)  # best-ranked first


# ── the frozen question set, on the pinned live stores when they are here ────────────────────────────────────────────

LIVE = Path(__file__).resolve().parents[2] / "data" / "eval-live-live"
QUESTIONS = Path(__file__).resolve().parents[2] / "eval" / "questions.yaml"


@pytest.mark.skipif(not (LIVE / "graph.json").exists(), reason="the pinned live stores are not on this machine")
async def test_the_traversal_equals_the_retriever_on_every_frozen_question():
    from eval.run_ablation import load_questions

    g = NetworkXGraphStore(LIVE / "graph.json")
    docs = SqliteDocStore(make_engine(LIVE / "arcana.db"))
    questions = load_questions(QUESTIONS)
    assert len(questions) == 20
    resolved = 0
    for q in questions:
        t = await same_as_retriever(g, docs, q["question"].strip())
        resolved += bool(t.seeds)
    assert resolved >= 1  # the check is not vacuous: some questions do resolve entities
