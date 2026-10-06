"""Five-arm retrieval ablation runner (D-15, D-20).

    uv run python eval/run_ablation.py --questions q-cross-01,q-single-01 --arms all

Arms differ only in which signals are enabled (api/retrieval/arms.py). For each question and arm it
records Recall@10, nDCG@10, the RAGAS non-LLM context metrics (when RAGAS is installed), the ranking
length, latency and the graph entity-resolution report, and writes one JSON file per run.

Rules this runner enforces (from the retrieval audit):
  - corpus parity must hold before anything runs (every chunk has a vector, the graph references only
    stored chunks, every document is ready); otherwise the run is refused;
  - the query embedding is computed once per question and shared by every arm;
  - a signal that FAILED invalidates that question-arm: it is recorded as invalid with None metrics,
    never as zero recall, and the process exits non-zero;
  - a question with no gold passages gets None metrics and is left out of every aggregate;
  - the protocol stamp, relevance rule and content hashes of the corpus, stores, questions and gold
    are written into the results, so a result is always tied to what produced it;
  - live (paid) mode is refused unless --allow-paid is given.

A run in fake mode (hashed bag-of-words embeddings, a fake extractor) checks the plumbing. Its numbers
are not evidence about retrieval, and the results file says so.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

import yaml

from api.container import Container, build_container
from api.core.logging import configure_logging
from api.core.settings import Settings, load_settings
from api.ingestion.embed import CachingEmbedder
from api.ingestion.pipeline import ingest_pdf
from api.ingestion.types import doc_id_for
from api.llm.models import ANTHROPIC_MODELS
from api.retrieval.arms import ARMS
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.protocol import protocol_stamp
from api.retrieval.sparse import SparseRetriever
from api.stores.preflight import check_corpus_parity
from eval import metrics
from eval.ragas_metrics import RagasUnavailable, non_llm_context_metrics, ragas_status

ROOT = Path(__file__).resolve().parents[1]
EMPTY_GRAPH_GATE = 0.30
GATE_MIN_QUESTIONS = 10  # below this the gate is reported, not enforced (smoke runs)
FAKE_WARNING = (
    "FAKE MODE: hashed bag-of-words embeddings and a fake extractor. This run checks the plumbing; "
    "its numbers say nothing about retrieval quality and must not be reported as results."
)


def require_approved_gold(golds: dict[str, metrics.Gold | None], live: bool) -> None:
    """Constraint 9: gold is written and approved BEFORE any benchmark arm is run. A live (paid) run
    against a draft, a smoke file or a missing file is refused; a fake-mode run only checks plumbing and
    is allowed (its results say which gold it used)."""
    if not live:
        return
    unapproved = sorted(q for q, g in golds.items() if g is None or not g.approved)
    if unapproved:
        raise RunInvalid(f"gold is not approved for: {', '.join(unapproved)}")


MAX_EXTRACTION_FAILURE_RATE = 0.05


def require_extraction_quality(ingestion: list[dict[str, Any]]) -> None:
    """A graph built from mostly-failed extractions would make the graph arms look useless for a reason that
    has nothing to do with graphs. Refuse a run where more than 5 percent of the chunks ingested NOW failed
    to extract (documents reused from an earlier ingest report None and are not counted here)."""
    fresh = [d for d in ingestion if d.get("ingested_now")]
    chunks = sum(d["chunks"] for d in fresh)
    failures = sum(d["extraction_failures"] or 0 for d in fresh)
    if chunks and failures / chunks > MAX_EXTRACTION_FAILURE_RATE:
        raise RunInvalid(
            f"{failures} of {chunks} chunks failed extraction ({failures / chunks:.0%}); "
            f"the limit is {MAX_EXTRACTION_FAILURE_RATE:.0%}. The graph would not be a fair test."
        )


class RunInvalid(Exception):
    """The run must not proceed or must not be reported (exit code 2)."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_questions(path: Path) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]


