"""What the graph signal followed for one question: a read-only account of its traversal (P2c, D-33).

`GraphRetriever` (graph.py) resolves the question to nodes, expands one hop from each and ranks the chunks that
evidence what it reached. It returns the ranking but not the path. This module walks the same graph the same way and
keeps the path: the seeds (the nodes the question resolved to), the edges followed from each seed, and the chunks
reached, in the retriever's own order, with how each was reached.

It does NOT change retrieval. The retriever is frozen (D-20); this is a second, read-only walk that imports the
retriever's constants and tie-break rules, and `test_traversal.py` asserts that its chunks, scores and order equal
`GraphRetriever.retrieve` on handmade graphs and on every question of the frozen set, so the two cannot drift apart.

How a chunk was reached (`via`), strongest first, and the one reported when several seeds reach it:
  mentions   the chunk mentions a seed node (the node's own chunk list);
  edge       a relation touching a seed was extracted from the chunk, and the chunk does not mention the seed;
  neighbour  the chunk only mentions a node one hop from a seed.
The first two score the retriever's DIRECT_WEIGHT times the entity's weight, the last NEIGHBOR_WEIGHT times it.
One hop is all the graph signal expands; a view built on this says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api.retrieval.entities import resolve_query_entities
from api.retrieval.graph import DIRECT_WEIGHT, NEIGHBOR_WEIGHT
from api.retrieval.types import TOP_K, ResolutionReport
from api.stores.doc_store import DocStore
from api.stores.graph_store import Edge, GraphStore

Via = Literal["mentions", "edge", "neighbour"]
_STRENGTH: dict[Via, int] = {"mentions": 2, "edge": 1, "neighbour": 0}


@dataclass(frozen=True)
class TraversalSeed:
    node_id: str
    label: str
    match: Literal["exact", "approximate"]
    weight: float


@dataclass(frozen=True)
class TraversalStep:
    """One edge followed from a seed (one hop, either direction)."""

    seed_id: str
    edge: Edge
    hop: int = 1


@dataclass(frozen=True)
class ReachedChunk:
    chunk_id: str
    doc_id: str
    score: float
    rank: int
    """1 is the chunk the graph signal ranks first."""
    via: Via
    seed_ids: tuple[str, ...]
    """The seeds that reach the chunk (any way)."""


@dataclass(frozen=True)
class GraphTraversal:
    seeds: tuple[TraversalSeed, ...]
    steps: tuple[TraversalStep, ...]
    reached: tuple[ReachedChunk, ...]
    resolution: ResolutionReport
    steps_total: int
    """Every edge followed. `steps` is all of them; a consumer that caps what it shows says how many it left out."""


def trace_graph_signal(query: str, graph: GraphStore, docs: DocStore, top_k: int = TOP_K) -> GraphTraversal:
    """The seeds, the edges followed and the chunks reached for `query`, in the retriever's order. Pure: reads the
    stores, writes nothing, makes no model or network call."""
    nodes = graph.nodes()
    report = resolve_query_entities(query, nodes)
    if not report.entities:
        return GraphTraversal((), (), (), report, 0)

    by_id = {n.id: n for n in nodes}
    scores: dict[str, float] = {}
    support: dict[str, int] = {}
    via: dict[str, Via] = {}
    reached_by: dict[str, list[str]] = {}
    seeds: list[TraversalSeed] = []
    steps: list[TraversalStep] = []

    def reach(chunk_id: str, how: Via, seed_id: str) -> None:
        if chunk_id not in via or _STRENGTH[how] > _STRENGTH[via[chunk_id]]:
            via[chunk_id] = how
        if seed_id not in reached_by.setdefault(chunk_id, []):
            reached_by[chunk_id].append(seed_id)

    for entity in report.entities:
        seed = by_id[entity.node_id]
        seeds.append(TraversalSeed(seed.id, seed.label, entity.match, entity.weight))
        sub = graph.expand([seed.id], hops=1)
        for edge in sub.edges:
            support[edge.chunk_id] = support.get(edge.chunk_id, 0) + 1
            steps.append(TraversalStep(seed.id, edge))
        mentions = set(seed.chunk_ids)
        edge_chunks = {e.chunk_id for e in sub.edges}
        direct = mentions | edge_chunks
        neighbour = {c for n in sub.nodes if n.id != seed.id for c in n.chunk_ids} - direct
        for chunk_id in direct:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + entity.weight * DIRECT_WEIGHT
            reach(chunk_id, "mentions" if chunk_id in mentions else "edge", seed.id)
        for chunk_id in neighbour:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + entity.weight * NEIGHBOR_WEIGHT
            reach(chunk_id, "neighbour", seed.id)

    stored = docs.get_chunks(list(scores))
    ranked = sorted(
        stored,
        key=lambda cid: (-round(scores[cid], 12), -support.get(cid, 0), stored[cid].doc_id, stored[cid].ordinal),
    )
    reached = tuple(
        ReachedChunk(cid, stored[cid].doc_id, scores[cid], i, via[cid], tuple(reached_by[cid]))
        for i, cid in enumerate(ranked[:top_k], start=1)
    )
    # An edge that joins two seeds is followed from each of them: it appears once per seed, so `steps_total` counts both.
    return GraphTraversal(tuple(seeds), tuple(steps), reached, report, len(steps))


def steps_for_display(traversal: GraphTraversal, limit: int) -> tuple[tuple[TraversalStep, ...], int]:
    """The steps worth showing: those whose chunk is one of the chunks reached (the passages the signal ranked top),
    best-ranked chunk first, at most `limit`, in the order they were followed within a rank; and how many followed
    steps are not shown. A hub seed follows hundreds of edges (755 on one frozen question) and almost all lead to
    passages outside the top ranks; a view shows the edges that led to the passages the signal returned and counts the
    rest, never padding with edges that led nowhere."""
    rank = {r.chunk_id: r.rank for r in traversal.reached}
    useful = [i for i, s in enumerate(traversal.steps) if s.edge.chunk_id in rank]
    useful.sort(key=lambda i: (rank[traversal.steps[i].edge.chunk_id], i))
    kept = useful[:limit]
    return tuple(traversal.steps[i] for i in kept), len(traversal.steps) - len(kept)
