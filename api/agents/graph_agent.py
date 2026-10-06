"""The Graph agent: how concepts connect, with the chunk behind every claimed connection (constraint 1).

Two tools over the GraphStore, never over a concrete backend (constraint 6):
  - find_path(a, b): the shortest path between two entities, and the edge that evidences each hop;
  - neighborhood(entity, hops): the entity's edges and the chunks that evidence them.

Every edge also carries `quote`, `page` and `doc_title` for the GraphView component: `quote` is a verbatim span of
the edge's chunk that contains BOTH endpoint labels, or None when the chunk never names them together (the
extractor saw an entity in a chunk but the chunk does not literally say so, for example across a PDF hyphen).
Such an edge stays in the payload, because the Research agent reads `chunk_ids` from it and the frozen evaluation
depends on that; the Composer is the one that leaves it out of a graph it draws.

Entities are resolved by the P0 resolver (deterministic, no model call). An edge whose chunk no longer
resolves in the DocStore is dropped, so every edge handed on points at evidence that exists. An entity
the graph does not know gives an explicit empty result carrying the resolution counts, not an exception:
"the graph found nothing" and "the graph never recognised the question" must stay distinguishable.

The agent produces data only. The Research agent reads `chunk_ids` from this agent's result on the turn
context to ground a relationship question; this module imports no other agent.
"""

from dataclasses import dataclass, field
from typing import Any

from api.agents.framework import Agent, AgentOutput, tool_spec
from api.agents.state import TurnContext
from api.genui.alignment import settle
from api.genui.catalog import cap
from api.genui.evidence import excerpt_containing
from api.genui.text import MIN_LABEL_CHARS
from api.retrieval.entities import resolve_query_entities
from api.retrieval.types import ResolutionReport
from api.stores.graph_store import Edge, GraphStore

MAX_EDGES = 12
MAX_HOPS = 2
MAX_ALIGN_SCAN = 1000  # chunks examined per entity at most: a hub entity can have hundreds
ALIGN_SLICE = 100  # chunks fetched at a time, so a scan stops as soon as every document has been looked at
MAX_ALIGN_CANDIDATES = 30  # entities examined per turn, the question's own first


@dataclass
class GraphResult:
    mode: str  # "path" | "neighborhood" | "none"
    entities: list[str] = field(default_factory=list)
    """Node ids the result is about, in the order they were asked for."""
    nodes: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    """Display label of every node in `nodes`, by node id."""
    alignment: dict[str, Any] = field(default_factory=dict)
    """Entity-by-document alignment for the question's entities (see `Alignment`), empty when there is none."""
    unquoted: int = 0
    """How many edges have no quote holding both endpoint labels (see the module note)."""
    chunk_ids: list[str] = field(default_factory=list)
    resolution: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "entities": self.entities,
            "nodes": self.nodes,
            "edges": self.edges,
            "labels": self.labels,
            "unquoted": self.unquoted,
            "alignment": self.alignment,
            "chunk_ids": self.chunk_ids,
            "resolution": self.resolution,
        }


def _summary(report: ResolutionReport) -> dict[str, Any]:
    return {
        "content_tokens": report.content_tokens,
        "covered_tokens": report.covered_tokens,
        "entities": [e.node_id for e in report.entities],
        "hit_rate": round(report.hit_rate, 3),
    }


def _edge_dicts(edges: list[Edge], graph: GraphStore, ctx: TurnContext) -> list[dict[str, Any]]:
    """Each edge with the verbatim quote that backs it (or None), plus the page and document title to cite it."""
    chunks = ctx.docs.get_chunks(list({e.chunk_id for e in edges}))
    titles: dict[str, str | None] = {}
    out: list[dict[str, Any]] = []
    for edge in edges:
        chunk = chunks.get(edge.chunk_id)
        src, dst = graph.get_node(edge.src), graph.get_node(edge.dst)
        quote = excerpt_containing(chunk.text, [src.label, dst.label]) if chunk and src and dst else None
        if edge.doc_id not in titles:
            document = ctx.docs.get_document(edge.doc_id)
            titles[edge.doc_id] = document.title if document else None
        out.append(
            {
                "src": edge.src,
                "dst": edge.dst,
                "relation": edge.relation,
                "chunk_id": edge.chunk_id,
                "doc_id": edge.doc_id,
                "quote": quote,
                "page": getattr(chunk, "page", None),
                "doc_title": titles[edge.doc_id],
            }
        )
    return out


def _order(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.src, edge.dst, edge.relation, edge.chunk_id)


def _grounded(edges: list[Edge], ctx: TurnContext) -> list[Edge]:
    """Only edges whose chunk exists in the DocStore."""
    found = ctx.docs.get_chunks(list({e.chunk_id for e in edges}))
    return [e for e in edges if e.chunk_id in found]


