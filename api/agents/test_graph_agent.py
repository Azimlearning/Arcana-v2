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
NODES = [
    "dense_retrieval",
    "vector_index",
    "cosine_similarity",
    "embedding",
    "bm25",
    "inverted_index",
    "lonely_concept",
]
EDGES = [
    ("dense_retrieval", "vector_index", "uses", "c1", "d1"),
    ("vector_index", "cosine_similarity", "ranks_by", "c2", "d1"),
    ("dense_retrieval", "embedding", "produces", "c3", "d1"),
    ("embedding", "cosine_similarity", "compared_with", "c4", "d1"),
    ("bm25", "inverted_index", "uses", "c5", "d2"),
]
CHUNKS = {
    f"c{i}": SimpleNamespace(id=f"c{i}", doc_id="d1" if i < 5 else "d2", page=i, text=f"Chunk {i} text.")
    for i in range(1, 6)
}


def make_graph(tmp_path: Path) -> NetworkXGraphStore:
    graph = NetworkXGraphStore(tmp_path / "g.json")
    for node in NODES:
        graph.upsert_node(Node(id=node, label=node.replace("_", " ")))
    for src, dst, relation, chunk, doc in EDGES:
        graph.upsert_edge(Edge(src, dst, relation, chunk, doc))
    return graph


def make_ctx(
    tmp_path: Path, *, graph: Any = "default", missing: tuple[str, ...] = (), chunks: dict[str, Any] | None = None
) -> TurnContext:
    known = {k: v for k, v in (chunks or CHUNKS).items() if k not in missing}
    docs: Any = SimpleNamespace(
        get_chunks=lambda ids: {i: known[i] for i in ids if i in known},
        get_document=lambda doc_id: SimpleNamespace(title=f"Paper {doc_id}"),
    )
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
    assert set(schemas) == {"find_path", "neighborhood", "align_documents"}
    assert schemas["align_documents"]["required"] == ["entities"]
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


async def test_a_comparison_pools_the_graphs_evidence_with_retrieval(tmp_path: Path):
    from api.agents.research import compare_documents
    from api.retrieval.types import RetrievalResult, RetrievedChunk

    async def retrieve(q: str) -> RetrievalResult:
        other = RetrievedChunk("c5", "d2", "Chunk 5 text.", 5, 1.0, ("dense",))
        return RetrievalResult(chunks=[other], per_signal={})

    from api.agents.framework import route_to_agent
    from api.agents.roster import default_roster

    ctx = make_ctx(tmp_path)
    ctx.roster, ctx.retrieve = default_roster(), retrieve
    await route_to_agent(ctx, "graph", "How is dense retrieval related to cosine similarity?")
    picked = [c.id for c in await compare_documents("q", ctx)]
    assert picked[0] in {"c3", "c4", "c1", "c2"} and "c5" in picked  # graph evidence from d1, retrieval from d2


def test_without_a_graph_result_there_is_no_graph_evidence(tmp_path: Path):
    assert graph_evidence(make_ctx(tmp_path)) == []


# ── quotes for the graph view ─────────────────────────────────────────────────

LABELLED = {
    **CHUNKS,
    "c1": SimpleNamespace(
        id="c1",
        doc_id="d1",
        page=3,
        text="Dense retrieval uses a vector index to find passages quickly. It scales well.",
    ),
}


async def test_an_edge_whose_chunk_names_both_labels_carries_a_verbatim_quote_page_and_title(tmp_path: Path):
    result = await neighborhood("dense retrieval", 1, make_ctx(tmp_path, chunks=LABELLED))
    by_chunk = {e["chunk_id"]: e for e in result.edges}
    grounded = by_chunk["c1"]
    assert grounded["quote"] == "Dense retrieval uses a vector index to find passages quickly."
    assert grounded["quote"] in LABELLED["c1"].text
    assert grounded["page"] == 3 and grounded["doc_title"] == "Paper d1"
    assert result.labels["dense_retrieval"] == "dense retrieval" and result.labels["vector_index"] == "vector index"


