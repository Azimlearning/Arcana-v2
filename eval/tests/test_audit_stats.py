"""Statistics findings of the pre-benchmark retrieval audit (2026-10-06)."""

import json
import random
from pathlib import Path

from eval.stats import (
    analyse,
    compare,
    gate_warning,
    main,
    paired_differences,
    wilcoxon_signed_rank,
)


def arm(recall: float | None) -> dict:
    return {"invalid": False, "recall_at_10": recall, "ndcg_at_10": recall}


def question(qid: str, **arms: dict) -> dict:
    return {"question_id": qid, "arms": arms}


def results_for(arms: list[str], n: int = 12) -> list[dict]:
    rng = random.Random(7)
    return [question(f"q{i}", **{a: arm(round(rng.random(), 2)) for a in arms}) for i in range(n)]


def test_mathematically_equal_differences_tie_even_when_floats_differ_in_the_last_digit():
    a, b = 4 / 7 - 3 / 7, 6 / 7 - 5 / 7
    assert a != b  # the noise this test is about: equal in mathematics, different as floats
    noisy = wilcoxon_signed_rank([a, b, -(2 / 7 - 1 / 7), 3 / 7 - 1 / 7])
    clean = wilcoxon_signed_rank([1 / 7, 1 / 7, -(1 / 7), 2 / 7])
    assert (noisy.w_plus, noisy.w_minus, noisy.p_value) == (clean.w_plus, clean.w_minus, clean.p_value)
    assert (clean.w_plus, clean.w_minus) == (8.0, 2.0)  # three tied |d| share rank 2, the largest is 4


def test_paired_differences_round_the_noise_away():
    results = [question("q1", a=arm(4 / 7), b=arm(3 / 7)), question("q2", a=arm(6 / 7), b=arm(5 / 7))]
    _, diffs = paired_differences(results, "recall_at_10", "a", "b")
    assert diffs[0] == diffs[1]


def test_a_difference_of_nothing_after_rounding_is_a_tie_not_a_win():
    results = [question("q1", a=arm(0.1 + 0.2), b=arm(0.3))]  # 0.30000000000000004 versus 0.3
    row = compare(results, "recall_at_10", "a", "b")
    assert (row["wins_a"], row["wins_b"], row["ties"], row["n_zero"]) == (0, 0, 1, 1)


def test_the_two_primary_metrics_are_holm_corrected_against_each_other():
    arms = ["flat", "hybrid"]
    tests = analyse(results_for(arms, n=14), arms)["primary_comparison"]["tests"]
    usable = [t for t in tests if t["p_value"] is not None]
    assert usable and all(t["p_value_holm"] >= t["p_value"] for t in usable)


def test_a_pair_with_nothing_to_test_has_no_adjusted_p_either():
    results = [question(f"q{i}", a=arm(0.5), b=arm(0.5), c=arm(round(0.1 * i, 2))) for i in range(1, 9)]
    out = analyse(results, ["a", "b", "c"])
    tied = next(t for t in out["secondary_comparisons"]["tests"] if (t["a"], t["b"]) == ("a", "b"))
    assert tied["p_value"] is None and tied["p_value_holm"] is None


def test_the_statistics_file_carries_a_failed_gate_and_the_code_state(tmp_path: Path):
    assert gate_warning(None) is None and gate_warning({"enforced": False, "passed": False}) is None
    assert gate_warning({"enforced": True, "passed": True}) is None
    assert "do not quote" in (gate_warning({"enforced": True, "passed": False}) or "")
    arms = ["flat", "hybrid"]
    run = {"mode": {}, "arms": arms, "code": {"commit": "abc", "dirty": False}, "questions_selected": ["q1"]}
    summary = {"empty_graph_gate": {"enforced": True, "passed": False}}
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"run": run, "results": results_for(arms), "summary": summary}), encoding="utf-8")
    assert main([str(path)]) == 0
    out = json.loads((tmp_path / "r-stats.json").read_text(encoding="utf-8"))
    assert out["code"] == {"commit": "abc", "dirty": False} and "do not quote" in out["gate_warning"]
