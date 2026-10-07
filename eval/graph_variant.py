# ruff: noqa: ASYNC240  (an offline command-line tool: blocking file operations inside its coroutines are fine)
"""Build a graph variant beside the frozen baseline and compare the two (G1.3 to G1.5, D-34).

    uv run python eval/graph_variant.py slice   --from data/eval-live-live --to <dir> --papers 2312.10997,2408.04948,...
    uv run python eval/graph_variant.py rebuild --slice <dir> --to <dir2> --max-usd 1.5 --allow-paid
    uv run python eval/graph_variant.py compare --baseline <dir> --variant <dir2> --allow-paid

`slice` copies the pinned stores and keeps only the named papers (documents, vectors and graph, through the store
interfaces). `rebuild` copies that slice's documents and vectors unchanged and builds a NEW graph over the stored chunks
with the atomic builder (`api/ingestion/atomic.py`): no PDF is parsed and nothing is embedded, so the two data directories
differ in the graph and only the graph. `compare` runs the same retrievers, with the same constants, over both and writes
the numbers below. The pinned stores, the question set, the gold and every scoring constant are never touched.

PROTOCOL (fixed before any live run, constraint 9; it changes only by a declared amendment made before a run, never
after seeing results; the same text is in D-34):

  Corpus     the papers named for the slice, chosen by a rule stated before the run (not by outcome). Baseline = the pinned
             graph restricted to those papers (every other document, vector and graph entry deleted); variant = the same
             documents and vectors with a graph built by the atomic builder at the recorded prompt version. `compare`
             refuses unless both directories have the same chunk hash and the same vector hash.
  Questions  the frozen 20, gold unchanged. Retrieval is scored only on questions whose gold has at least one passage in
             the slice's chunks (the answerable ones); how many that is, and which, is in the result. With fewer than ten
             such questions retrieval numbers are DESCRIPTIVE: no significance test is run or claimed.
  Arms       `graph`, `hybrid` and the control `flat` (dense plus BM25, which has no graph and must not differ), over each
             data directory; the retrievers' constants and GRAPH_SCORING_VERSION are the frozen ones.
  Primary    Recall@10 and nDCG@10 per question and arm; the paired difference variant minus baseline per question; the
             mean, and the counts of questions that improved, tied and worsened.
  Secondary  the structural metrics of eval/graph_quality.py for both graphs on the same documents; the build's cost, drops
             and merges.
  Registered `no structural regression` means all three of: the variant's share of edges stated in one sentence of their
  gate      chunk is at least the baseline's; its number of distinct relation strings is at most the baseline's; its share
             of nodes found in two or more documents is at least the baseline's. `no large retrieval drop` means the
             hybrid arm's mean paired nDCG@10 difference is at least -0.05. The gate decides whether the builder becomes
             the default for new ingestion; a failed gate is a reason to improve the design and measure again (D-34).
  Spend      `rebuild` is the only paid step (extraction through the LLM seam, under the cap and a ceiling given with
             --max-usd, confirmed by Azim beforehand); `compare` computes at most the questions' query embeddings.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.container import Container, build_container
from api.core.logging import configure_logging
from api.core.settings import Settings, load_settings
from api.ingestion import atomic
from api.ingestion.embed import CachingEmbedder
from api.ingestion.pipeline import IngestDeps, build_graph
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.sparse import SparseRetriever
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.preflight import check_corpus_parity
from eval import metrics
from eval.graph_quality import measure
from eval.run_ablation import (
    INGESTION_REPORT,
    ROOT,
    RunInvalid,
    chunks_sha256,
    git_state,
    load_ingestion_report,
    load_questions,
    run_arm,
    sha256_file,
)

ARMS_COMPARED = ("graph", "hybrid", "flat")
MAX_NDCG_DROP = 0.05
PAIRED_MIN_FOR_SIGNIFICANCE = 10
VARIANT_FILE = "variant.json"
STORE_FILES = ("arcana.db", "vectors.npz", "graph.json", INGESTION_REPORT)


def copy_database(source: Path, target: Path) -> None:
    """Copy a SQLite database with the backup API. A plain file copy would miss what is still in the write-ahead log
    (`arcana.db-wal`), which is exactly where a store written moments ago keeps its rows."""
    reader = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()


def settings_for(data_dir: Path) -> Settings:
    return load_settings().model_copy(update={"arcana_data_dir": data_dir})


def is_live(settings: Settings) -> bool:
    return "live" in (settings.arcana_llm_mode, settings.arcana_embed_mode)


# ── slice ─────────────────────────────────────────────────────────────────────


def slice_stores(source: Path, target: Path, papers: list[str]) -> dict[str, Any]:
    """Copy `source`'s stores to `target` and delete every document but `papers` (arxiv ids), through the store interfaces."""
    if target.exists() and any(target.iterdir()):
        raise RunInvalid(f"{target} is not empty: a slice is made into a new directory")
    report = load_ingestion_report(source)
    unknown = [p for p in papers if p not in report]
    if unknown:
        raise RunInvalid(f"not in {source / INGESTION_REPORT}: {unknown}")
    target.mkdir(parents=True, exist_ok=True)
    copy_database(source / "arcana.db", target / "arcana.db")
    for name in ("vectors.npz", "graph.json"):
        shutil.copyfile(source / name, target / name)

    settings = settings_for(target)
    container = build_container(settings)
    keep = {report[p]["doc_id"] for p in papers}
    for document in container.docs.list_documents():
        if document.id in keep:
            continue
        chunk_ids = container.docs.delete_document(document.id)
        container.vectors.delete(chunk_ids)
        container.graph.delete_document(document.id, chunk_ids)
    container.graph.save()
    container.vectors.save()
    problems = check_corpus_parity(container.docs, container.vectors, container.graph)
    if problems:
        raise RunInvalid("the slice does not pass the corpus parity check: " + "; ".join(problems))
    (target / INGESTION_REPORT).write_text(json.dumps([report[p] for p in papers], indent=2), encoding="utf-8")
    chunks = container.docs.all_chunks()
    return {
        "papers": papers,
        "documents": len(keep),
        "chunks": len(chunks),
        "hashes": {
            "graph_sha256": sha256_file(target / "graph.json"),
            "vectors_sha256": sha256_file(target / "vectors.npz"),
            "chunks_sha256": chunks_sha256(chunks),
        },
    }