async def test_an_edge_whose_chunk_does_not_name_both_labels_stays_but_has_no_quote(tmp_path: Path):
    result = await neighborhood("dense retrieval", 1, make_ctx(tmp_path, chunks=LABELLED))
    by_chunk = {e["chunk_id"]: e for e in result.edges}
    assert by_chunk["c3"]["quote"] is None  # "Chunk 3 text." names neither entity
    assert result.unquoted == 1
    assert "c3" in result.chunk_ids  # still evidence for the Research agent: chunk_ids is unchanged


# ── align_documents: entities several documents all discuss ───────────────────

from api.agents.graph_agent import align_documents  # noqa: E402


def two_paper_world(tmp_path: Path, *, drop: tuple[str, ...] = (), third_paper: bool = False):
    """Dense retrieval and BM25 appear in papers d1 and d2 (and, optionally, dense retrieval alone in d3)."""
    texts = {
        "k1": ("d1", 1, "Paper one studies dense retrieval with learned embeddings. It is fast."),
        "k2": ("d2", 4, "In paper two, dense retrieval is compared against sparse baselines."),
        "k3": ("d1", 2, "The first paper also reports BM25 as its sparse baseline."),
        "k4": ("d2", 5, "Paper two treats BM25 as the strongest sparse method."),
        "k5": ("d3", 7, "The third paper only discusses dense retrieval at length."),
        "k6": ("d1", 3, "Louvain communities are mentioned once, in paper one only."),
    }
    chunks = {i: SimpleNamespace(id=i, doc_id=d, page=p, text=t) for i, (d, p, t) in texts.items() if i not in drop}
    graph = NetworkXGraphStore(tmp_path / "align.json")
    graph.upsert_node(
        Node(
            "dense",
            "dense retrieval",
            doc_ids=("d1", "d2", "d3") if third_paper else ("d1", "d2"),
            chunk_ids=("k1", "k2", "k5") if third_paper else ("k1", "k2"),
        )
    )
    graph.upsert_node(Node("bm25", "BM25", doc_ids=("d1", "d2"), chunk_ids=("k3", "k4")))
    graph.upsert_node(Node("louvain", "Louvain communities", doc_ids=("d1",), chunk_ids=("k6",)))
    graph.upsert_edge(Edge("dense", "bm25", "compared_with", "k2", "d2"))
    graph.upsert_edge(Edge("dense", "louvain", "unrelated", "k6", "d1"))
    docs: Any = SimpleNamespace(
        get_chunks=lambda ids: {i: chunks[i] for i in ids if i in chunks},
        get_document=lambda d: SimpleNamespace(id=d, title=f"Paper {d}", status="ready"),
    )
    none: Any = None
    return TurnContext(docs, none, none, TokenBudget(), "blk", graph=graph)


async def test_two_papers_sharing_two_entities_align_with_a_verbatim_quote_in_each_cell(tmp_path: Path):
    ctx = two_paper_world(tmp_path)
    result = await align_documents(["dense retrieval", "bm25"], ctx)
    assert [d["doc_id"] for d in result.documents] == ["d1", "d2"]
    assert [d["label"] for d in result.dimensions] == ["dense retrieval", "BM25"]  # the question's order
    assert len(result.cells) == 4
    chunks = ctx.docs.get_chunks(["k1", "k2", "k3", "k4"])
    for cell in result.cells:
        label = next(d["label"] for d in result.dimensions if d["id"] == cell["dimension_id"])
        chunk = chunks[cell["chunk_id"]]
        assert chunk.doc_id == cell["doc_id"] and cell["quote"] in chunk.text  # of that paper, verbatim
        assert label.lower() in cell["quote"].lower()
        assert cell["doc_title"] == f"Paper {cell['doc_id']}" and cell["page"] == chunk.page


