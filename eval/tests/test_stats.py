"""The Wilcoxon signed-rank test, checked against brute-force enumeration of every sign assignment."""

import json
import random
from collections.abc import Sequence
from itertools import product
from pathlib import Path

import pytest

from eval.stats import analyse, compare, holm, main, paired_differences, wilcoxon_signed_rank

# Darwin's maize data as used in Wilcoxon (1945): 15 paired differences. W- = 24, W+ = 96.
DARWIN = [49, -67, 8, 16, 6, 23, 28, 41, 14, 29, 56, 24, 75, 60, -48]


def brute_force_p(diffs: Sequence[float]) -> float:
    """Two-sided exact p by enumerating all 2^n sign assignments over the same (tie-adjusted) ranks."""
    from eval.stats import _average_ranks

    nz = [d for d in diffs if d != 0]
    ranks = _average_ranks([abs(d) for d in nz])
    w_plus = sum(r for d, r in zip(nz, ranks, strict=True) if d > 0)
    lower = upper = 0
    for signs in product((0, 1), repeat=len(nz)):
        w = sum(r for s, r in zip(signs, ranks, strict=True) if s)
        lower += w <= w_plus + 1e-9
        upper += w >= w_plus - 1e-9
    total = 2 ** len(nz)
    return min(1.0, 2 * min(lower, upper) / total)


def test_the_textbook_example_has_the_known_rank_sums_and_the_enumerated_p():
    r = wilcoxon_signed_rank(DARWIN)
    assert (r.n, r.n_zero, r.w_plus, r.w_minus, r.statistic) == (15, 0, 96, 24, 24)
    assert r.p_value == pytest.approx(brute_force_p(DARWIN))
    assert r.p_value == pytest.approx(0.0413, abs=5e-4)  # the value published for this data
    assert r.effect_size_rb == pytest.approx((96 - 24) / 120)


@pytest.mark.parametrize("seed", range(12))
def test_the_exact_p_matches_enumeration_on_random_data_with_ties_and_zeros(seed: int):
    rng = random.Random(seed)
    diffs = [rng.choice([-3, -2, -1, -0.5, 0, 0, 0.5, 1, 1, 2, 3, 4]) for _ in range(rng.randint(3, 14))]
    r = wilcoxon_signed_rank(diffs)
    if r.n == 0:
        assert r.p_value is None
    else:
        assert r.p_value == pytest.approx(brute_force_p(diffs))
        assert r.p_value is not None and 0 < r.p_value <= 1


def test_every_difference_in_one_direction_gives_the_smallest_possible_p():
    r = wilcoxon_signed_rank([0.1 * i for i in range(1, 11)])
    assert r.n == 10 and r.w_minus == 0 and r.p_value == pytest.approx(2 / 2**10)
    assert r.effect_size_rb == 1.0
    assert wilcoxon_signed_rank([-0.1 * i for i in range(1, 11)]).effect_size_rb == -1.0


def test_a_perfectly_balanced_set_is_not_significant():
    r = wilcoxon_signed_rank([1, -1, 2, -2, 3, -3])
    assert r.p_value == 1.0 and r.effect_size_rb == 0.0


def test_zero_differences_are_dropped_and_counted_and_all_zero_has_no_p_value():
    r = wilcoxon_signed_rank([0, 0, 0.5, 0, -0.25])
    assert (r.n, r.n_zero) == (2, 3)
    nothing = wilcoxon_signed_rank([0.0, 0.0, 0.0])
    assert nothing.n == 0 and nothing.p_value is None and nothing.effect_size_rb is None


def test_tied_magnitudes_share_an_average_rank():
    r = wilcoxon_signed_rank([1, 1, -1, 2])  # |d| ranks: 1,1,1 -> 2 each; 2 -> 4
    assert (r.w_plus, r.w_minus) == (8.0, 2.0)


def test_holm_adjustment_by_hand():
    # p = 0.01, 0.04, 0.03 -> sorted 0.01(x3), 0.03(x2), 0.04(x1) = 0.03, 0.06, 0.04 -> monotone 0.03, 0.06, 0.06
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5]) == [0.5]
    assert holm([0.4, 0.6]) == pytest.approx([0.8, 0.8])


# ── pairing questions from a runner result ────────────────────────────────────


def arm(recall: float | None, *, invalid: bool = False, ndcg: float | None = None) -> dict:
    return {"invalid": invalid, "recall_at_10": recall, "ndcg_at_10": ndcg if ndcg is not None else recall}


def question(qid: str, **arms: dict) -> dict:
    return {"question_id": qid, "arms": arms}


def test_a_question_with_an_invalid_arm_or_no_gold_is_left_out_not_scored_zero():
    results = [
        question("q1", a=arm(0.5), b=arm(0.25)),
        question("q2", a=arm(0.5, invalid=True), b=arm(0.25)),  # an invalid run is not a zero
        question("q3", a=arm(None), b=arm(None)),  # no gold passages: undefined metric
        question("q4", a=arm(0.75), b=arm(0.75)),
    ]
    ids, diffs = paired_differences(results, "recall_at_10", "a", "b")
    assert ids == ["q1", "q4"] and diffs == [0.25, 0.0]
    row = compare(results, "recall_at_10", "a", "b")
    assert (row["questions_paired"], row["wins_a"], row["wins_b"], row["ties"], row["n"], row["n_zero"]) == (2, 1, 0, 1, 1, 1)


def results_for(arms: list[str], n: int = 12) -> list[dict]:
    rng = random.Random(7)
    return [question(f"q{i}", **{a: arm(round(rng.random(), 2)) for a in arms}) for i in range(n)]


def test_analyse_reports_hybrid_vs_flat_as_the_pre_registered_primary_and_corrects_the_rest():
    arms = ["dense", "sparse", "graph", "flat", "hybrid"]
    out = analyse(results_for(arms), arms)
    primary = out["primary_comparison"]
    assert primary["pre_registered"] and [(t["a"], t["b"], t["metric"]) for t in primary["tests"]] == [
        ("hybrid", "flat", "recall_at_10"),
        ("hybrid", "flat", "ndcg_at_10"),
    ]
    secondary = out["secondary_comparisons"]["tests"]
    assert len(secondary) == 2 * 9  # the other nine pairs of five arms, for two metrics
    assert all("p_value_holm" in t and t["p_value_holm"] >= t["p_value"] for t in secondary)
    assert not any({t["a"], t["b"]} == {"hybrid", "flat"} for t in secondary)


def test_without_both_primary_arms_there_is_no_primary_test():
    assert analyse(results_for(["dense", "sparse"]), ["dense", "sparse"])["primary_comparison"]["tests"] == []


def test_the_cli_writes_statistics_beside_the_results_and_carries_the_protocol(tmp_path: Path, capsys):
    arms = ["dense", "flat", "hybrid"]
    run = {"mode": "fake", "warning": "FAKE MODE", "protocol": {"version": "p0-2"}, "relevance_rule": {"k": 10}, "hashes": {"x": "y"}, "arms": arms}
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"run": run, "results": results_for(arms)}), encoding="utf-8")
    assert main([str(path)]) == 0
    out = json.loads((tmp_path / "r-stats.json").read_text(encoding="utf-8"))
    assert out["protocol"] == {"version": "p0-2"} and out["warning"] == "FAKE MODE" and out["hashes"] == {"x": "y"}
    assert "hybrid vs flat recall_at_10" in capsys.readouterr().out
