"""Store contract tests. Each store is exercised through its abstraction, then reopened from disk."""

from pathlib import Path

import numpy as np
import pytest

from api.stores.doc_store import Chunk, DocStatus, Document, Turn
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

DIM = 3072


# ── GraphStore ────────────────────────────────────────────────────────────────


def build_graph(path: Path) -> NetworkXGraphStore:
    g = NetworkXGraphStore(path)
    for node_id, doc in [("a", "d1"), ("b", "d1"), ("c", "d2"), ("d", "d3")]:
        g.upsert_node(Node(id=node_id, label=node_id.upper(), doc_ids=(doc,)))
    g.upsert_edge(Edge("a", "b", "uses", "c1", "d1"))
    g.upsert_edge(Edge("b", "c", "extends", "c2", "d2"))
    g.upsert_edge(Edge("c", "d", "cites", "c3", "d3"))
    return g


def test_graph_expand_respects_hops(tmp_path: Path):
    g = build_graph(tmp_path / "g.json")
    one = g.expand(["a"], hops=1)
    assert {e.chunk_id for e in one.edges} == {"c1"}
    two = g.expand(["a"], hops=2)
    assert {e.chunk_id for e in two.edges} == {"c1", "c2"}
    assert {n.id for n in two.nodes} == {"a", "b", "c"}


def test_graph_expand_ignores_unknown_seeds(tmp_path: Path):
    assert build_graph(tmp_path / "g.json").expand(["nope"]).edges == []


def test_graph_shortest_path_and_none(tmp_path: Path):
    g = build_graph(tmp_path / "g.json")
    assert g.shortest_path("a", "d") == ["a", "b", "c", "d"]
    g.upsert_node(Node(id="z", label="Z", doc_ids=("d9",)))
    assert g.shortest_path("a", "z") is None
    assert g.shortest_path("a", "missing") is None


def test_graph_communities_cover_all_nodes(tmp_path: Path):
    g = build_graph(tmp_path / "g.json")
    assert set().union(*g.communities()) == {"a", "b", "c", "d"}


def test_graph_node_upsert_merges_documents(tmp_path: Path):
    g = NetworkXGraphStore(tmp_path / "g.json")
    g.upsert_node(Node(id="a", label="First", doc_ids=("d1",)))
    g.upsert_node(Node(id="a", label="Second", type="Method", doc_ids=("d2",)))
    node = g.get_node("a")
    assert node is not None
    assert node.label == "First" and node.type == "Method" and node.doc_ids == ("d1", "d2")


def test_graph_edge_upsert_is_idempotent_and_needs_a_chunk(tmp_path: Path):
    g = build_graph(tmp_path / "g.json")
    g.upsert_edge(Edge("a", "b", "uses", "c1", "d1"))
    assert len(g.edges()) == 3
    with pytest.raises(ValueError):
        g.upsert_edge(Edge("a", "b", "uses", "", "d1"))
    with pytest.raises(KeyError):
        g.upsert_edge(Edge("a", "ghost", "uses", "c9", "d1"))


def test_graph_delete_document_removes_edges_and_orphans(tmp_path: Path):
    g = build_graph(tmp_path / "g.json")
    g.delete_document("d3")
    assert {e.chunk_id for e in g.edges()} == {"c1", "c2"}
    assert g.get_node("d") is None  # only d3 mentioned it
    assert g.get_node("c") is not None  # d2 still does


def test_graph_persists_across_reopen(tmp_path: Path):
    path = tmp_path / "sub" / "g.json"
    g = build_graph(path)
    g.save()
    reopened = NetworkXGraphStore(path)
    assert sorted(n.id for n in reopened.nodes()) == ["a", "b", "c", "d"]
    assert sorted(e.chunk_id for e in reopened.edges()) == ["c1", "c2", "c3"]
    assert reopened.get_node("a") == g.get_node("a")
    assert not list(path.parent.glob("*.tmp"))


# ── VectorStore ───────────────────────────────────────────────────────────────


