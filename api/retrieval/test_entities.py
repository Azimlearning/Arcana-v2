import pytest

from api.retrieval.entities import APPROX_WEIGHT, EXACT_WEIGHT, MAX_APPROX, resolve_query_entities
from api.stores.graph_store import Node


def node(id_: str, *docs: str) -> Node:
    return Node(id=id_, label=id_.replace("_", " "), doc_ids=docs or ("d1",))


NODES = [
    node("dense_retrieval", "d1", "d2"),
    node("bm25", "d1"),
    node("knowledge_graph", "d1", "d2"),
    node("reciprocal_rank_fusion"),
    node("graph_retrieval"),
    node("entity_resolution"),
]


def by_id(report):
    return {e.node_id: e for e in report.entities}


def test_exact_multiword_and_acronym_matches():
    report = resolve_query_entities("How does Dense Retrieval compare with BM25?", NODES)
    found = by_id(report)
    assert set(found) == {"dense_retrieval", "bm25"}
    assert all(e.match == "exact" and e.weight == EXACT_WEIGHT for e in found.values())
    assert report.content_tokens == 3 and report.covered_tokens == 3 and report.hit_rate == 1.0


def test_plural_and_camel_case_fold_to_the_same_node():
    assert set(by_id(resolve_query_entities("what are knowledge graphs", NODES))) == {"knowledge_graph"}
    assert set(by_id(resolve_query_entities("GraphRetrieval", NODES))) == {"graph_retrieval"}
    assert set(by_id(resolve_query_entities("graph retrieval", NODES))) == {"graph_retrieval"}


def test_longest_match_wins_and_spans_do_not_overlap():
    nodes = [node("dense_retrieval"), node("retrieval"), node("dense")]
    report = resolve_query_entities("dense retrieval", nodes)
    assert [e.node_id for e in report.entities] == ["dense_retrieval"]


def test_approximate_match_ranks_best_first_and_weighs_less():
    nodes = [node("dense_retrieval"), node("graph_retrieval"), node("vector_store"), node("vector_index")]
    report = resolve_query_entities("dense vector retrieval", nodes)
    first = report.entities[0]
    assert first.node_id == "dense_retrieval" and first.match == "approximate"  # shares 2 of 2 tokens
    assert all(e.weight == APPROX_WEIGHT < EXACT_WEIGHT for e in report.entities)


def test_one_query_word_is_claimed_by_at_most_one_approximate_node():
    # graph_retrieval would match only "retrieval", which dense_retrieval already accounts for; and of
    # vector_index / vector_store only one may claim "vector". Without this, one word counts several times.
    nodes = [node("dense_retrieval"), node("graph_retrieval"), node("vector_store"), node("vector_index")]
    report = resolve_query_entities("dense vector retrieval", nodes)
    assert [e.node_id for e in report.entities] == ["dense_retrieval", "vector_index"]


def test_approximate_matches_are_capped_at_three():
    nodes = [node(f"{w}_thing") for w in ("alpha", "beta", "gamma", "delta", "epsilon")]
    report = resolve_query_entities("alpha beta gamma delta epsilon", nodes)
    assert len(report.entities) == MAX_APPROX == 3
    # Equal containment and overlap everywhere, so id order picks the three: alpha, beta, delta.
    assert [e.node_id for e in report.entities] == ["alpha_thing", "beta_thing", "delta_thing"]


def test_lowercase_acronym_finds_a_camel_case_node():
    nodes = [node("graph_rag"), node("bm25")]
    for query in ("graphrag", "GraphRAG", "graph rag", "what is graph-rag"):
        report = resolve_query_entities(query, nodes)
        assert [e.node_id for e in report.entities] == ["graph_rag"], query
        assert report.entities[0].match == "exact", query


def test_exact_coverage_is_reported_apart_from_approximate():
    report = resolve_query_entities("bm25 vector", [node("bm25"), node("vector_store")])
    assert report.n_exact == 1 and report.n_approx == 1
    assert report.hit_rate == 1.0 and report.exact_hit_rate == pytest.approx(0.5)


def test_approximate_requires_half_of_a_nodes_tokens():
    nodes = [node("retrieval_augmented_generation")]  # one of three tokens shared: below half
    assert resolve_query_entities("retrieval", nodes).entities == ()


def test_approximate_only_considers_words_exact_matching_left_over():
    nodes = [node("bm25"), node("sparse_bm25_variant")]
    report = resolve_query_entities("bm25", nodes)
    assert [e.node_id for e in report.entities] == ["bm25"]  # no approximate pass for a covered word


def test_no_match_reports_a_zero_hit_rate_rather_than_failing():
    report = resolve_query_entities("zebra giraffe lion", NODES)
    assert report.entities == () and report.hit_rate == 0.0 and not report.any_resolved
    assert report.content_tokens == 3


@pytest.mark.parametrize("query", ["", "   ", "?!", "what is the of"])
def test_degenerate_queries_have_no_content_and_no_error(query: str):
    report = resolve_query_entities(query, NODES)
    assert report.content_tokens == 0 and report.hit_rate == 0.0 and report.entities == ()


def test_partial_coverage_is_reported_honestly():
    report = resolve_query_entities("BM25 outperforms zebra", NODES)
    assert report.content_tokens == 3 and report.covered_tokens == 1
    assert report.hit_rate == pytest.approx(1 / 3)


def test_empty_graph():
    assert resolve_query_entities("dense retrieval", []).entities == ()
