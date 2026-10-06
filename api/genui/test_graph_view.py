"""GraphView: every tampered field is rejected with its path, and a grounded graph passes."""

import copy

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import graph_view
from api.genui.catalog import cap, graph_edges
from api.genui.evidence import excerpt_containing
from api.genui.generated import GraphView
from api.genui.validate import validate_block


@pytest.fixture
def base(ingested):
    """(docs, a ready GraphView dict with one edge whose stored quote names both ends)."""
    deps, _ = ingested
    for chunk in deps.docs.all_chunks():
        quote = excerpt_containing(chunk.text, ["Dense Retrieval", "BM25"])
        if quote:
            document = deps.docs.get_document(chunk.doc_id)
            assert document is not None
            data = {
                "nodes": [{"id": "dense", "label": "Dense Retrieval"}, {"id": "bm25", "label": "BM25"}],
                "edges": [{"source": "dense", "target": "bm25", "relation": "related to", "citationId": "c1"}],
                "citations": [
                    {
                        "id": "c1",
                        "chunkId": chunk.id,
                        "docId": chunk.doc_id,
                        "docTitle": document.title,
                        "page": chunk.page,
                        "quote": quote,
                    }
                ],
            }
            return deps.docs, graph_view("g", "ready", data=data)
    raise AssertionError("the fixture has no chunk naming both Dense Retrieval and BM25")


def fails(raw, docs) -> list[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs)
    return [i.path for i in exc.value.issues]


def test_a_grounded_graph_passes(base):
    docs, raw = base
    block = validate_block(raw, docs)
    assert isinstance(block, GraphView) and len(block.data.edges) == 1


def test_an_edge_to_a_node_that_is_not_listed_is_rejected(base):
    docs, raw = base
    raw["data"]["edges"][0]["target"] = "ghost"
    assert "data.edges.0.target" in fails(raw, docs)


def test_an_edge_whose_chunk_does_not_exist_is_rejected(base):
    docs, raw = base
    raw["data"]["citations"][0]["chunkId"] = "no-such-chunk"
    assert fails(raw, docs) == ["data.citations.0.chunkId"]


def test_a_quote_that_is_not_a_verbatim_span_is_rejected(base):
    docs, raw = base
    raw["data"]["citations"][0]["quote"] = "Dense Retrieval and BM25 are both mentioned here, but not by the paper."
    assert "data.citations.0.quote" in fails(raw, docs)


def test_a_quote_that_lacks_an_endpoint_label_is_rejected(base):
    docs, raw = base
    raw["data"]["nodes"][1]["label"] = "Louvain communities"  # the verbatim quote never says this
    assert fails(raw, docs) == ["data.edges.0.citationId"]


def test_an_orphan_node_is_rejected(base):
    docs, raw = base
    raw["data"]["nodes"].append({"id": "lonely", "label": "Dense Retrieval"})
    assert fails(raw, docs) == ["data.nodes.2"]


def test_an_orphan_citation_is_rejected(base):
    docs, raw = base
    raw["data"]["citations"].append(copy.deepcopy(raw["data"]["citations"][0]) | {"id": "c2"})
    assert fails(raw, docs) == ["data.citations.1"]


def test_an_edge_citing_nothing_in_the_block_is_rejected(base):
    docs, raw = base
    raw["data"]["edges"][0]["citationId"] = "c9"
    assert "data.edges.0.citationId" in fails(raw, docs)


def test_a_duplicate_node_id_and_a_self_loop_are_rejected(base):
    docs, raw = base
    raw["data"]["nodes"][1]["id"] = "dense"
    paths = fails(raw, docs)
    assert "data.nodes.1.id" in paths and "data.edges.0.target" in paths


def test_more_nodes_than_the_cap_is_rejected(base):
    docs, raw = base
    for i in range(cap("GraphView", "nodes") - 1):  # 2 + 29 = 31 nodes
        raw["data"]["nodes"].append({"id": f"n{i}", "label": "BM25"})
    paths = fails(raw, docs)
    assert "data.nodes" in paths


def test_more_edges_than_the_cap_is_rejected(base):
    docs, raw = base
    raw["data"]["edges"] = raw["data"]["edges"] * (cap("GraphView", "edges") + 1)
    assert "data.edges" in fails(raw, docs)


def test_a_ready_block_needs_an_edge_and_placeholders_carry_nothing(base):
    docs, raw = base
    assert fails(graph_view("g", "ready"), docs) == ["data.edges"]
    assert validate_block(graph_view("g", "loading"), docs).meta.status == "loading"
    assert fails(graph_view("g", "empty", data=raw["data"]), docs) == ["data"]


# ── what the Composer may draw: a pure function of the Graph agent's payload ──


def edge(src="a", dst="b", quote: str | None = "A verbatim quote naming Alpha and Beta.", **over):
    return {
        "src": src,
        "dst": dst,
        "relation": "uses",
        "chunk_id": "k1",
        "doc_id": "d1",
        "quote": quote,
        "page": 1,
        "doc_title": "Paper",
    } | over


def payload(*edges, labels=None):
    return {"edges": list(edges), "labels": labels or {"a": "Alpha", "b": "Beta", "c": "Gamma"}}


def test_only_edges_with_a_quote_and_two_different_labelled_ends_are_drawn():
    drawn = graph_edges(
        payload(
            edge(),
            edge(quote=None),  # the chunk never names both ends
            edge(src="a", dst="a"),  # a self-loop
            edge(src="a", dst="zz"),  # an end with no label
            edge(relation="  "),
            edge(doc_title=None),
        )
    )
    assert len(drawn) == 1 and drawn[0]["relation"] == "uses"


def test_a_relation_is_shown_in_words_not_with_underscores():
    assert graph_edges(payload(edge(relation="is_a_kind_of")))[0]["relation"] == "is a kind of"


def test_the_node_cap_stops_a_big_graph_without_leaving_a_half_edge():
    labels = {f"n{i}": f"N{i}" for i in range(80)}
    edges = [
        edge(src=f"n{2 * i}", dst=f"n{2 * i + 1}", quote=f"N{2 * i} relates to N{2 * i + 1} in this sentence.")
        for i in range(40)
    ]  # 80 distinct ends, 40 edges
    drawn = graph_edges(payload(*edges, labels=labels))
    assert len(drawn) == cap("GraphView", "nodes") // 2  # 15 edges use exactly the 30 nodes allowed


def test_nothing_is_drawn_without_a_payload():
    assert graph_edges(None) == [] and graph_edges({}) == []


def test_an_edge_whose_quote_does_not_hold_both_labels_or_is_too_short_is_not_drawn():
    labels = {"a": "Alpha", "b": "Beta"}
    assert graph_edges(payload(edge(quote="Only Alpha is named in this long enough sentence."), labels=labels)) == []
    assert graph_edges(payload(edge(quote="Alpha Beta"), labels=labels)) == []  # under the minimum quote length
    ok = edge(quote="Alpha is compared with Beta in this sentence.")
    assert len(graph_edges(payload(ok, labels=labels))) == 1


def test_a_one_character_label_is_refused_by_the_check_and_the_validator(base):
    assert (
        graph_edges(payload(edge(quote="A is related to B in this long enough sentence."), labels={"a": "A", "b": "B"}))
        == []
    )
    docs, raw = base
    raw["data"]["nodes"][1]["label"] = "B"
    assert "data.nodes.1.label" in fails(raw, docs)