async def test_an_entity_in_one_paper_only_is_never_a_dimension(tmp_path: Path):
    result = await align_documents(["dense retrieval", "bm25", "louvain communities"], two_paper_world(tmp_path))
    assert [d["id"] for d in result.dimensions] == ["dense", "bm25"]


async def test_an_entity_whose_chunks_never_name_it_has_no_cell_and_can_fall_away(tmp_path: Path):
    # Without k4, BM25 is evidenced in one paper only, so it stops being a dimension: one entity is not a comparison.
    result = await align_documents(["dense retrieval", "bm25"], two_paper_world(tmp_path, drop=("k4",)))
    assert result.cells == []


async def test_a_paper_that_covers_only_some_entities_gets_cells_only_for_those(tmp_path: Path):
    result = await align_documents(["dense retrieval", "bm25"], two_paper_world(tmp_path, third_paper=True))
    assert [d["doc_id"] for d in result.documents] == ["d1", "d2", "d3"]
    d3 = [c for c in result.cells if c["doc_id"] == "d3"]
    assert all(c["dimension_id"] == "dense" for c in d3)  # BM25 is not in d3: no cell, and no placeholder


async def test_alignment_is_the_same_every_time_and_comes_with_the_agent_payload(tmp_path: Path):
    first = await align_documents(["dense retrieval", "bm25"], two_paper_world(tmp_path))
    again = await align_documents(["dense retrieval", "bm25"], two_paper_world(tmp_path))
    assert first == again
    output = await GRAPH_AGENT.run("How does dense retrieval compare with BM25?", two_paper_world(tmp_path))
    assert output.payload["alignment"]["dimensions"] == first.dimensions


async def test_whatever_the_graph_looks_like_every_cell_is_that_papers_own_verbatim_words(tmp_path: Path):
    """Property test over random handmade graphs: a cell the evidence does not support is never produced."""
    import random

    from api.genui.catalog import cap

    max_docs, max_dims = cap("ComparisonGrid", "documents"), cap("ComparisonGrid", "entities")
    from api.genui.text import label_in_quote, normalise

    rng = random.Random(11)
    labels = ["Dense retrieval", "BM25", "Louvain", "Reciprocal rank fusion", "Knowledge graph", "Chunking", "HyDE"]
    produced = 0
    key = lambda n: labels[n].lower().replace(" ", "_")  # noqa: E731 - the resolver matches on the normalised name
    for trial in range(40):
        docs_n = rng.randint(1, 5)
        graph = NetworkXGraphStore(tmp_path / f"p{trial}.json")
        chunks: dict[str, Any] = {}
        node_chunks: dict[int, list[str]] = {n: [] for n in range(len(labels))}
        node_docs: dict[int, set[str]] = {n: set() for n in range(len(labels))}
        for d in range(docs_n):
            for k in range(rng.randint(1, 4)):
                named = [n for n in range(len(labels)) if rng.random() < 0.4]
                text = " ".join(f"The paper discusses {labels[n]} here." for n in named) or "Nothing relevant is said."
                cid = f"t{trial}_d{d}_k{k}"
                chunks[cid] = SimpleNamespace(id=cid, doc_id=f"d{d}", page=k + 1, text=text)
                for n in named + [n for n in range(len(labels)) if rng.random() < 0.1]:  # sometimes mis-attributed
                    node_chunks[n].append(cid)
                    node_docs[n].add(f"d{d}")
        for n, label in enumerate(labels):
            graph.upsert_node(Node(key(n), label, doc_ids=tuple(sorted(node_docs[n])), chunk_ids=tuple(node_chunks[n])))
        for n in range(len(labels) - 1):
            graph.upsert_edge(Edge(key(n), key(n + 1), "related", next(iter(chunks)), "d0"))
        docs: Any = SimpleNamespace(
            get_chunks=lambda ids, c=chunks: {i: c[i] for i in ids if i in c},
            get_document=lambda d: SimpleNamespace(id=d, title=f"Paper {d}", status="ready"),
        )
        none: Any = None
        ctx = TurnContext(docs, none, none, TokenBudget(), "blk", graph=graph)
        seeds = rng.sample(labels, rng.randint(1, 4))
        result = await align_documents(seeds, ctx)
        produced += bool(result.cells)

        assert len(result.documents) <= max_docs and len(result.dimensions) <= max_dims
        shown_docs = {d["doc_id"] for d in result.documents}
        by_dim: dict[str, set[str]] = {}
        for cell in result.cells:
            chunk = chunks[cell["chunk_id"]]
            label = next(d["label"] for d in result.dimensions if d["id"] == cell["dimension_id"])
            assert chunk.doc_id == cell["doc_id"] in shown_docs
            assert cell["quote"] in normalise(chunk.text) and label_in_quote(cell["quote"], label)
            by_dim.setdefault(cell["dimension_id"], set()).add(cell["doc_id"])
        assert {d["id"] for d in result.dimensions} == set(by_dim)
        assert all(len(docs_) >= 2 for docs_ in by_dim.values())  # every entity shown is evidenced twice
        assert shown_docs == {c["doc_id"] for c in result.cells}  # every paper shown has a cell
        assert len(result.documents) in (0, *range(2, max_docs + 1))
    assert produced >= 8  # the property was exercised on real alignments, not only on empty ones


