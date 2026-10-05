# Adapted from Azimlearning/Arcana (v1), api/retrieval/graph.py @ 9a3d67f.
# Read in full. Kept: the scoring idea (direct match 1.0, 1-hop neighbours 0.5, alias below exact)
# and graceful skipping of chunks that no longer exist. Changed for v2: no LLM call at query time
# (entity resolution is deterministic and logged), and chunks come from node and edge provenance.
"""Graph retrieval: resolve the query to nodes, expand one hop, rank the chunks that evidence them.

For each resolved entity (weight 1.0 exact, 0.6 approximate):
  - chunks that mention the entity, or that an edge touching it was extracted from, score its weight;
  - chunks that only mention a 1-hop neighbour score half its weight.
Scores add across entities, so a chunk that evidences several query entities rises. When nothing
resolves, the signal returns an empty ranking, logs a warning, and the resolution report says why.

Ties are common (every chunk of one exact entity scores 1.0), so they are broken by evidence, not by
chunk id, which is a hash and would make the order pseudo-random (D-20):
  1. edge support: how many relations touching the query entities were extracted from the chunk;
  2. document order: document id, then the chunk's position in it.
Neither uses the dense or sparse scores; the graph signal stays independent of the other two.

FROZEN (D-20): the weights here and the constants in entities.py. Changing any needs a declared
amendment and a GRAPH_SCORING_VERSION bump, so benchmark results can be partitioned by version.
"""

from __future__ import annotations

from api.core.logging import get_logger
from api.retrieval.entities import resolve_query_entities
from api.retrieval.types import TOP_K, RetrievedChunk, RetrieverResult
from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore

log = get_logger(__name__)

GRAPH_SCORING_VERSION = "p0-2"
DIRECT_WEIGHT = 1.0
NEIGHBOR_WEIGHT = 0.5


class GraphRetriever:
    def __init__(self, *, graph: GraphStore, docs: DocStore):
        self._graph = graph
        self._docs = docs

    async def retrieve(self, query: str, top_k: int = TOP_K) -> RetrieverResult:
        nodes = self._graph.nodes()
        report = resolve_query_entities(query, nodes)
        if not report.entities:
            log.warning(
                "graph_resolved_nothing",
                content_tokens=report.content_tokens,
                graph_nodes=len(nodes),
            )
            return RetrieverResult([], report)

        by_id = {n.id: n for n in nodes}
        scores: dict[str, float] = {}
        support: dict[str, int] = {}
        for entity in report.entities:
            seed = by_id[entity.node_id]
            sub = self._graph.expand([seed.id], hops=1)
            for edge in sub.edges:
                support[edge.chunk_id] = support.get(edge.chunk_id, 0) + 1
            direct = set(seed.chunk_ids) | {e.chunk_id for e in sub.edges}
            neighbor = {c for n in sub.nodes if n.id != seed.id for c in n.chunk_ids} - direct
            for chunk_id in direct:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + entity.weight * DIRECT_WEIGHT
            for chunk_id in neighbor:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + entity.weight * NEIGHBOR_WEIGHT

        stored = self._docs.get_chunks(list(scores))
        for chunk_id in scores.keys() - stored.keys():
            log.warning("graph_hit_without_chunk", chunk_id=chunk_id)  # graph outlived its chunk
        # Round before comparing so a float sum that differs by an ulp cannot reorder a true tie.
        ranked = sorted(
            stored,
            key=lambda cid: (
                -round(scores[cid], 12),
                -support.get(cid, 0),
                stored[cid].doc_id,
                stored[cid].ordinal,
            ),
        )
        chunks: list[RetrievedChunk] = []
        for chunk_id in ranked:
            chunk = stored[chunk_id]
            chunks.append(
                RetrievedChunk(
                    chunk.id, chunk.doc_id, chunk.text, chunk.page, scores[chunk_id], ("graph",)
                )
            )
            if len(chunks) == top_k:
                break
        return RetrieverResult(chunks, report)