def _finish(
    mode: str, entities: list[str], edges: list[Edge], graph: GraphStore, report: ResolutionReport, ctx: TurnContext
) -> GraphResult:
    nodes = list(dict.fromkeys([*entities, *(n for e in edges for n in (e.src, e.dst))]))
    known = [n for n in nodes if graph.get_node(n) is not None]
    dicts = _edge_dicts(edges, graph, ctx)
    return GraphResult(
        mode=mode,
        entities=entities,
        nodes=known,
        edges=dicts,
        labels={n: node.label for n in known if (node := graph.get_node(n)) is not None},
        unquoted=sum(1 for d in dicts if d["quote"] is None),
        chunk_ids=list(dict.fromkeys(e.chunk_id for e in edges)),
        resolution=_summary(report),
    )


def _resolve_one(text: str, graph: GraphStore) -> tuple[str | None, ResolutionReport]:
    """The best node for a phrase: an exact match over an approximate one, then the first named."""
    report = resolve_query_entities(text, graph.nodes())
    ranked = sorted(report.entities, key=lambda e: e.match != "exact")  # stable: exact first
    return (ranked[0].node_id if ranked else None), report


def _path(graph: GraphStore, ctx: TurnContext, src: str, dst: str, report: ResolutionReport) -> GraphResult | None:
    """The shortest src to dst path over GROUNDED edges, one edge per hop, or None if there is none.

    Searched here rather than with `GraphStore.shortest_path`: the store's path may run through an edge
    whose chunk is gone while an equally short grounded route exists. Breadth-first over sorted edges,
    ignoring direction, so the same graph always gives the same path."""
    by_node: dict[str, list[tuple[str, Edge]]] = {}
    for edge in sorted(_grounded(graph.edges(), ctx), key=_order):
        by_node.setdefault(edge.src, []).append((edge.dst, edge))
        by_node.setdefault(edge.dst, []).append((edge.src, edge))
    came_from: dict[str, tuple[str, Edge]] = {}
    frontier = [src]
    seen = {src}
    while frontier and dst not in seen:
        following: list[str] = []
        for node in frontier:
            for neighbour, edge in by_node.get(node, []):
                if neighbour not in seen:
                    seen.add(neighbour)
                    came_from[neighbour] = (node, edge)
                    following.append(neighbour)
        frontier = following
    if dst not in came_from:
        return None
    chosen: list[Edge] = []
    node = dst
    while node != src:
        node, edge = came_from[node]
        chosen.append(edge)
    chosen.reverse()
    return _finish("path", [src, dst], chosen, graph, report, ctx)


def _neighborhood(graph: GraphStore, ctx: TurnContext, node: str, hops: int, report: ResolutionReport) -> GraphResult:
    sub = graph.expand([node], hops=max(1, min(hops, MAX_HOPS)))
    edges = sorted(_grounded(sub.edges, ctx), key=_order)[:MAX_EDGES]
    return _finish("neighborhood", [node], edges, graph, report, ctx)


def _none(report: ResolutionReport) -> GraphResult:
    return GraphResult(mode="none", resolution=_summary(report))


@dataclass
class Alignment:
    """Entities that several documents all discuss, with the stored words that show it (for ComparisonGrid)."""

    documents: list[dict[str, str]] = field(default_factory=list)
    """`{doc_id, title}`, in display order."""
    dimensions: list[dict[str, str]] = field(default_factory=list)
    """`{id, label}`: the entities, resolved ones first."""
    cells: list[dict[str, Any]] = field(default_factory=list)
    """One per (document, entity) with evidence: `{doc_id, dimension_id, chunk_id, page, quote, doc_title}`."""

    def payload(self) -> dict[str, Any]:
        return {"documents": self.documents, "dimensions": self.dimensions, "cells": self.cells}


