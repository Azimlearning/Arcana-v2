"""P3-lite (D-37): does a pretrained cross-encoder re-ranker help the hybrid arm? One experiment, the protocol fixed here before any run.

    uv run python eval/rerank_compare.py --baseline eval/results/20261006T093813Z-benchmark.json --data-dir data/eval-live-live --allow-paid

PROTOCOL (written 2026-10-14, before the first run; constraint 9)
-----------------------------------------------------------------
Corpus and questions: the P1 benchmark's own (the same 16 papers, the same 19 answerable questions, the same gold). The stores' graph, vector and
chunk hashes must equal the baseline result's, or the run is refused. The candidate generator is the frozen hybrid arm (dense + sparse + graph,
RRF k = 60, scoring frozen by D-20); only the **depth** differs.

Arms, per question (nDCG@10 and Recall@10 by the harness's own `eval/metrics.py`, scored on the top ten):
    hybrid        the frozen arm, recomputed; its chunk ids must equal the baseline's (else the run is invalid)
    hybrid_nN     the same arm with N per signal and N after fusion, scored on the top ten      (N = 30, 50)  [the depth control]
    rerank_nN     the top N of `hybrid_nN` re-ordered by the engine, scored on the top ten      (N = 10, 30, 50)
The depth control matters: deeper candidate lists change the fused top ten by themselves, so a re-ranker is credited only for what it adds over
`hybrid_nN`, never over `hybrid` alone. The engine is the pretrained Xenova/ms-marco-MiniLM-L-6-v2 cross-encoder (not trained here).

Headline pairs (named now, the only ones with a verdict): (rerank_n50 vs hybrid) and (rerank_n50 vs hybrid_n50), on nDCG@10, exact two-sided
Wilcoxon signed-rank from `eval/stats.py`. Every other pair is exploratory and reported with no verdict.

DECISION RULE: the engine is reported as **helping** only if, on (rerank_n50 vs hybrid_n50), the mean nDCG@10 difference is positive and p < 0.05.
Otherwise it is reported as **not shown to help**, whatever the sign of the mean. 19 questions is a small sample and a non-significant gain is not
evidence of no effect; it is reported as exactly that. Candidate recall (the share of gold passages anywhere in the N candidates) is reported to say
what a re-ranker could at most reach.

COST: the 19 question embeddings only (cached per question), about $0.00006 in all; a ceiling of `--max-usd` (default 0.01) is checked after each
question and the run stops if it is passed. Running the cross-encoder costs nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)  # so `api` and `eval` import when run as a script

from api.container import build_container
from api.core.logging import configure_logging
from api.core.settings import load_settings
from api.engines.base import apply_rerank
from api.engines.rerank import DEFAULT_MODEL, CrossEncoderRerankEngine
from api.ingestion.embed import CachingEmbedder
from api.retrieval.arms import ARMS
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever
from api.stores.preflight import check_corpus_parity
from eval import metrics, stats
from eval.run_ablation import (
    RunInvalid,
    chunks_sha256,
    load_questions,
    require_approved_gold,
    require_clean_code,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
DEPTHS = (10, 30, 50)
HEADLINE = (("rerank_n50", "hybrid"), ("rerank_n50", "hybrid_n50"))
DECISION_ALPHA = 0.05


def _entry(
    texts: list[str], gold: metrics.Gold | None, n_rel: int, ids: list[str], extra: dict[str, Any]
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "invalid": False,
        "chunk_ids": ids,
        "recall_at_10": None,
        "ndcg_at_10": None,
        **extra,
    }
    if gold is not None and gold.passages:
        row["recall_at_10"] = metrics.recall_at_k(texts, gold)
        row["ndcg_at_10"] = metrics.ndcg_at_k(texts, gold, n_rel)
    return row


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


async def run(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    base = load_settings()
    live = base.arcana_llm_mode == "live" or base.arcana_embed_mode == "live"
    if live and not args.allow_paid:
        raise RunInvalid(
            "live (paid) mode is configured; pass --allow-paid (it pays only for 19 question embeddings)"
        )
    data_dir = Path(args.data_dir)
    settings = base.model_copy(update={"arcana_data_dir": data_dir})
    configure_logging("WARNING")

    baseline_path = Path(args.baseline)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))  # noqa: ASYNC240  (a one-off tool, not a server path)
    selected = baseline["run"]["questions_selected"]
    questions = [
        q for q in load_questions(ROOT / "eval" / "questions.yaml") if q["id"] in set(selected)
    ]
    golds = {q["id"]: metrics.load_gold(ROOT / "eval" / "gold", q["id"]) for q in questions}
    require_approved_gold(golds, live)
    code = require_clean_code(live, getattr(args, "allow_dirty", False))

    container = build_container(settings)
    problems = check_corpus_parity(container.docs, container.vectors, container.graph)
    if problems:
        raise RunInvalid("corpus parity check failed: " + "; ".join(problems))
    chunks = container.docs.all_chunks()
    store_hashes = {
        "graph_sha256": sha256_file(data_dir / "graph.json"),
        "vectors_sha256": sha256_file(data_dir / "vectors.npz"),
        "chunks_sha256": chunks_sha256(chunks),
    }
    expected = {k: baseline["run"]["hashes"][k] for k in store_hashes}
    if store_hashes != expected:
        raise RunInvalid(
            f"the stores differ from the baseline result's: {store_hashes} against {expected}"
        )

    engine = CrossEncoderRerankEngine()
    if not engine.is_available():
        raise RunInvalid(
            "the cross-encoder is not available (install the `engines` extra: uv sync --extra engines)"
        )

    cached = CachingEmbedder(container.embedder)
    retrievers = {
        "dense": DenseRetriever(vectors=container.vectors, docs=container.docs, embedder=cached),
        "sparse": SparseRetriever(docs=container.docs),
        "graph": GraphRetriever(graph=container.graph, docs=container.docs),
    }
    corpus_texts = [c.text for c in chunks]
    baseline_by_q = {r["question_id"]: r for r in baseline["results"]}
    spent_before = container.ledger.month_total()
    results: list[dict[str, Any]] = []

    for q in questions:
        gold = golds[q["id"]]
        n_rel = metrics.relevant_count(corpus_texts, gold) if gold and gold.passages else 0
        question = q["question"].strip()
        arms: dict[str, dict[str, Any]] = {}
        candidate_recall: dict[str, float | None] = {}
        for depth in DEPTHS:
            fused = await hybrid_retrieve(
                question, **retrievers, signals=ARMS["hybrid"], top_k=depth
            )
            if fused.failed:
                for name in (("hybrid",) if depth == DEPTHS[0] else ()) + (
                    f"hybrid_n{depth}",
                    f"rerank_n{depth}",
                ):
                    arms[name] = {
                        "invalid": True,
                        "chunk_ids": [],
                        "recall_at_10": None,
                        "ndcg_at_10": None,
                    }
                continue
            candidates = fused.chunks
            texts = [c.text for c in candidates]
            candidate_recall[f"n{depth}"] = (
                metrics.recall_at_k(texts, gold, k=depth)
                if gold is not None and gold.passages
                else None
            )
            top10 = candidates[:10]
            if depth == DEPTHS[0]:
                frozen_ids = baseline_by_q[q["id"]]["arms"]["hybrid"]["chunk_ids"]
                ids = [c.id for c in top10]
                if ids != frozen_ids:
                    raise RunInvalid(
                        f"{q['id']}: the recomputed hybrid top ten differs from the baseline's (the candidate generator is not the frozen one)"
                    )
                arms["hybrid"] = _entry(
                    [c.text for c in top10], gold, n_rel, ids, {"matches_baseline": True}
                )
            else:
                arms[f"hybrid_n{depth}"] = _entry(
                    [c.text for c in top10], gold, n_rel, [c.id for c in top10], {}
                )
            started = time.perf_counter()
            outcome = apply_rerank(engine, question, candidates)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            if not outcome.used:
                arms[f"rerank_n{depth}"] = {
                    "invalid": True,
                    "chunk_ids": [],
                    "recall_at_10": None,
                    "ndcg_at_10": None,
                    "reason": outcome.reason,
                }
                continue
            reranked = outcome.chunks[:10]
            arms[f"rerank_n{depth}"] = _entry(
                [c.text for c in reranked],
                gold,
                n_rel,
                [c.id for c in reranked],
                {"engine_used": True, "rerank_ms": elapsed_ms},
            )
        results.append(
            {
                "question_id": q["id"],
                "category": q["category"],
                "n_gold_passages": len(gold.passages) if gold else 0,
                "relevant_chunks_in_corpus": n_rel,
                "candidate_recall": candidate_recall,
                "arms": arms,
            }
        )
        spent = container.ledger.month_total() - spent_before
        if spent > args.max_usd:
            raise RunInvalid(
                f"spend ${spent:.6f} passed the ceiling ${args.max_usd}; stopped after {q['id']}"
            )

    arm_names = ["hybrid", "hybrid_n30", "hybrid_n50", "rerank_n10", "rerank_n30", "rerank_n50"]
    per_arm = {}
    for arm in arm_names:
        rows = [
            r["arms"][arm] for r in results if arm in r["arms"] and not r["arms"][arm]["invalid"]
        ]
        per_arm[arm] = {
            "questions": len(rows),
            "mean_recall_at_10": _mean(
                [r["recall_at_10"] for r in rows if r["recall_at_10"] is not None]
            ),
            "mean_ndcg_at_10": _mean(
                [r["ndcg_at_10"] for r in rows if r["ndcg_at_10"] is not None]
            ),
        }
    pairs = []
    for a, b in (
        *HEADLINE,
        ("rerank_n30", "hybrid_n30"),
        ("rerank_n10", "hybrid"),
        ("hybrid_n50", "hybrid"),
    ):
        for metric in ("ndcg_at_10", "recall_at_10"):
            row = stats.compare(results, metric, a, b)
            row["headline"] = (a, b) in HEADLINE and metric == "ndcg_at_10"
            pairs.append(row)
    decisive = next(
        p
        for p in pairs
        if (p["a"], p["b"]) == ("rerank_n50", "hybrid_n50") and p["metric"] == "ndcg_at_10"
    )
    helped = (
        decisive["mean_difference"] is not None
        and decisive["mean_difference"] > 0
        and decisive["p_value"] is not None
        and decisive["p_value"] < DECISION_ALPHA
    )
    verdict = "helps" if helped else "not shown to help"
    candidate_summary = {
        f"n{d}": _mean(
            [
                r["candidate_recall"].get(f"n{d}")
                for r in results
                if r["candidate_recall"].get(f"n{d}") is not None
            ]
        )
        for d in DEPTHS
    }
    out = {
        "run": {
            "timestamp": datetime.now(UTC).isoformat(),
            "label": args.label,
            "protocol": (__doc__ or "").split("PROTOCOL", 1)[-1].strip(),
            "code": code,
            "python": platform.python_version(),
            "engine": {"name": engine.name, "model": DEFAULT_MODEL},
            "mode": {"llm": settings.arcana_llm_mode, "embed": settings.arcana_embed_mode},
            "baseline": str(baseline_path),
            "hashes": store_hashes,
            "questions": [q["id"] for q in questions],
            "query_embeddings_computed": cached.inner_calls,
            "spent_usd": round(container.ledger.month_total() - spent_before, 6),
            "ceiling_usd": args.max_usd,
        },
        "results": results,
        "summary": {
            "per_arm": per_arm,
            "candidate_recall_mean": candidate_summary,
            "pairs": pairs,
            "verdict": verdict,
            "decision_pair": decisive,
        },
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240  (a one-off tool, not a server path)
    path = out_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{args.label}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return path, out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument(
        "--baseline",
        required=True,
        help="the P1 benchmark result whose hashes and hybrid top tens this run must reproduce",
    )
    p.add_argument("--data-dir", required=True)
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    p.add_argument("--label", default="p3-rerank")
    p.add_argument("--max-usd", type=float, default=0.01)
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--allow-dirty", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path, out = asyncio.run(run(args))
    except RunInvalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    summary = out["summary"]
    shown = {
        "wrote": str(path),
        "spent_usd": out["run"]["spent_usd"],
        "per_arm": summary["per_arm"],
        "candidate_recall_mean": summary["candidate_recall_mean"],
        "verdict": summary["verdict"],
    }
    print(json.dumps(shown, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