def select_questions(questions: list[dict[str, Any]], ids: str | None) -> list[dict[str, Any]]:
    if not ids:
        return questions
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    by_id = {q["id"]: q for q in questions}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise RunInvalid(f"unknown question id(s): {missing}")
    return [by_id[i] for i in wanted]


def select_arms(spec: str) -> list[str]:
    arms = list(ARMS) if spec == "all" else [a.strip() for a in spec.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise RunInvalid(f"unknown arm(s): {unknown}; choose from {list(ARMS)}")
    return arms


async def ensure_corpus(
    container: Container, manifest: list[dict[str, Any]], corpus_dir: Path, reingest: bool
) -> list[dict[str, Any]]:
    """Ingest every manifest paper (or reuse what is already stored, unchanged). Returns per-document facts."""
    report: list[dict[str, Any]] = []
    for entry in manifest:
        path = corpus_dir / entry["file"]
        if not path.exists():
            raise RunInvalid(f"corpus PDF missing: {path}")
        raw = path.read_bytes()
        doc_id = doc_id_for(raw)
        stored = container.docs.get_document(doc_id)
        if stored is not None and stored.status == "ready" and not reingest:
            n_chunks = len(container.docs.chunks_for_document(doc_id))
            report.append({"arxiv_id": entry["arxiv_id"], "doc_id": doc_id, "status": "ready", "chunks": n_chunks,
                           "nodes": None, "edges": None, "extraction_failures": None, "ingested_now": False})
            continue
        result = await ingest_pdf(raw, entry["file"], container.ingest_deps)
        report.append({"arxiv_id": entry["arxiv_id"], "doc_id": result.doc_id, "status": result.status,
                       "chunks": result.chunk_count, "nodes": result.node_count, "edges": result.edge_count,
                       "extraction_failures": result.extraction_failures, "ingested_now": True,
                       "error": result.error})
        if result.status != "ready":
            break  # stop at the first failure (spend cap, provider down): later papers would only pay for embeddings first
    return report


def resolution_record(result) -> dict[str, Any] | None:
    r = result.resolution
    if r is None:
        return None
    return {
        "content_tokens": r.content_tokens, "covered_tokens": r.covered_tokens,
        "hit_rate": round(r.hit_rate, 4), "exact_hit_rate": round(r.exact_hit_rate, 4),
        "n_exact": r.n_exact, "n_approx": r.n_approx,
        "entities": [{"node_id": e.node_id, "match": e.match} for e in r.entities],
    }


async def run_arm(arm: str, question: str, retrievers: dict[str, Any], gold: metrics.Gold | None,
                  corpus_texts: list[str], n_relevant: int, ragas_ok: bool) -> dict[str, Any]:
    result = await hybrid_retrieve(question, **retrievers, signals=ARMS[arm])
    entry: dict[str, Any] = {
        "invalid": bool(result.failed), "failed_signals": list(result.failed),
        "ranking_length": len(result.chunks), "latency_ms": round(result.latency_ms, 2),
        "graph_ranking_empty": (not result.per_signal["graph"]) if "graph" in result.signals else None,
        "resolution": resolution_record(result), "chunk_ids": [c.id for c in result.chunks],
        "recall_at_10": None, "ndcg_at_10": None, "ragas_context_recall": None, "ragas_context_precision": None,
    }
    if result.failed:
        return entry  # invalid: never scored as zero recall
    texts = [c.text for c in result.chunks]
    if gold is not None and gold.passages:
        entry["recall_at_10"] = metrics.recall_at_k(texts, gold)
        entry["ndcg_at_10"] = metrics.ndcg_at_k(texts, gold, n_relevant)
        if ragas_ok:
            try:
                scores = await non_llm_context_metrics(texts, [p.text for p in gold.passages])
                entry["ragas_context_recall"], entry["ragas_context_precision"] = scores.context_recall, scores.context_precision
            except RagasUnavailable:
                pass
    return entry


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(results: list[dict[str, Any]], arms: list[str]) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for arm in arms:
        rows = [q["arms"][arm] for q in results]
        valid = [r for r in rows if not r["invalid"]]
        per_arm[arm] = {
            "questions": len(rows), "invalid": len(rows) - len(valid),
            "mean_recall_at_10": mean([r["recall_at_10"] for r in valid if r["recall_at_10"] is not None]),
            "mean_ndcg_at_10": mean([r["ndcg_at_10"] for r in valid if r["ndcg_at_10"] is not None]),
            "mean_ranking_length": mean([float(r["ranking_length"]) for r in valid]),
            "mean_latency_ms": mean([r["latency_ms"] for r in valid]),
        }
    graph_arm = "graph" if "graph" in arms else ("hybrid" if "hybrid" in arms else None)
    gate: dict[str, Any] = {"applicable": graph_arm is not None}
    if graph_arm:
        flags = [q["arms"][graph_arm]["graph_ranking_empty"] for q in results if not q["arms"][graph_arm]["invalid"]]
        fraction = (sum(1 for f in flags if f) / len(flags)) if flags else None
        enforced = len(results) >= GATE_MIN_QUESTIONS
        gate.update({"arm": graph_arm, "empty_graph_fraction": None if fraction is None else round(fraction, 4),
                     "threshold": EMPTY_GRAPH_GATE, "enforced": enforced,
                     "passed": True if fraction is None or not enforced else fraction <= EMPTY_GRAPH_GATE})
    return {"per_arm": per_arm, "empty_graph_gate": gate}


async def run(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    base = load_settings()
    live = base.arcana_llm_mode == "live" or base.arcana_embed_mode == "live"
    if live and not args.allow_paid:
        raise RunInvalid("live (paid) mode is configured; pass --allow-paid to run, or switch to fake mode")
    data_dir = Path(args.data_dir) if args.data_dir else ROOT / "data" / f"eval-{base.arcana_llm_mode}-{base.arcana_embed_mode}"
    settings: Settings = base.model_copy(update={"arcana_data_dir": data_dir})
    configure_logging("WARNING")

    questions_path, manifest_path, gold_dir = Path(args.questions_file), Path(args.manifest), Path(args.gold_dir)
    questions = select_questions(load_questions(questions_path), args.questions)
    arms = select_arms(args.arms)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    golds = {q["id"]: metrics.load_gold(gold_dir, q["id"]) for q in questions}
    require_approved_gold(golds, live)

    container = build_container(settings)
    ingestion = await ensure_corpus(container, manifest, Path(args.corpus_dir), args.reingest)
    failed_docs = [d["arxiv_id"] for d in ingestion if d["status"] != "ready"]
    if failed_docs:
        raise RunInvalid(f"documents failed to ingest: {failed_docs}")
    require_extraction_quality(ingestion)
    problems = check_corpus_parity(container.docs, container.vectors, container.graph)
    if problems:
        raise RunInvalid("corpus parity check failed: " + "; ".join(problems))

    chunks = container.docs.all_chunks()
    corpus_texts = [c.text for c in chunks]
    cached = CachingEmbedder(container.embedder)
    retrievers = {
        "dense": DenseRetriever(vectors=container.vectors, docs=container.docs, embedder=cached),
        "sparse": SparseRetriever(docs=container.docs),
        "graph": GraphRetriever(graph=container.graph, docs=container.docs),
    }
    ragas = ragas_status()

    results: list[dict[str, Any]] = []
    for q in questions:
        gold = golds[q["id"]]
        n_rel = metrics.relevant_count(corpus_texts, gold) if gold and gold.passages else 0
        arm_rows = {arm: await run_arm(arm, q["question"].strip(), retrievers, gold, corpus_texts, n_rel,
                                       bool(ragas["available"])) for arm in arms}
        results.append({
            "question_id": q["id"], "category": q["category"],
            "gold_status": gold.status if gold else "missing", "gold_approved": bool(gold and gold.approved),
            "n_gold_passages": len(gold.passages) if gold else 0,
            "relevant_chunks_in_corpus": n_rel, "arms": arm_rows,
        })

    started = datetime.now(UTC)
    mode = {"llm": settings.arcana_llm_mode, "embed": settings.arcana_embed_mode}
    out = {
        "run": {
            "timestamp": started.isoformat(), "label": args.label, "mode": mode,
            "warning": FAKE_WARNING if mode == {"llm": "fake", "embed": "fake"} else None,
            "protocol": protocol_stamp(), "relevance_rule": metrics.rule_stamp(), "ragas": ragas,
            "extraction_model": ANTHROPIC_MODELS["light"] if settings.arcana_llm_mode == "live" else "fake",
            "arms": arms, "query_embeddings_computed": cached.inner_calls,
            "hashes": {
                "questions_sha256": sha256_file(questions_path), "manifest_sha256": sha256_file(manifest_path),
                "graph_sha256": sha256_file(data_dir / "graph.json"), "vectors_sha256": sha256_file(data_dir / "vectors.npz"),
                "gold_sha256": {qid: sha256_file(gold_dir / f"{qid}.yaml") for qid, g in golds.items() if g is not None},
            },
            "corpus": {"documents": ingestion, "chunks": len(chunks), "parity_problems": problems},
        },
        "results": results,
        "summary": summarise(results, arms),
    }
    results_dir = Path(args.out)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}-{args.label}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return path, out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--questions", help="comma-separated question ids (default: all)")
    p.add_argument("--arms", default="all", help=f"'all' or a comma-separated subset of {list(ARMS)}")
    p.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    p.add_argument("--manifest", default=str(ROOT / "eval" / "corpus" / "MANIFEST.json"))
    p.add_argument("--corpus-dir", default=str(ROOT / "eval" / "corpus"), help="directory holding the manifest's PDFs")
    p.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    p.add_argument("--data-dir", help="store location (default: data/eval-<llm>-<embed>)")
    p.add_argument("--label", default="run")
    p.add_argument("--reingest", action="store_true", help="ingest again even if a document is already stored")
    p.add_argument("--allow-paid", action="store_true", help="permit live (paid) providers")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path, out = asyncio.run(run(args))
    except RunInvalid as exc:
        print(f"RUN REFUSED: {exc}", file=sys.stderr)
        return 2
    run_info = out["run"]
    if run_info["warning"]:
        print(run_info["warning"], file=sys.stderr)
    print(f"wrote {path}")
    for arm, s in out["summary"]["per_arm"].items():
        print(f"  {arm:7} recall@10={s['mean_recall_at_10']}  ndcg@10={s['mean_ndcg_at_10']}  "
              f"len={s['mean_ranking_length']}  invalid={s['invalid']}/{s['questions']}")
    gate = out["summary"]["empty_graph_gate"]
    if gate.get("empty_graph_fraction") is not None:
        print(f"  empty-graph fraction ({gate['arm']}): {gate['empty_graph_fraction']} "
              f"(gate {'enforced' if gate['enforced'] else 'not enforced below ' + str(GATE_MIN_QUESTIONS) + ' questions'})")
    if not run_info["ragas"]["available"]:
        print(f"  RAGAS metrics are null: {run_info['ragas']['reason']}", file=sys.stderr)
    invalid = sum(s["invalid"] for s in out["summary"]["per_arm"].values())
    if invalid:
        print(f"{invalid} question-arm run(s) are INVALID (a signal failed); see the results file.", file=sys.stderr)
        return 3
    if gate.get("enforced") and not gate["passed"]:
        print("EMPTY-GRAPH GATE FAILED: treat as an entity-resolution defect, not a finding about graphs.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