def _align(graph: GraphStore, ctx: TurnContext, seeds: list[str]) -> Alignment:
    """The entity-by-document alignment for `seeds` and their neighbours that occur in two or more documents.

    For each (entity, document) the cell is the first stored chunk of that document that holds a verbatim sentence
    naming the entity. The entity's chunks are read in slices, in ingestion order and by page then id within a slice,
    and reading stops once every document the entity occurs in has a cell or has been ruled out, so a hub entity in
    many papers does not lose the later ones to a fixed window. Documents and entities are then settled (see `settle`): every entity kept is
    evidenced in two or more kept documents. Order: seeds first, then by number of documents, then label."""
    near = [n for n in graph.expand(seeds, hops=1).nodes if len(n.doc_ids) >= 2] if seeds else []
    neighbours = [n.id for n in sorted(near, key=lambda n: (-len(n.doc_ids), n.id))]
    ordered = list(dict.fromkeys([*seeds, *neighbours]))
    candidates = [
        n
        for n in ordered
        if (node := graph.get_node(n))
        and len(node.doc_ids) >= 2
        and MIN_LABEL_CHARS
        <= len(node.label.strip())
        <= cap("ComparisonGrid", "label_chars")  # a column the grid would drop anyway
    ][:MAX_ALIGN_CANDIDATES]
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    documents: dict[str, Any] = {}
    for node_id in candidates:
        node = graph.get_node(node_id)
        assert node is not None
        wanted = set(node.doc_ids)
        for start in range(0, min(len(node.chunk_ids), MAX_ALIGN_SCAN), ALIGN_SLICE):
            if all((d, node_id) in cells or documents.get(d, True) is None for d in wanted):
                break  # every document has its cell, or is not citable
            chunks = ctx.docs.get_chunks(list(node.chunk_ids[start : start + ALIGN_SLICE]))
            for chunk in sorted(chunks.values(), key=lambda c: (c.page or 0, c.id)):
                if (chunk.doc_id, node_id) in cells or chunk.doc_id not in wanted:
                    continue
                if chunk.doc_id not in documents:
                    document = ctx.docs.get_document(chunk.doc_id)
                    documents[chunk.doc_id] = document if document is not None and document.status == "ready" else None
                document = documents[chunk.doc_id]
                if document is None:
                    continue
                quote = excerpt_containing(chunk.text, [node.label])
                if quote is not None:
                    cells[(chunk.doc_id, node_id)] = {
                        "doc_id": chunk.doc_id,
                        "dimension_id": node_id,
                        "chunk_id": chunk.id,
                        "page": chunk.page,
                        "quote": quote,
                        "doc_title": document.title,
                    }

    per_doc: dict[str, int] = {}
    per_entity: dict[str, int] = {}
    for doc_id, node_id in cells:
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        per_entity[node_id] = per_entity.get(node_id, 0) + 1
    labels = {n: node.label for n in per_entity if (node := graph.get_node(n)) is not None}
    doc_order = sorted(per_doc, key=lambda d: (-per_doc[d], d))
    dim_order = sorted(
        (n for n in per_entity if per_entity[n] >= 2),
        key=lambda n: (
            seeds.index(n) if n in seeds else len(seeds),
            -per_entity[n],
            labels.get(n, n).lower(),
        ),
    )
    docs, dims = settle(
        doc_order,
        dim_order,
        set(cells),
        max_docs=cap("ComparisonGrid", "documents"),
        max_dims=cap("ComparisonGrid", "entities"),
    )
    if len(docs) < 2 or len(dims) < 2:
        return Alignment()
    return Alignment(
        documents=[{"doc_id": d, "title": documents[d].title} for d in docs],
        dimensions=[{"id": n, "label": labels[n]} for n in dims],
        cells=[cells[(d, n)] for d in docs for n in dims if (d, n) in cells],
    )


# ── tools ─────────────────────────────────────────────────────────────────────


async def find_path(a: str, b: str, ctx: TurnContext) -> GraphResult:
    """The shortest path between two entities and the edge, with its chunk, behind each hop."""
    graph = ctx.graph
    if graph is None:
        return _none(ResolutionReport(0, 0))
    src, report_a = _resolve_one(a, graph)
    dst, report_b = _resolve_one(b, graph)
    if src is None or dst is None or src == dst:
        return _none(report_a if src is None else report_b)
    return _path(graph, ctx, src, dst, report_b) or _none(report_b)


async def align_documents(entities: list[str], ctx: TurnContext) -> Alignment:
    """Entities (and their neighbours) that two or more documents discuss, with a verbatim quote per document."""
    graph = ctx.graph
    if graph is None:
        return Alignment()
    seeds = list(
        dict.fromkeys(
            n for e in entities[: cap("ComparisonGrid", "entities")] if (n := _resolve_one(e, graph)[0]) is not None
        )
    )
    return _align(graph, ctx, seeds)


async def neighborhood(entity: str, hops: int, ctx: TurnContext) -> GraphResult:
    """The entity's edges within a few hops and the chunks that evidence them."""
    graph = ctx.graph
    if graph is None:
        return _none(ResolutionReport(0, 0))
    node, report = _resolve_one(entity, graph)
    if node is None:
        return _none(report)
    return _neighborhood(graph, ctx, node, hops, report)


# ── the agent ─────────────────────────────────────────────────────────────────


async def _run(query: str, ctx: TurnContext) -> AgentOutput:
    """Resolve the question's entities; two or more give a path, one gives a neighbourhood."""
    graph = ctx.graph
    if graph is None:
        return AgentOutput(_none(ResolutionReport(0, 0)).payload(), status="partial", note="no graph")
    report = resolve_query_entities(query, graph.nodes())
    ids = [e.node_id for e in sorted(report.entities, key=lambda e: e.match != "exact")]
    result: GraphResult | None = None
    if len(ids) >= 2:
        result = _path(graph, ctx, ids[0], ids[1], report)
    if result is None and ids:  # one entity, or two with no path between them
        result = _neighborhood(graph, ctx, ids[0], 1, report)
    if result is None or not result.edges:
        result = _none(report)
    # Alignment needs no edges: two papers can both discuss an entity without a stored relation between them.
    result.alignment = _align(graph, ctx, ids[: cap("ComparisonGrid", "entities")]).payload() if ids else {}
    if result.mode == "none":
        return AgentOutput(result.payload(), status="partial", note="no entity resolved" if not ids else "no edges")
    return AgentOutput(result.payload())


GRAPH_AGENT = Agent(
    name="graph", run=_run, tools=(tool_spec(find_path), tool_spec(neighborhood), tool_spec(align_documents))
)
