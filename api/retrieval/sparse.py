# Adapted from Azimlearning/Arcana (v1), api/retrieval/bm25.py @ 9a3d67f.
# Read in full and adapted for v2 (D-01, D-16): reads chunks from DocStore, returns v2's types, and
# runs the CPU-bound scoring in a worker thread so the three signals really overlap.
"""BM25 keyword retrieval over the same chunks as the dense signal (benchmark protocol).

Tokenisation is ASCII-only and minimal on purpose: results must reproduce across machines, and
Python's Unicode-aware \\w+ varies with the Unicode database version. The index is rebuilt per
query, which is fine at this corpus size; cache it if the corpus grows (P1).

Known behaviour of rank_bm25 (kept from v1 for comparability with the pilot): a term present in more
than half of the chunks gets a zero or negative idf, so on a very small corpus its hits score <= 0
and are dropped. Real corpora are large enough for this not to bite; tests use rare terms.
"""

from __future__ import annotations

import asyncio
import re

from rank_bm25 import BM25Okapi

from api.retrieval.types import TOP_K, RetrievedChunk, RetrieverResult
from api.stores.doc_store import Chunk, DocStore

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.ASCII)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _rank(chunks: list[Chunk], query_tokens: list[str], top_k: int) -> list[RetrievedChunk]:
    scores = BM25Okapi([tokenize(c.text) for c in chunks]).get_scores(query_tokens)
    # Score descending; chunk id breaks ties so the order is the same on every run.
    ranked = sorted(zip(chunks, scores, strict=True), key=lambda pair: (-pair[1], pair[0].id))
    return [
        RetrievedChunk(c.id, c.doc_id, c.text, c.page, float(score), ("sparse",))
        for c, score in ranked[:top_k]
        if score > 0.0  # a non-positive score carries no evidence and only bloats fusion
    ]


class SparseRetriever:
    def __init__(self, *, docs: DocStore):
        self._docs = docs

    async def retrieve(self, query: str, top_k: int = TOP_K) -> RetrieverResult:
        query_tokens = tokenize(query)
        chunks = self._docs.all_chunks() if query_tokens else []
        if not chunks:
            return RetrieverResult([])
        return RetrieverResult(await asyncio.to_thread(_rank, chunks, query_tokens, top_k))
