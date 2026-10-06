"""Paired statistics for the ablation (P1 B5): the Wilcoxon signed-rank test, written by hand.

    uv run python eval/stats.py eval/results/<run>.json --out eval/results/<run>-stats.json

Why by hand: scipy is a large dependency for one test, and the exact distribution is short to write and
easy to check against brute-force enumeration (eval/tests/test_stats.py does exactly that).

The test, for paired differences d_i = a_i - b_i over questions:
  - zero differences are dropped (the Wilcoxon method); n is the number left;
  - |d| are ranked with tied values given their average rank;
  - W+ is the sum of ranks of positive differences, W- of negative ones;
  - the p-value is EXACT and two-sided: 2 x min(P(W+ <= observed), P(W+ >= observed)) under random signs,
    capped at 1, computed from the permutation distribution of the (tie-adjusted) ranks, so ties need no
    normal approximation;
  - the effect size is the matched-pairs rank-biserial correlation (W+ - W-) / (W+ + W-), from -1 to 1,
    positive when a beats b.

What it cannot do: 19 or 20 questions is a small sample, the questions are not a random draw from a
population, and arms share the same corpus and gold, so a p-value here is a statement about this question
set, not about retrieval in general. The primary comparison is pre-registered (hybrid versus flat); every
other pair is secondary and is reported with Holm-adjusted p-values and no claim of significance beyond that.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

PRIMARY = ("hybrid", "flat")
METRICS = ("recall_at_10", "ndcg_at_10")


@dataclass(frozen=True)
class WilcoxonResult:
    n: int
    """Pairs with a non-zero difference."""
    n_zero: int
    """Pairs dropped because the difference was zero."""
    w_plus: float
    w_minus: float
    statistic: float
    """min(W+, W-), the conventional reported statistic."""
    p_value: float | None
    """Exact two-sided; None when there are no non-zero differences (nothing to test)."""
    effect_size_rb: float | None
    """Rank-biserial correlation, positive when the first arm is better."""


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1  # average of positions i+1 .. j+1
        i = j + 1
    return ranks


def wilcoxon_signed_rank(differences: Sequence[float]) -> WilcoxonResult:
    nonzero = [d for d in differences if d != 0]
    n_zero = len(differences) - len(nonzero)
    if not nonzero:
        return WilcoxonResult(0, n_zero, 0.0, 0.0, 0.0, None, None)
    ranks = _average_ranks([abs(d) for d in nonzero])
    w_plus = sum(r for d, r in zip(nonzero, ranks, strict=True) if d > 0)
    w_minus = sum(r for d, r in zip(nonzero, ranks, strict=True) if d < 0)

    # Permutation distribution of W+ over all 2^n sign assignments. Ranks may be half-integers, so work in
    # doubled integer units: counts[s] = number of sign assignments whose doubled W+ equals s.
    doubled = [round(2 * r) for r in ranks]
    counts = [0] * (sum(doubled) + 1)
    counts[0] = 1
    for r in doubled:
        for s in range(len(counts) - 1, r - 1, -1):
            counts[s] += counts[s - r]
    total = 2 ** len(doubled)
    observed = round(2 * w_plus)
    lower = sum(counts[: observed + 1]) / total  # P(W+ <= observed)
    upper = sum(counts[observed:]) / total  # P(W+ >= observed)
    p = min(1.0, 2 * min(lower, upper))
    effect = (w_plus - w_minus) / (w_plus + w_minus)
    return WilcoxonResult(len(nonzero), n_zero, w_plus, w_minus, min(w_plus, w_minus), p, effect)


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def paired_differences(results: Sequence[dict[str, Any]], metric: str, a: str, b: str) -> tuple[list[str], list[float]]:
    """(question ids, a - b) for every question where BOTH arms ran validly and have a score. A question
    with no gold (metric None) or an invalid arm is left out of the pair, never counted as zero."""
    ids: list[str] = []
    diffs: list[float] = []
    for q in results:
        ra, rb = q["arms"][a], q["arms"][b]
        if ra["invalid"] or rb["invalid"] or ra[metric] is None or rb[metric] is None:
            continue
        ids.append(q["question_id"])
        diffs.append(ra[metric] - rb[metric])
    return ids, diffs


def compare(results: Sequence[dict[str, Any]], metric: str, a: str, b: str) -> dict[str, Any]:
    ids, diffs = paired_differences(results, metric, a, b)
    test = wilcoxon_signed_rank(diffs)
    mean_diff = sum(diffs) / len(diffs) if diffs else None
    ordered = sorted(diffs)
    median = None if not ordered else (ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2)
    return {
        "a": a,
        "b": b,
        "metric": metric,
        "questions_paired": len(ids),
        "mean_difference": None if mean_diff is None else round(mean_diff, 4),
        "median_difference": None if median is None else round(median, 4),
        "wins_a": sum(d > 0 for d in diffs),
        "wins_b": sum(d < 0 for d in diffs),
        "ties": sum(d == 0 for d in diffs),
        **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(test).items()},
    }


def analyse(results: Sequence[dict[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    primary = [compare(results, m, *PRIMARY) for m in METRICS] if all(a in arms for a in PRIMARY) else []
    secondary: list[dict[str, Any]] = []
    for metric in METRICS:
        family = [
            compare(results, metric, a, b)
            for a, b in combinations(arms, 2)
            if {a, b} != set(PRIMARY) and a != b
        ]
        usable = [r for r in family if r["p_value"] is not None]
        for r, adj in zip(usable, holm([r["p_value"] for r in usable]), strict=True):
            r["p_value_holm"] = round(adj, 6)
        secondary.extend(family)
    return {
        "primary_comparison": {
            "hypothesis": "hybrid retrieval differs from flat (vector plus BM25, no graph) retrieval",
            "pre_registered": True,
            "tests": primary,
        },
        "secondary_comparisons": {"correction": "Holm, within each metric", "tests": secondary},
        "method": "Wilcoxon signed-rank, exact two-sided; zero differences dropped; rank-biserial effect size",
        "caveat": (
            "A small sample (at most 19 to 20 questions) that is not a random draw; arms share the corpus and "
            "gold. A p-value describes this question set, not retrieval in general. A null result is a result."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("results", help="a results JSON written by eval/run_ablation.py")
    p.add_argument("--out", help="where to write the statistics JSON (default: beside the results)")
    args = p.parse_args(argv)
    path = Path(args.results)
    data = json.loads(path.read_text(encoding="utf-8"))
    arms = list(data["run"]["arms"]) if "arms" in data.get("run", {}) else list(data["results"][0]["arms"])
    run = data.get("run", {})
    out = {
        "results_file": path.name,
        "mode": run.get("mode"),
        "warning": run.get("warning"),  # a fake-mode run says so here too: its statistics are plumbing only
        "protocol": run.get("protocol"),
        "relevance_rule": run.get("relevance_rule"),
        "hashes": run.get("hashes"),
        **analyse(data["results"], arms),
    }
    target = Path(args.out) if args.out else path.with_name(path.stem + "-stats.json")
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    for t in out["primary_comparison"]["tests"]:
        print(
            f"  {t['a']} vs {t['b']} {t['metric']}: n={t['n']} W+={t['w_plus']} W-={t['w_minus']} "
            f"p={t['p_value']} r={t['effect_size_rb']} mean diff={t['mean_difference']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
