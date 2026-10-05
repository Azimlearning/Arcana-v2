"""Corpus parity preflight. Run before any benchmark and after any ingest.

The five arms must retrieve over the same corpus. Chunks are stored before vectors and the graph, so
a crashed or cancelled ingest could leave text visible to the sparse signal but not to the dense or
graph signals: a silent asymmetry between arms. This returns every violation it finds; an empty list
means the three stores agree.
"""

from __future__ import annotations

from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore
from api.stores.vector_store import VectorStore

_SHOW = 5


def _sample(ids: set[str]) -> str:
    shown = sorted(ids)[:_SHOW]
    return ", ".join(shown) + (f" (+{len(ids) - _SHOW} more)" if len(ids) > _SHOW else "")


def check_corpus_parity(docs: DocStore, vectors: VectorStore, graph: GraphStore) -> list[str]:
    problems: list[str] = []
    documents = docs.list_documents()
    doc_ids = {d.id for d in documents}

    not_ready = {d.id for d in documents if d.status != "ready"}
    if not_ready:
        problems.append(f"documents not ready: {_sample(not_ready)}")

    chunk_ids = {c.id for c in docs.all_chunks()}
    vector_ids = set(vectors.ids())
    if chunk_ids - vector_ids:
        problems.append(f"chunks without a vector (dense cannot see them): {_sample(chunk_ids - vector_ids)}")
    if vector_ids - chunk_ids:
        problems.append(f"vectors without a chunk (stale): {_sample(vector_ids - chunk_ids)}")

    nodes, edges = graph.nodes(), graph.edges()
    graph_chunks = {c for n in nodes for c in n.chunk_ids} | {e.chunk_id for e in edges}
    if graph_chunks - chunk_ids:
        problems.append(f"graph references chunks that are not stored: {_sample(graph_chunks - chunk_ids)}")
    graph_docs = {d for n in nodes for d in n.doc_ids} | {e.doc_id for e in edges}
    if graph_docs - doc_ids:
        problems.append(f"graph references unknown documents: {_sample(graph_docs - doc_ids)}")
    return problems