# ── rebuild ───────────────────────────────────────────────────────────────────


async def rebuild_graph(
    slice_dir: Path, target: Path, builder: str, max_usd: float, allow_paid: bool
) -> dict[str, Any]:
    """Build a new graph for `slice_dir`'s documents with `builder`, into `target` (documents and vectors copied unchanged)."""
    if target.exists() and any(target.iterdir()):
        raise RunInvalid(f"{target} is not empty: a variant is built into a new directory")
    settings = settings_for(target)
    if is_live(settings) and not allow_paid:
        raise RunInvalid("live (paid) mode is configured; pass --allow-paid to rebuild with a real model")
    if max_usd <= 0:
        raise RunInvalid("--max-usd must be a positive ceiling")
    target.mkdir(parents=True, exist_ok=True)
    copy_database(slice_dir / "arcana.db", target / "arcana.db")
    shutil.copyfile(slice_dir / "vectors.npz", target / "vectors.npz")

    container = build_container(settings)
    deps = IngestDeps(
        docs=container.docs,
        vectors=container.vectors,
        graph=NetworkXGraphStore(target / "graph.json"),
        embedder=container.embedder,
        llm=container.llm,
        builder=builder,
    )
    deps.graph.save()  # an empty graph file exists even if the ceiling stops the build before the first document
    saved = load_ingestion_report(slice_dir)
    documents: list[dict[str, Any]] = []
    spent_before = container.ledger.month_total()
    per_chunk = 0.0
    for arxiv_id, entry in saved.items():
        chunks = container.docs.chunks_for_document(entry["doc_id"])
        projected = (container.ledger.month_total() - spent_before) + len(chunks) * max(per_chunk, 0.0037)
        if projected > max_usd:
            documents.append(
                {"arxiv_id": arxiv_id, "doc_id": entry["doc_id"], "status": "not_built_ceiling", "chunks": len(chunks)}
            )
            break
        before = container.ledger.month_total()
        nodes, edges, failures, report = await build_graph(chunks, deps)
        deps.graph.save()
        cost = round(container.ledger.month_total() - before, 6)
        if chunks:
            per_chunk = max(per_chunk, cost / len(chunks)) if per_chunk else cost / len(chunks)
        documents.append(
            {
                "arxiv_id": arxiv_id,
                "doc_id": entry["doc_id"],
                "status": "ready",
                "chunks": len(chunks),
                "nodes": nodes,
                "edges": edges,
                "extraction_failures": failures,
                "cost_usd": cost,
                "build_report": report,
            }
        )
    spent = round(container.ledger.month_total() - spent_before, 6)
    (target / INGESTION_REPORT).write_text(json.dumps(documents, indent=2), encoding="utf-8")
    info = {
        "builder": builder,
        "prompt_version": atomic.PROMPT_VERSION if builder == "atomic" else None,
        "max_usd": max_usd,
        "spent_usd": spent,
        "documents": len(documents),
        "complete": all(d["status"] == "ready" for d in documents) and len(documents) == len(saved),
        "code": git_state(),
        "mode": {"llm": settings.arcana_llm_mode, "embed": settings.arcana_embed_mode},
        "slice_hashes": {
            "vectors_sha256": sha256_file(target / "vectors.npz"),
            "chunks_sha256": chunks_sha256(container.docs.all_chunks()),
        },
        "graph_sha256": sha256_file(target / "graph.json"),
    }
    (target / VARIANT_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


# ── compare ───────────────────────────────────────────────────────────────────


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def paired(rows: list[dict[str, Any]], arm: str, metric: str) -> dict[str, Any]:
    diffs = []
    for r in rows:
        a, b = r["baseline"][arm][metric], r["variant"][arm][metric]
        if a is not None and b is not None and not r["baseline"][arm]["invalid"] and not r["variant"][arm]["invalid"]:
            diffs.append(round(b - a, 6))
    return {
        "pairs": len(diffs),
        "baseline_mean": mean([r["baseline"][arm][metric] for r in rows if r["baseline"][arm][metric] is not None]),
        "variant_mean": mean([r["variant"][arm][metric] for r in rows if r["variant"][arm][metric] is not None]),
        "mean_difference": mean(diffs),
        "improved": sum(d > 0 for d in diffs),
        "tied": sum(d == 0 for d in diffs),
        "worsened": sum(d < 0 for d in diffs),
    }


def registered_gate(baseline: dict[str, Any], variant: dict[str, Any], hybrid_ndcg: dict[str, Any]) -> dict[str, Any]:
    """The pre-registered gate, evaluated and reported. It states facts; whether to adopt is Azim's decision."""

    def share(m: dict[str, Any], key: str) -> float:
        return m[key]["share"] or 0.0

    stated = share(variant, "edges_stated_in_one_sentence") >= share(baseline, "edges_stated_in_one_sentence")
    relations = variant["distinct_relations"] <= baseline["distinct_relations"]
    shared = share(variant, "nodes_in_two_or_more_documents") >= share(baseline, "nodes_in_two_or_more_documents")
    drop = hybrid_ndcg["mean_difference"]
    return {
        "structural_no_regression": {
            "edges_stated_in_one_sentence_not_lower": stated,
            "distinct_relations_not_higher": relations,
            "nodes_in_two_or_more_documents_not_lower": shared,
            "passed": stated and relations and shared,
        },
        "no_large_retrieval_drop": {
            "hybrid_mean_ndcg_difference": drop,
            "threshold": -MAX_NDCG_DROP,
            "passed": drop is None or drop >= -MAX_NDCG_DROP,
        },
    }


async def compare_variants(args: argparse.Namespace) -> dict[str, Any]:
    baseline_dir, variant_dir = Path(args.baseline), Path(args.variant)
    base_settings = settings_for(baseline_dir)
    live = is_live(base_settings)
    if live and not args.allow_paid:
        raise RunInvalid("live (paid) mode is configured; pass --allow-paid (it pays only for query embeddings)")
    configure_logging("WARNING")
    if sha256_file(baseline_dir / "vectors.npz") != sha256_file(variant_dir / "vectors.npz"):
        raise RunInvalid(
            "the two directories do not hold the same vectors: a graph comparison must change only the graph"
        )
    containers: dict[str, Container] = {
        "baseline": build_container(base_settings),
        "variant": build_container(settings_for(variant_dir)),
    }
    for name, c in containers.items():
        problems = check_corpus_parity(c.docs, c.vectors, c.graph)
        if problems:
            raise RunInvalid(f"{name}: corpus parity check failed: " + "; ".join(problems))
    base_chunks = containers["baseline"].docs.all_chunks()
    same = {
        "chunks": chunks_sha256(base_chunks) == chunks_sha256(containers["variant"].docs.all_chunks()),
        "vectors": sha256_file(baseline_dir / "vectors.npz") == sha256_file(variant_dir / "vectors.npz"),
    }
    if not all(same.values()):
        raise RunInvalid(f"the two directories do not hold the same corpus and vectors: {same}")

    questions_path, gold_dir = Path(args.questions_file), Path(args.gold_dir)
    questions = load_questions(questions_path)
    corpus_texts = [c.text for c in base_chunks]
    embedder = CachingEmbedder(containers["baseline"].embedder)  # one query embedding per question, shared by both
    retrievers: dict[str, dict[str, Any]] = {}
    for name, c in containers.items():
        retrievers[name] = {
            "dense": DenseRetriever(vectors=c.vectors, docs=c.docs, embedder=embedder),
            "sparse": SparseRetriever(docs=c.docs),
            "graph": GraphRetriever(graph=c.graph, docs=c.docs),
        }

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for q in questions:
        gold = metrics.load_gold(gold_dir, q["id"])
        n_rel = metrics.relevant_count(corpus_texts, gold) if gold and gold.passages else 0
        if n_rel == 0:
            skipped.append({"question_id": q["id"], "reason": "no gold passage in this slice's chunks"})
            continue
        row: dict[str, Any] = {"question_id": q["id"], "category": q["category"], "relevant_chunks_in_slice": n_rel}
        for name in containers:
            row[name] = {
                arm: await run_arm(arm, q["question"].strip(), retrievers[name], gold, corpus_texts, n_rel, False)
                for arm in ARMS_COMPARED
            }
        rows.append(row)

    texts = {c.id: c.text for c in base_chunks}
    structure = {name: measure(c.graph.nodes(), c.graph.edges(), texts) for name, c in containers.items()}
    summary = {
        arm: {metric: paired(rows, arm, metric) for metric in ("recall_at_10", "ndcg_at_10")} for arm in ARMS_COMPARED
    }
    control_differs = any(r["baseline"]["flat"]["chunk_ids"] != r["variant"]["flat"]["chunk_ids"] for r in rows)
    variant_info = (
        json.loads((variant_dir / VARIANT_FILE).read_text(encoding="utf-8"))
        if (variant_dir / VARIANT_FILE).exists()
        else None
    )
    started = datetime.now(UTC)
    mode = {"llm": base_settings.arcana_llm_mode, "embed": base_settings.arcana_embed_mode}
    return {
        "run": {
            "timestamp": started.isoformat(),
            "label": args.label,
            "mode": mode,
            "warning": None
            if live
            else "FAKE MODE: this run checks the plumbing; its numbers say nothing about retrieval quality.",
            "code": git_state(),
            "protocol": __doc__,
            "variant": variant_info,
            "hashes": {
                "questions_sha256": sha256_file(questions_path),
                "baseline_graph_sha256": sha256_file(baseline_dir / "graph.json"),
                "variant_graph_sha256": sha256_file(variant_dir / "graph.json"),
                "vectors_sha256": sha256_file(baseline_dir / "vectors.npz"),
                "chunks_sha256": chunks_sha256(base_chunks),
            },
            "query_embeddings_computed": embedder.inner_calls,
            "answerable_questions": [r["question_id"] for r in rows],
            "skipped_questions": skipped,
            "descriptive_only": len(rows) < PAIRED_MIN_FOR_SIGNIFICANCE,
            "control_arm_flat_differs": control_differs,
        },
        "structure": structure,
        "retrieval": {"summary": summary, "per_question": rows},
        "gate": registered_gate(structure["baseline"], structure["variant"], summary["hybrid"]["ndcg_at_10"]),
    }


# ── command line ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a graph variant beside the frozen baseline and compare the two.")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("slice", help="copy the pinned stores, keeping only the named papers")
    s.add_argument("--from", dest="source", required=True)
    s.add_argument("--to", required=True)
    s.add_argument("--papers", required=True, help="comma-separated arxiv ids from the source's ingestion report")
    r = sub.add_parser("rebuild", help="build a new graph over a slice's stored chunks")
    r.add_argument("--slice", required=True)
    r.add_argument("--to", required=True)
    r.add_argument("--builder", default="atomic", choices=["atomic", "freeform"])
    r.add_argument("--max-usd", type=float, required=True, help="a ceiling for this build, confirmed beforehand")
    r.add_argument("--allow-paid", action="store_true")
    r.add_argument("--allow-dirty", action="store_true", help="for tests only: a result should name committed code")
    c = sub.add_parser("compare", help="run the same retrievers over both and write the comparison")
    c.add_argument("--baseline", required=True)
    c.add_argument("--variant", required=True)
    c.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    c.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    c.add_argument("--out", default=str(ROOT / "eval" / "results"))
    c.add_argument("--label", default="graph-variant")
    c.add_argument("--allow-paid", action="store_true")
    c.add_argument("--allow-dirty", action="store_true", help="for tests only: a result should name committed code")
    args = ap.parse_args(argv)

    try:
        if args.command == "slice":
            info = slice_stores(
                Path(args.source), Path(args.to), [p.strip() for p in args.papers.split(",") if p.strip()]
            )
            print(json.dumps(info, indent=2))
            return 0
        state = git_state()
        if not args.allow_dirty and (state["commit"] is None or state["dirty"] is not False):
            print(f"commit first: a result must name the code it ran on ({state['changed_files']})", file=sys.stderr)
            return 2
        if args.command == "rebuild":
            info = asyncio.run(
                rebuild_graph(Path(args.slice), Path(args.to), args.builder, args.max_usd, args.allow_paid)
            )
            print(json.dumps(info, indent=2))
            return 0
        result = asyncio.run(compare_variants(args))
    except RunInvalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{args.label}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {path}")
    print(json.dumps(result["gate"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
