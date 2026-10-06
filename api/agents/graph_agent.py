"""The Graph agent: how concepts connect, with the chunk behind every claimed connection (constraint 1).

Two tools over the GraphStore, never over a concrete backend (constraint 6):
  - find_path(a, b): the shortest path between two entities, and the edge that evidences each hop;
  - neighborhood(entity, hops): the entity's edges and the chunks that evidence them.

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
from api.retrieval.entities import resolve_query_entities
from api.retrieval.types import ResolutionReport
from api.stores.graph_store import Edge, GraphStore

MAX_EDGES = 12
MAX_HOPS = 2


@dataclass
class GraphResult:
    mode: str  # "path" | "neighborhood" | "none"
    entities: list[str] = field(default_factory=list)
    """Node ids the result is about, in the order they were asked for."""
    nodes: list[str] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)
    resolution: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "entities": self.entities,
            "nodes": self.nodes,
            "edges": self.edges,
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


def _edge_dict(edge: Edge) -> dict[str, str]:
    return {
        "src": edge.src,
        "dst": edge.dst,
        "relation": edge.relation,
        "chunk_id": edge.chunk_id,
        "doc_id": edge.doc_id,
    }


def _order(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.src, edge.dst, edge.relation, edge.chunk_id)


def _grounded(edges: list[Edge], ctx: TurnContext) -> list[Edge]:
    """Only edges whose chunk exists in the DocStore."""
    found = ctx.docs.get_chunks(list({e.chunk_id for e in edges}))
    return [e for e in edges if e.chunk_id in found]


def _finish(mode: str, entities: list[str], edges: list[Edge], graph: GraphStore, report: ResolutionReport) -> GraphResult:
    nodes = list(dict.fromkeys([*entities, *(n for e in edges for n in (e.src, e.dst))]))
    return GraphResult(
        mode=mode,
        entities=entities,
        nodes=[n for n in nodes if graph.get_node(n) is not None],
        edges=[_edge_dict(e) for e in edges],
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
    return _finish("path", [src, dst], chosen, graph, report)


def _neighborhood(graph: GraphStore, ctx: TurnContext, node: str, hops: int, report: ResolutionReport) -> GraphResult:
    sub = graph.expand([node], hops=max(1, min(hops, MAX_HOPS)))
    edges = sorted(_grounded(sub.edges, ctx), key=_order)[:MAX_EDGES]
    return _finish("neighborhood", [node], edges, graph, report)


def _none(report: ResolutionReport) -> GraphResult:
    return GraphResult(mode="none", resolution=_summary(report))


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
    if result.mode == "none":
        return AgentOutput(result.payload(), status="partial", note="no entity resolved" if not ids else "no edges")
    return AgentOutput(result.payload())


GRAPH_AGENT = Agent(name="graph", run=_run, tools=(tool_spec(find_path), tool_spec(neighborhood)))
