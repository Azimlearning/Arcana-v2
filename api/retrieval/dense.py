"""Dense retrieval: embed the query, rank stored chunk vectors by cosine similarity.

Embedding the query is a paid call in live mode, so it goes through the same embedder (and spend
ledger) as ingestion. If it fails, the retriever raises and hybrid retrieval degrades to the other
signals.
"""

from __future__ import annotations

from api.core.logging import get_logger
from api.ingestion.embed import Embedder
from api.retrieval.types import TOP_K, RetrievedChunk, RetrieverResult
from api.stores.doc_store import DocStore
from api.stores.vector_store import VectorStore

log = get_logger(__name__)


class DenseRetriever:
    def __init__(self, *, vectors: VectorStore, docs: DocStore, embedder: Embedder):
        self._vectors = vectors
        self._docs = docs
        self._embedder = embedder

    async def retrieve(self, query: str, top_k: int = TOP_K) -> RetrieverResult:
        if not query.strip() or self._vectors.count() == 0:
            return RetrieverResult([])
        (vector,) = await self._embedder.embed([query])
        hits = self._vectors.query(vector, k=top_k)
        stored = self._docs.get_chunks([h.id for h in hits])
        chunks: list[RetrievedChunk] = []
        for hit in hits:
            chunk = stored.get(hit.id)
            if chunk is None:
                log.warning("dense_hit_without_chunk", chunk_id=hit.id)  # vector outlived its chunk
                continue
            chunks.append(
                RetrievedChunk(chunk.id, chunk.doc_id, chunk.text, chunk.page, hit.score, ("dense",))
            )
        return RetrieverResult(chunks)