async def test_a_hub_entity_does_not_lose_papers_ingested_after_hundreds_of_other_chunks(tmp_path: Path):
    chunks: dict[str, Any] = {}
    for k in range(450):  # paper d1 mentions the hub in ingestion order first, but only in passing filler
        chunks[f"f{k}"] = SimpleNamespace(
            id=f"f{k}", doc_id="d1", page=1, text=f"Filler passage number {k} says little."
        )
    chunks["h1"] = SimpleNamespace(
        id="h1", doc_id="d1", page=9, text="Paper one finally discusses retrieval pipelines."
    )
    chunks["h2"] = SimpleNamespace(
        id="h2", doc_id="d2", page=2, text="Paper two builds on retrieval pipelines directly."
    )
    chunks["h3"] = SimpleNamespace(
        id="h3", doc_id="d3", page=3, text="Paper three also evaluates retrieval pipelines here."
    )
    chunks["s2"] = SimpleNamespace(id="s2", doc_id="d2", page=4, text="Paper two reports sparse indexes as a baseline.")
    chunks["s3"] = SimpleNamespace(id="s3", doc_id="d3", page=5, text="Paper three reports sparse indexes as well.")
    graph = NetworkXGraphStore(tmp_path / "hub.json")
    graph.upsert_node(
        Node(
            "retrieval_pipelines",
            "retrieval pipelines",
            doc_ids=("d1", "d2", "d3"),
            chunk_ids=(*[f"f{k}" for k in range(450)], "h1", "h2", "h3"),
        )
    )
    graph.upsert_node(Node("sparse_indexes", "sparse indexes", doc_ids=("d2", "d3"), chunk_ids=("s2", "s3")))
    graph.upsert_edge(Edge("retrieval_pipelines", "sparse_indexes", "uses", "s2", "d2"))
    docs: Any = SimpleNamespace(
        get_chunks=lambda ids: {i: chunks[i] for i in ids if i in chunks},
        get_document=lambda d: SimpleNamespace(id=d, title=f"Paper {d}", status="ready"),
    )
    none: Any = None
    ctx = TurnContext(docs, none, none, TokenBudget(), "blk", graph=graph)
    result = await align_documents(["retrieval pipelines", "sparse indexes"], ctx)
    hub_docs = {c["doc_id"] for c in result.cells if c["dimension_id"] == "retrieval_pipelines"}
    assert hub_docs == {"d1", "d2", "d3"}  # d2 and d3 sit beyond a 200-chunk window and are still found
