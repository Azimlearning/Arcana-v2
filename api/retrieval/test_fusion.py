import pytest

from api.retrieval.fusion import reciprocal_rank_fusion
from api.retrieval.types import RetrievedChunk, Signal


def rc(id_: str, *sources: Signal, text: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(id_, "doc", text or f"text {id_}", 1, 0.5, sources or ("dense",))


def test_rrf_matches_a_hand_computed_example():
    # k = 60.   A = [a, b, c]   B = [b, c, d]
    #   a: 1/61            = 0.016393
    #   b: 1/62 + 1/61     = 0.032522
    #   c: 1/63 + 1/62     = 0.032002
    #   d: 1/63            = 0.015873
    fused = reciprocal_rank_fusion(
        [[rc("a"), rc("b"), rc("c")], [rc("b", "sparse"), rc("c", "sparse"), rc("d", "sparse")]], k=60
    )
    assert [c.id for c in fused] == ["b", "c", "a", "d"]
    expected = {"a": 1 / 61, "b": 1 / 62 + 1 / 61, "c": 1 / 63 + 1 / 62, "d": 1 / 63}
    for chunk in fused:
        assert chunk.score == pytest.approx(expected[chunk.id])


def test_default_k_is_sixty():
    (only,) = reciprocal_rank_fusion([[rc("a")]])
    assert only.score == pytest.approx(1 / 61)


def test_agreement_across_lists_outweighs_a_single_top_rank():
    # rank 1 in one list: 1/61 = 0.0164.  rank 10 in two lists: 2/70 = 0.0286.
    nine = [rc(f"x{i}") for i in range(9)]
    first_in_one = [rc("solo")] + [rc(f"y{i}") for i in range(9)]
    fused = reciprocal_rank_fusion([first_in_one, [*nine, rc("agreed")], [*nine, rc("agreed")]])
    scores = {c.id: c.score for c in fused}
    assert scores["solo"] == pytest.approx(1 / 61)
    assert scores["agreed"] == pytest.approx(2 / 70)
    assert scores["agreed"] > scores["solo"]


def test_contributing_signals_are_unioned_in_order():
    fused = reciprocal_rank_fusion(
        [[rc("a", "dense")], [rc("a", "sparse")], [rc("a", "graph"), rc("b", "graph")]]
    )
    by_id = {c.id: c for c in fused}
    assert by_id["a"].sources == ("dense", "sparse", "graph")
    assert by_id["b"].sources == ("graph",)


def test_ties_break_by_best_rank_then_id():
    # Identical scores and identical best ranks: chunk id decides.
    fused = reciprocal_rank_fusion([[rc("q")], [rc("p")]])
    assert [c.id for c in fused] == ["p", "q"]

    # Identical scores, different best ranks. With k = 1, rank 1 in one list scores 1/2, and rank 3
    # in two lists scores 1/4 + 1/4 = 1/2. The chunk with the better best rank comes first.
    pad = [rc("f1"), rc("f2")]
    fused = reciprocal_rank_fusion([[rc("single")], [*pad, rc("both")], [*pad, rc("both")]], k=1)
    scores = {c.id: c.score for c in fused}
    assert scores["single"] == pytest.approx(scores["both"])
    ids = [c.id for c in fused]
    assert ids.index("single") < ids.index("both")


def test_duplicates_are_removed_and_first_seen_text_is_kept():
    fused = reciprocal_rank_fusion([[rc("a", text="first")], [rc("a", text="second")]])
    assert len(fused) == 1 and fused[0].text == "first"


def test_empty_inputs():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_ranking_keeps_its_order():
    fused = reciprocal_rank_fusion([[rc("c"), rc("a"), rc("b")]])
    assert [c.id for c in fused] == ["c", "a", "b"]


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[rc("a")]], k=0)
