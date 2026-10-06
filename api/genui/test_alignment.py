"""settle(): the documents and entities that may be compared together, whatever the evidence looks like."""

import random

from api.genui.alignment import settle


def test_a_full_grid_is_kept_as_given():
    present = {(d, e) for d in ("d1", "d2") for e in ("a", "b")}
    assert settle(["d1", "d2"], ["a", "b"], present, max_docs=6, max_dims=8) == (["d1", "d2"], ["a", "b"])


def test_an_entity_in_one_document_only_is_dropped_and_can_strand_a_document():
    present = {("d1", "a"), ("d2", "a"), ("d3", "c")}  # c is only in d3, so d3 has nothing left to compare
    assert settle(["d1", "d2", "d3"], ["a", "c"], present, max_docs=6, max_dims=8) == (["d1", "d2"], ["a"])


def test_caps_keep_the_first_in_the_order_given():
    present = {(d, e) for d in "wxyz" for e in "abcd"}
    assert settle(list("wxyz"), list("abcd"), present, max_docs=3, max_dims=2) == (["w", "x", "y"], ["a", "b"])


def test_duplicates_in_the_order_lists_are_ignored():
    present = {("d1", "a"), ("d2", "a")}
    assert settle(["d1", "d1", "d2"], ["a", "a"], present, max_docs=6, max_dims=8) == (["d1", "d2"], ["a"])


def test_whatever_the_evidence_the_result_obeys_the_rules():
    rng = random.Random(7)
    docs, dims = [f"d{i}" for i in range(9)], [f"e{i}" for i in range(12)]
    for _ in range(300):
        present = {(d, e) for d in docs for e in dims if rng.random() < rng.choice([0.1, 0.3, 0.6])}
        kept_docs, kept_dims = settle(docs, dims, present, max_docs=6, max_dims=8)
        assert len(kept_docs) <= 6 and len(kept_dims) <= 8
        assert kept_docs == [d for d in docs if d in kept_docs]  # order preserved
        for e in kept_dims:
            assert sum((d, e) in present for d in kept_docs) >= 2
        for d in kept_docs:
            assert any((d, e) in present for e in kept_dims)
        assert (kept_docs == [] and kept_dims == []) or (len(kept_docs) >= 2 and len(kept_dims) >= 1)
