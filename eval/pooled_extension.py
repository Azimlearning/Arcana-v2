"""Pool the original 19 answerable questions with the 19 declared extension questions (D-39) and report the headline pairs H1 to H4.

    uv run python eval/pooled_extension.py

The pairs, the samples and the rule for D-38 were fixed in `refdocs/plans/2026-10-15-question-set-extension.md` before any arm was run on the
new questions. This tool only reads result files that already exist (no model, no spend). Per-question scores of the same arms, over the same
stores, gold rule and code, are concatenated; the test is the harness's exact Wilcoxon signed-rank test (`eval/stats.py`).

    H1  hybrid_n30 against frozen hybrid                     new 19 only (confirms or reverses D-38); Recall@10 is the rule's metric
    H2  frozen hybrid against flat                           pooled 38, and the new 19 alone
    H3  hybrid_vault (atomic2) against the baseline hybrid   pooled 38
    H4  vault against its own directory's frozen graph       pooled 38 (atomic2)
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import stats
from eval.run_ablation import git_state

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
OLD_COMPARE = RESULTS / "20261014T151443Z-m2-look5.json"
OLD_RERANK = RESULTS / "20261014T135007Z-p3-rerank.json"
NEW_COMPARE = RESULTS / "20261014T192526Z-m2-ext.json"
NEW_RERANK = RESULTS / "20261014T192055Z-ext-rerank.json"
ATOMIC2 = "atomic2-full-vault1"
METRICS = ("recall_at_10", "ndcg_at_10")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_scores(result: dict[str, Any], where: str, arm: str, metric: str) -> dict[str, float | None]:
    """question id -> score, for an arm of a vault_compare result (`where` is `baseline` or a variant directory name)."""
    return {q["question_id"]: q[where][arm][metric] for q in result["per_question"]}


def rerank_scores(result: dict[str, Any], arm: str, metric: str) -> dict[str, float | None]:
    return {q["question_id"]: q["arms"][arm][metric] for q in result["results"]}


def pair(a: dict[str, float | None], b: dict[str, float | None]) -> dict[str, Any]:
    ids = sorted(i for i in a if i in b and a[i] is not None and b[i] is not None)
    diffs = [a[i] - b[i] for i in ids]  # type: ignore[operator]
    w = stats.wilcoxon_signed_rank(diffs)
    return {
        "questions": len(ids),
        "mean_a": round(sum(a[i] for i in ids) / len(ids), 4),  # type: ignore[misc]
        "mean_b": round(sum(b[i] for i in ids) / len(ids), 4),  # type: ignore[misc]
        "mean_difference": round(sum(diffs) / len(ids), 4),
        "better": sum(d > 1e-12 for d in diffs),
        "tied": sum(abs(d) <= 1e-12 for d in diffs),
        "worse": sum(d < -1e-12 for d in diffs),
        "p_value": w.p_value,
        "effect_size_rb": w.effect_size_rb,
    }


def build() -> dict[str, Any]:
    old_c, old_r, new_c, new_r = _load(OLD_COMPARE), _load(OLD_RERANK), _load(NEW_COMPARE), _load(NEW_RERANK)
    out: dict[str, Any] = {"pairs": {}}
    for m in METRICS:
        out["pairs"][f"H1 hybrid_n30 vs hybrid, new 19 [{m}]"] = pair(
            rerank_scores(new_r, "hybrid_n30", m), rerank_scores(new_r, "hybrid", m)
        )
        out["pairs"][f"H1x hybrid_n30 vs hybrid, original 19 (where the depth was chosen) [{m}]"] = pair(
            rerank_scores(old_r, "hybrid_n30", m), rerank_scores(old_r, "hybrid", m)
        )
        out["pairs"][f"H1p hybrid_n30 vs hybrid, pooled 38 [{m}]"] = pair(
            {**rerank_scores(old_r, "hybrid_n30", m), **rerank_scores(new_r, "hybrid_n30", m)},
            {**rerank_scores(old_r, "hybrid", m), **rerank_scores(new_r, "hybrid", m)},
        )
        for label, parts in (("new 19", [new_c]), ("original 19", [old_c]), ("pooled 38", [old_c, new_c])):
            def merged(where: str, arm: str, parts: list[dict[str, Any]] = parts, m: str = m) -> dict[str, float | None]:
                d: dict[str, float | None] = {}
                for p in parts:
                    d.update(compare_scores(p, where, arm, m))
                return d

            out["pairs"][f"H2 hybrid vs flat, {label} [{m}]"] = pair(merged("baseline", "hybrid"), merged("baseline", "flat"))
            if label == "pooled 38":
                out["pairs"][f"H3 hybrid_vault (atomic2) vs baseline hybrid, {label} [{m}]"] = pair(
                    merged(ATOMIC2, "hybrid_vault"), merged("baseline", "hybrid")
                )
                out["pairs"][f"H4 vault vs own frozen graph (atomic2), {label} [{m}]"] = pair(
                    merged(ATOMIC2, "vault"), merged(ATOMIC2, "graph")
                )
    h1 = out["pairs"]["H1 hybrid_n30 vs hybrid, new 19 [recall_at_10]"]
    out["d38_rule"] = {
        "rule": "D-38 stands only if the mean Recall@10 difference (hybrid_n30 minus hybrid) on the 19 new questions is positive",
        "mean_recall_difference_new_19": h1["mean_difference"],
        "stands": h1["mean_difference"] > 0,
    }
    return out


def main() -> int:
    state = git_state()
    result = build()
    result["run"] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "code": state,
        "inputs": [p.name for p in (OLD_COMPARE, OLD_RERANK, NEW_COMPARE, NEW_RERANK)],
    }
    path = RESULTS / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-extension-pooled.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, p in result["pairs"].items():
        print(
            f"{name}: {p['mean_b']} -> {p['mean_a']} ({p['mean_difference']:+.4f}; "
            f"{p['better']}/{p['tied']}/{p['worse']}; p={p['p_value']})"
        )
    print("D-38 rule:", result["d38_rule"])
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
