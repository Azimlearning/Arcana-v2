"""Engines (P3-lite, D-37): the fallback rule by hand, and the cross-encoder where the runtime and weights are present.

The rule: a re-ranker may only re-order its candidates; absent, unavailable, failing, or returning the wrong number of scores or a non-finite
score, the heuristic's order stands and the reason is recorded; ties keep the heuristic's order.
"""

from typing import Any

import pytest

from api.engines.base import RerankEngine, apply_rerank
from api.engines.rerank import CrossEncoderRerankEngine
from api.retrieval.types import RetrievedChunk


def chunk(cid: str, text: str = "") -> RetrievedChunk:
    return RetrievedChunk(cid, "d", text or f"text of {cid}", 1, 1.0, ("dense",))


CANDIDATES = [chunk("a"), chunk("b"), chunk("c"), chunk("d")]


class Fixed(RerankEngine):
    name = "fixed"

    def __init__(
        self, scores: list[float] | None = None, available: bool = True, raises: bool = False
    ):
        self.scores, self.available, self.raises, self.seen = scores, available, raises, None

    def is_available(self) -> bool:
        return self.available

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.seen = payload
        if self.raises:
            raise ValueError("boom")
        return {"scores": self.scores if self.scores is not None else [0.0] * len(payload["texts"])}


def ids(outcome) -> list[str]:
    return [c.id for c in outcome.chunks]


def test_the_engines_scores_re_order_the_candidates_highest_first():
    engine = Fixed([0.1, 0.9, 0.5, 0.7])
    out = apply_rerank(engine, "q", CANDIDATES)
    assert out.used and out.reason is None
    assert ids(out) == ["b", "d", "c", "a"] and out.scores == (0.9, 0.7, 0.5, 0.1)
    assert engine.seen == {
        "query": "q",
        "texts": ["text of a", "text of b", "text of c", "text of d"],
    }


def test_equal_scores_keep_the_heuristics_order():
    assert ids(apply_rerank(Fixed([0.5, 0.9, 0.5, 0.9]), "q", CANDIDATES)) == ["b", "d", "a", "c"]


def test_the_output_is_always_a_permutation_of_the_input():
    out = apply_rerank(Fixed([3.0, 1.0, 4.0, 1.5]), "q", CANDIDATES)
    assert sorted(ids(out)) == ["a", "b", "c", "d"] and len(out.chunks) == 4


@pytest.mark.parametrize(
    ("engine", "reason"),
    [
        (None, "no engine"),
        (Fixed(available=False), "engine unavailable"),
        (Fixed(raises=True), "engine failed: ValueError"),
        (Fixed([0.1, 0.2]), "engine returned the wrong number of scores"),
        (
            Fixed([0.1, float("nan"), 0.3, 0.4]),
            "engine returned a score that is not a finite number",
        ),
        (
            Fixed([0.1, float("inf"), 0.3, 0.4]),
            "engine returned a score that is not a finite number",
        ),
    ],
)
def test_anything_but_a_clean_answer_leaves_the_heuristics_order(engine, reason):
    out = apply_rerank(engine, "q", CANDIDATES)
    assert not out.used and out.reason == reason
    assert ids(out) == ["a", "b", "c", "d"]


def test_fewer_than_two_candidates_is_not_sent_to_the_engine():
    engine = Fixed([1.0])
    assert apply_rerank(engine, "q", [chunk("a")]).reason == "fewer than two candidates"
    assert engine.seen is None
    assert apply_rerank(engine, "q", []).chunks == []


def test_the_cross_encoder_engine_without_its_runtime_or_weights_is_unavailable_not_an_error(
    monkeypatch,
):
    engine = CrossEncoderRerankEngine(
        model_name="no/such-model", cache_dir="/nonexistent-cache-dir-for-test"
    )
    monkeypatch.setattr("builtins.__import__", _import_without_fastembed(__import__))
    assert engine.is_available() is False
    out = apply_rerank(engine, "q", CANDIDATES)
    assert not out.used and ids(out) == ["a", "b", "c", "d"] and out.reason == "engine unavailable"


def _import_without_fastembed(real):
    def fake(name, *args, **kwargs):
        if name.startswith("fastembed"):
            raise ImportError("fastembed is not installed")
        return real(name, *args, **kwargs)

    return fake


def _model_is_cached() -> bool:
    try:
        engine = CrossEncoderRerankEngine()
        return engine.is_available()
    except Exception:
        return False


@pytest.mark.skipif(
    not _model_is_cached(),
    reason="the `engines` extra or the cross-encoder weights are not present",
)
def test_the_real_cross_encoder_ranks_a_relevant_passage_above_an_unrelated_one():
    engine = CrossEncoderRerankEngine()
    query = "What does reciprocal rank fusion do?"
    relevant = chunk(
        "rel",
        "Reciprocal rank fusion combines several ranked lists into one by summing 1 over k plus rank for each list.",
    )
    unrelated = chunk(
        "irr",
        "The mitochondria is the organelle that produces most of the chemical energy in a cell.",
    )
    out = apply_rerank(engine, query, [unrelated, relevant])
    assert out.used and ids(out) == ["rel", "irr"]
    again = apply_rerank(engine, query, [unrelated, relevant])
    assert again.scores == out.scores  # deterministic
