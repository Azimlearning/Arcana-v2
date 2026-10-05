from pathlib import Path

import numpy as np

from api.stores.doc_store import Chunk, Document
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.stores.preflight import check_corpus_parity


def stores(tmp_path: Path):
    return (
        SqliteDocStore(make_engine(tmp_path / "a.db")),
        NumpyVectorStore(tmp_path / "v.npz"),
        NetworkXGraphStore(tmp_path / "g.json"),
    )


def consistent(tmp_path: Path):
    docs, vectors, graph = stores(tmp_path)
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-05"))
    docs.put_chunks([Chunk("c1", "d", 0, 1, "x"), Chunk("c2", "d", 1, 1, "y")])
    vectors.upsert(["c1", "c2"], np.eye(2, 8).tolist())
    graph.upsert_node(Node("a", "a", doc_ids=("d",), chunk_ids=("c1",)))
    graph.upsert_node(Node("b", "b", doc_ids=("d",), chunk_ids=("c2",)))
    graph.upsert_edge(Edge("a", "b", "r", "c2", "d"))
    return docs, vectors, graph


def test_a_consistent_corpus_has_no_problems(tmp_path: Path):
    assert check_corpus_parity(*consistent(tmp_path)) == []


def test_a_chunk_without_a_vector_is_reported(tmp_path: Path):
    docs, vectors, graph = consistent(tmp_path)
    vectors.delete(["c2"])
    (problem,) = check_corpus_parity(docs, vectors, graph)
    assert "without a vector" in problem and "c2" in problem


def test_a_stale_vector_is_reported(tmp_path: Path):
    docs, vectors, graph = consistent(tmp_path)
    vectors.upsert(["ghost"], [[1.0] * 8])
    assert any("without a chunk" in p and "ghost" in p for p in check_corpus_parity(docs, vectors, graph))


def test_a_document_that_is_not_ready_is_reported(tmp_path: Path):
    docs, vectors, graph = consistent(tmp_path)
    docs.set_status("d", "embedding")
    assert any("not ready" in p for p in check_corpus_parity(docs, vectors, graph))


def test_graph_references_to_missing_chunks_or_documents_are_reported(tmp_path: Path):
    docs, vectors, graph = consistent(tmp_path)
    graph.upsert_node(Node("z", "z", doc_ids=("nope",), chunk_ids=("c9",)))
    problems = check_corpus_parity(docs, vectors, graph)
    assert any("not stored" in p and "c9" in p for p in problems)
    assert any("unknown documents" in p and "nope" in p for p in problems)