def rand(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal((n, DIM)).astype(np.float32)


def test_vector_query_is_exact_cosine_best_first():
    v = rand(50, 1)
    store = NumpyVectorStore(Path("unused.npz"))
    store.upsert([f"id{i}" for i in range(50)], v.tolist())
    query = v[7] * 3.0  # scaled: cosine ignores magnitude
    hits = store.query(query.tolist(), k=5)
    assert hits[0].id == "id7" and hits[0].score == pytest.approx(1.0, abs=1e-5)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    expected = np.argsort(-(v / np.linalg.norm(v, axis=1, keepdims=True)) @ (query / np.linalg.norm(query)))[:5]
    assert [h.id for h in hits] == [f"id{i}" for i in expected]


def test_vector_upsert_replaces_and_delete_removes():
    store = NumpyVectorStore(Path("unused.npz"))
    a, b = rand(2, 2)
    store.upsert(["x", "y"], [a.tolist(), b.tolist()])
    store.upsert(["x"], [b.tolist()])  # x now points the way y does
    assert store.count() == 2
    assert store.query(b.tolist(), k=2)[0].score == pytest.approx(1.0, abs=1e-5)
    store.delete(["x", "never-existed"])
    assert store.count() == 1 and [h.id for h in store.query(a.tolist(), k=5)] == ["y"]


def test_vector_empty_store_and_bad_input():
    store = NumpyVectorStore(Path("unused.npz"))
    assert store.query(rand(1, 3)[0].tolist(), k=5) == []
    store.upsert(["x"], rand(1, 4).tolist())
    with pytest.raises(ValueError):
        store.upsert(["y"], [[1.0] * 8])
    with pytest.raises(ValueError):
        store.upsert(["a", "a"], rand(2, 5).tolist())
    with pytest.raises(ValueError):
        store.query([1.0] * 8)


def test_vector_persists_across_reopen(tmp_path: Path):
    path = tmp_path / "data" / "v.npz"
    v = rand(30, 6)
    store = NumpyVectorStore(path)
    store.upsert([f"id{i}" for i in range(30)], v.tolist())
    before = store.query(v[3].tolist(), k=5)
    store.save()
    reopened = NumpyVectorStore(path)
    assert reopened.count() == 30
    after = reopened.query(v[3].tolist(), k=5)
    assert [h.id for h in after] == [h.id for h in before]
    assert [h.score for h in after] == pytest.approx([h.score for h in before], abs=1e-6)
    assert not list(path.parent.glob("*.tmp"))


# ── DocStore ──────────────────────────────────────────────────────────────────


def doc(id_: str = "d1", status: DocStatus = "pending") -> Document:
    return Document(id_, "Paper", f"/x/{id_}.pdf", status, 123, None, "2026-10-05T00:00:00Z")


def test_doc_store_documents_and_chunks(tmp_path: Path):
    store = SqliteDocStore(make_engine(tmp_path / "a.db"))
    store.put_document(doc())
    store.set_status("d1", "failed", "boom")
    got = store.get_document("d1")
    assert got is not None and got.status == "failed" and got.error == "boom"

    store.put_chunks([Chunk("c2", "d1", 1, 2, "two"), Chunk("c1", "d1", 0, 1, "one")])
    assert [c.id for c in store.chunks_for_document("d1")] == ["c1", "c2"]
    assert set(store.get_chunks(["c1", "missing"])) == {"c1"}
    assert store.get_chunk("c2") == Chunk("c2", "d1", 1, 2, "two")
    assert store.get_chunks([]) == {}
    store.put_chunks([Chunk("c1", "d1", 0, 1, "one, edited")])
    chunk = store.get_chunk("c1")
    assert chunk is not None and chunk.text == "one, edited"
    assert len(store.all_chunks()) == 2


def test_doc_store_delete_cascades_to_chunks(tmp_path: Path):
    store = SqliteDocStore(make_engine(tmp_path / "a.db"))
    store.put_document(doc("d1"))
    store.put_document(doc("d2"))
    store.put_chunks([Chunk("c1", "d1", 0, 1, "x"), Chunk("c9", "d2", 0, 1, "y")])
    assert store.delete_document("d1") == ["c1"]
    assert store.get_document("d1") is None and store.get_chunk("c1") is None
    assert store.get_chunk("c9") is not None


def test_doc_store_rejects_orphan_chunks(tmp_path: Path):
    store = SqliteDocStore(make_engine(tmp_path / "a.db"))
    with pytest.raises(Exception, match="FOREIGN KEY"):
        store.put_chunks([Chunk("c1", "no-such-doc", 0, 1, "x")])


def test_doc_store_turns_and_persistence(tmp_path: Path):
    path = tmp_path / "a.db"
    store = SqliteDocStore(make_engine(path))
    store.put_document(doc())
    store.put_chunks([Chunk("c1", "d1", 0, 1, "kept")])
    store.record_turn(Turn("t1", "2026-10-05T00:00:01Z", "q?", "ok", 12, None))
    store.engine.dispose()

    reopened = SqliteDocStore(make_engine(path))
    assert reopened.get_document("d1") == doc()
    assert reopened.get_chunk("c1") == Chunk("c1", "d1", 0, 1, "kept")
    assert reopened.turns() == [Turn("t1", "2026-10-05T00:00:01Z", "q?", "ok", 12, None)]


def test_doc_store_traces_round_trip_replace_and_persist(tmp_path: Path):
    path = tmp_path / "t.db"
    store = SqliteDocStore(make_engine(path))
    assert store.get_trace("t1") is None  # never recorded
    store.record_trace("t1", '{"first": 1}')
    store.record_trace("t2", '{"other": 2}')
    store.record_trace("t1", '{"second": 1}')  # a re-record replaces, it does not duplicate
    assert store.get_trace("t1") == '{"second": 1}' and store.get_trace("t2") == '{"other": 2}'
    store.engine.dispose()
    assert SqliteDocStore(make_engine(path)).get_trace("t1") == '{"second": 1}'


def test_a_data_directory_from_before_traces_existed_still_opens_and_gains_the_table(tmp_path: Path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)  # the P0 turns table, with a row, and no turn_traces table
    old.execute(
        "CREATE TABLE turns (id VARCHAR PRIMARY KEY, created_at VARCHAR NOT NULL, query TEXT NOT NULL,"
        " outcome VARCHAR NOT NULL, latency_ms INTEGER NOT NULL, error_code VARCHAR)"
    )
    old.execute("INSERT INTO turns VALUES ('t0', '2026-10-05T00:00:00Z', 'old?', 'ok', 5, NULL)")
    old.commit()
    old.close()

    store = SqliteDocStore(make_engine(path))
    assert [t.id for t in store.turns()] == ["t0"]  # the old rows are untouched
    store.record_trace("t0", "{}")
    assert store.get_trace("t0") == "{}"


def test_graph_node_chunk_ids_merge_persist_and_prune(tmp_path: Path):
    path = tmp_path / "g.json"
    g = NetworkXGraphStore(path)
    g.upsert_node(Node(id="a", label="A", doc_ids=("d1",), chunk_ids=("d1_c1",)))
    g.upsert_node(Node(id="a", label="A", doc_ids=("d2",), chunk_ids=("d2_c9", "d1_c1")))
    node = g.get_node("a")
    assert node is not None and node.chunk_ids == ("d1_c1", "d2_c9")  # unioned, no duplicates

    g.save()
    reopened = NetworkXGraphStore(path).get_node("a")
    assert reopened is not None and reopened.chunk_ids == ("d1_c1", "d2_c9")

    g.delete_document("d2", chunk_ids=["d2_c9"])
    pruned = g.get_node("a")
    assert pruned is not None and pruned.doc_ids == ("d1",) and pruned.chunk_ids == ("d1_c1",)


def test_vector_ties_are_ordered_by_id_not_by_insertion_or_partition_luck():
    store = NumpyVectorStore(Path("unused.npz"))
    same = [1.0] + [0.0] * 7
    store.upsert(["m", "b", "z", "a"], [same, same, same, same])  # four identical vectors
    assert [h.id for h in store.query(same, k=3)] == ["a", "b", "m"]
    assert sorted(store.ids()) == ["a", "b", "m", "z"]
