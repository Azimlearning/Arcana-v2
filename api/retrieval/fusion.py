# Adapted from Azimlearning/Arcana (v1), api/retrieval/fusion.py @ 9a3d67f.
# Read in full and adapted for v2 (D-01, D-16): chunks record every contributing signal, and ties
# break deterministically (v1 relied on dict insertion order).
"""Reciprocal Rank Fusion: score(chunk) = sum over rankings of 1 / (k + rank), rank from 1.

Rank-based on purpose: cosine similarity, BM25 scores and graph weights live on different scales,
so scores are discarded and only positions are used. A chunk in several rankings is boosted
additively; a chunk in one ranking still scores. This single function is the only difference
between the "flat" arm (dense + sparse) and the "hybrid" arm (plus graph) in the ablation.
"""

from __future__ import annotations

from api.retrieval.types import RRF_K, RetrievedChunk, Signal


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], *, k: int = RRF_K
) -> list[RetrievedChunk]:
    """Fuse ranked lists into one, best first, de-duplicated by chunk id.

    Ties break by the best (lowest) rank the chunk achieved in any list, then by chunk id, so the
    order is identical on every run and machine.
    """
    if k < 1:
        raise ValueError(f"RRF k must be >= 1 (got {k})")

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    sources: dict[str, list[Signal]] = {}
    first: dict[str, RetrievedChunk] = {}

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            best_rank[chunk.id] = min(best_rank.get(chunk.id, rank), rank)
            first.setdefault(chunk.id, chunk)
            seen = sources.setdefault(chunk.id, [])
            for source in chunk.sources:
                if source not in seen:
                    seen.append(source)

    # Round for ordering only: mathematically tied sums can differ by an ulp, and rank must decide.
    order = sorted(scores, key=lambda cid: (-round(scores[cid], 12), best_rank[cid], cid))
    return [
        RetrievedChunk(
            id=cid,
            doc_id=first[cid].doc_id,
            text=first[cid].text,
            page=first[cid].page,
            score=scores[cid],
            sources=tuple(sources[cid]),
        )
        for cid in order
    ]
