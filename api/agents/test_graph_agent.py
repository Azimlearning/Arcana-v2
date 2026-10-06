"""The Graph agent on a handmade graph: paths, neighbourhoods, grounded edges, honest empties (P1 A6)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from api.agents.framework import AgentOutput
from api.agents.graph_agent import GRAPH_AGENT, find_path, neighborhood
from api.agents.research import graph_evidence
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore

# dense_retrieval -- vector_index -- cosine_similarity       bm25 -- inverted_index
#        \_______ embedding _______/   (a longer way round)        lonely_concept (no edges)
NODES = ["dense_retrieval", "vector_index", "cosine_similarity", "embedding", "bm25", "inverted_index", "lonely_concept"]
EDGES = [
    ("dense_retrieval", "vector_index", "uses", "c1", "d1"),
    ("vector_index", "cosine_similarity", "ranks_by", "c2", "d1"),
    ("dense_retrieval", "embedding", "produces", "c3", "d1"),
    ("embedding", "cosine_similarity", "compared_with", "c4", "d1"),
    ("bm25", "inverted_index", "uses", "c5", "d2"),
]
CHUNKS = {f"c{i}": SimpleNamespace(id=f"c{i}", doc_id="d1" if i < 5 else "d2", page=i, text=f"Chunk {i} text.") for i in range(1, 6)}


def make_graph(tmp_path: Path) -> NetworkXGraphStore:
    graph = NetworkXGraphStore(tmp_path / "g.json")
    for node in NODES:
        graph.upsert_node(Node(id=node, label=node.replace("_", " ")))
    for src, dst, relation, chunk, doc in EDGES:
        graph.upsert_edge(Edge(src, dst, relation, chunk, doc))
    return graph


def make_ctx(tmp_path: Path, *, graph: Any = "default", missing: tuple[str, ...] = ()) -> TurnContext:
    known = {k: v for k, v in CHUNKS.items() if k not in missing}
    docs: Any = SimpleNamespace(get_chunks=lambda ids: {i: known[i] for i in ids if i in known})
    none: Any = None
    return TurnContext(
        docs, none, none, TokenBudget(), "blk", graph=make_graph(tmp_path) if graph == "default" else graph
    )


def edge_triples(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(e["src"], e["dst"], e["chunk_id"]) for e in payload["edges"]]


# ── find_path ─────────────────────────────────────────────────────────────────


async def test_find_path_returns_the_shortest_path_with_the_edge_behind_each_hop(tmp_path: Path):
    result = await find_path("dense retrieval", "cosine similarity", make_ctx(tmp_path))
    assert result.mode == "path"
    # Two routes of two hops exist; the search is deterministic and takes the alphabetically first.
    assert edge_triples({"edges": result.edges}) == [
        ("dense_retrieval", "embedding", "c3"),
        ("embedding", "cosine_similarity", "c4"),
    ]
    assert result.chunk_ids == ["c3", "c4"]
    assert result.entities == ["dense_retrieval", "cosine_similarity"]


async def test_a_path_is_the_same_every_time(tmp_path: Path):
    first = await find_path("dense retrieval", "cosine similarity", make_ctx(tmp_path))
    again = await find_path("dense retrieval", "cosine similarity", make_ctx(tmp_path))
    assert first == again


async def test_a_path_routes_around_an_ungrounded_chunk_when_an_equally_short_route_exists(tmp_path: Path):
    result = await find_path("dense retrieval", "cosine similarity", make_ctx(tmp_path, missing=("c3",)))
    assert result.mode == "path" and result.chunk_ids == ["c1", "c2"]  # via vector_index instead


async def test_a_path_follows_edges_against_their_direction(tmp_path: Path):
    result = await find_path("cosine similarity", "dense retrieval", make_ctx(tmp_path))
    assert result.mode == "path" and len(result.edges) == 2  # edges are stored the other way round


async def test_two_entities_in_different_components_have_no_path(tmp_path: Path):
    result = await find_path("dense retrieval", "bm25", make_ctx(tmp_path))
    assert result.mode == "none" and result.edges == []


async def test_a_path_through_an_ungrounded_chunk_is_not_returned(tmp_path: Path):
    # Both routes between dense_retrieval and cosine_similarity lose a chunk, so no grounded path remains.
    result = await find_path("dense retrieval", "cosine similarity", make_ctx(tmp_path, missing=("c1", "c3")))
    assert result.mode == "none"


# ── neighborhood ──────────────────────────────────────────────────────────────


async def test_neighborhood_returns_the_entitys_edges_and_their_chunks(tmp_path: Path):
    result = await neighborhood("dense retrieval", 1, make_ctx(tmp_path))
    assert result.mode == "neighborhood"
    assert {e["chunk_id"] for e in result.edges} == {"c1", "c3"}
    assert "dense_retrieval" in result.nodes and "embedding" in result.nodes


async def test_more_hops_reach_further_but_are_clamped(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    one = await neighborhood("dense retrieval", 1, ctx)
    two = await neighborhood("dense retrieval", 2, ctx)
    huge = await neighborhood("dense retrieval", 99, ctx)
    assert len(two.edges) > len(one.edges)
    assert huge.edges == two.edges  # clamped to two hops
    assert "bm25" not in huge.nodes


async def test_every_edge_in_every_result_has_a_chunk_that_resolves(tmp_path: Path):
    ctx = make_ctx(tmp_path, missing=("c2",))
    results = [
        await find_path("dense retrieval", "cosine similarity", ctx),
        await neighborhood("dense retrieval", 2, ctx),
        await neighborhood("bm25", 1, ctx),
    ]
    for result in results:
        assert result.edges, result.mode
        for edge in result.edges:
            assert ctx.docs.get_chunks([edge["chunk_id"]]), edge  # resolves in the DocStore
            assert edge["chunk_id"] != "c2"  # the dangling one was dropped


# ── unresolvable entities ─────────────────────────────────────────────────────


async def test_an_unknown_entity_gives_an_explicit_empty_result_with_the_resolution_report(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    for result in (await neighborhood("quantum chromodynamics", 1, ctx), await find_path("zebra", "quark", ctx)):
        assert result.mode == "none" and result.edges == [] and result.chunk_ids == []
        assert result.resolution["covered_tokens"] == 0 and result.resolution["content_tokens"] > 0


async def test_a_known_entity_with_no_edges_gives_an_empty_result(tmp_path: Path):
    result = await neighborhood("lonely concept", 1, make_ctx(tmp_path))
    assert result.mode == "neighborhood" and result.edges == []  # recognised, but nothing connects to it


async def test_with_no_graph_store_the_tools_return_empty_results(tmp_path: Path):
    ctx = make_ctx(tmp_path, graph=None)
    assert (await neighborhood("dense retrieval", 1, ctx)).mode == "none"
    assert (await find_path("a", "b", ctx)).mode == "none"


# ── the agent ─────────────────────────────────────────────────────────────────


async def run(tmp_path: Path, query: str, **kw: Any) -> AgentOutput:
    return await GRAPH_AGENT.run(query, make_ctx(tmp_path, **kw))


async def test_two_entities_in_the_question_give_a_path(tmp_path: Path):
    out = await run(tmp_path, "How is dense retrieval related to cosine similarity?")
    assert out.status == "ok" and out.payload["mode"] == "path"
    assert set(out.payload["chunk_ids"]) <= {"c1", "c2", "c3", "c4"}


async def test_one_entity_gives_its_neighbourhood(tmp_path: Path):
    out = await run(tmp_path, "What is BM25 connected to?")
    assert out.payload["mode"] == "neighborhood" and out.payload["chunk_ids"] == ["c5"]


async def test_two_entities_with_no_path_fall_back_to_the_first_ones_neighbourhood(tmp_path: Path):
    out = await run(tmp_path, "How is dense retrieval related to bm25?")
    assert out.status == "ok" and out.payload["mode"] == "neighborhood"


async def test_a_question_naming_nothing_in_the_graph_is_partial_not_a_failure(tmp_path: Path):
    out = await run(tmp_path, "Why is the sky blue?")
    assert out.status == "partial" and out.note == "no entity resolved"
    assert out.payload["mode"] == "none" and out.payload["resolution"]["covered_tokens"] == 0


async def test_the_agent_is_partial_when_the_turn_has_no_graph(tmp_path: Path):
    out = await run(tmp_path, "How is dense retrieval related to bm25?", graph=None)
    assert out.status == "partial" and out.note == "no graph"


def test_the_agents_tools_have_schemas_without_the_injected_context():
    schemas = {t.name: t.input_schema for t in GRAPH_AGENT.tools}
    assert set(schemas) == {"find_path", "neighborhood"}
    assert schemas["find_path"]["required"] == ["a", "b"]
    assert schemas["neighborhood"]["properties"]["hops"] == {"type": "integer"}
    assert "ctx" not in schemas["neighborhood"]["properties"]


# ── research reads the graph's evidence from the turn, not from the agent ─────


async def test_research_leads_with_the_chunks_the_graph_agent_found(tmp_path: Path):
    from api.agents.framework import route_to_agent
    from api.agents.roster import default_roster

    ctx = make_ctx(tmp_path)
    ctx.roster = default_roster()
    await route_to_agent(ctx, "graph", "How is dense retrieval related to cosine similarity?")
    chunks = graph_evidence(ctx)
    assert chunks and all(c.sources == ("graph",) for c in chunks)
    assert [c.id for c in chunks] == ctx.results["graph"].payload["chunk_ids"][: len(chunks)]


def test_without_a_graph_result_there_is_no_graph_evidence(tmp_path: Path):
    assert graph_evidence(make_ctx(tmp_path)) == []
