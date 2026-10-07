# ruff: noqa: ASYNC240  (an offline command-line tool: blocking file operations inside its coroutines are fine)
"""Build a graph variant beside the frozen baseline and compare the two (G1.3 to G1.5, D-34).

    uv run python eval/graph_variant.py slice   --from data/eval-live-live --to <dir> --papers 2309.15217v2,...   (the versioned ids of the ingestion report)
    uv run python eval/graph_variant.py rebuild --slice <dir> --to <dir2> --max-usd 1.5 --allow-paid
    uv run python eval/graph_variant.py compare --baseline <dir> --variant <dir2> --allow-paid
    uv run python eval/graph_variant.py choose  --from data/eval-live-live
    uv run python eval/graph_variant.py audit   --baseline <dir> --variant <dir2>

`slice` copies the pinned stores and keeps only the named papers (documents, vectors and graph, through the store
interfaces). `rebuild` copies that slice's documents and vectors unchanged and builds a NEW graph over the stored chunks
with the atomic builder (`api/ingestion/atomic.py`): no PDF is parsed and nothing is embedded, so the two data directories
differ in the graph and only the graph. `compare` runs the same retrievers, with the same constants, over both and writes
the numbers below. The pinned stores, the question set, the gold and every scoring constant are never touched.

PROTOCOL (fixed before any live run, constraint 9; amended 2026-10-07 after the retrieval audit and BEFORE any live
run, builder prompt g1-2; it changes only by a declared amendment made before a run, never after seeing results; the same
text is in D-34):

  Corpus     the papers chosen by the `choose` command (rule below). Baseline = the pinned graph restricted to those papers
             (every other document, vector and graph entry deleted); variant = the same documents and vectors with a graph
             built by the atomic builder at the recorded prompt version. `compare` refuses unless both directories have the
             same chunk hash and the same vector bytes, and unless the variant has a complete rebuild record.
  Slice rule  greedy, stated before the choice: start with no paper; repeatedly add the paper that makes the most
             not-yet-answerable frozen questions answerable per chunk (a question is answerable by a paper if the paper has a
             chunk holding one of its gold passages); ties go to the lower arxiv id; stop when the next paper would take the
             slice past 450 chunks or no paper adds a question. Build order is arxiv id ascending (the builder does not depend
             on order: the alias links are per chunk).
  Pilot      one paper, the shortest in the manifest (2309.15217v2, Ragas), rebuilt first to measure cost and to check that
             the builder runs. Its outputs may be examined only to find a defect, and any change to the prompt or the rules
             made because of it is a declared amendment with a new prompt version; every paper of the measured slice is then
             rebuilt with that version (the pilot is not a result). The pilot paper may be in the slice.
  Questions  the frozen 20, gold unchanged. Retrieval is scored only on questions whose gold has at least one passage in the
             slice's chunks (the answerable ones). With fewer than ten such questions retrieval is DESCRIPTIVE: not evaluated
             by the gate, and no significance test is run or claimed. Recall@10 divides by all of a question's gold passages,
             including any outside the slice, so absolute values are depressed in the same way for both graphs.
  Arms       `graph`, `hybrid` and the control `flat` (dense plus BM25, which has no graph) over each data directory; the
             retrievers' constants and GRAPH_SCORING_VERSION are the frozen ones. If `flat` differs between the directories the
             run is refused: something other than the graph changed.
  Primary    Recall@10 and nDCG@10 per question and arm, the paired difference variant minus baseline, the mean, and the
             counts improved, tied and worsened; for the `graph` arm as well as `hybrid`.
  Validity   the graph arm is INVALID (flagged at the top of the result) if, on the variant, it returns no passage for more
             than half of the answerable questions. The frozen resolver matches query words to node ids only, so the result
             reports, for both graphs, the entity-resolution hit rate and the number of questions with an empty graph ranking.
  Registered `no structural regression` means ALL of: (1) the share of the slice's chunks that name at least one concept is
  gate      at least 0.8 times the baseline's (the graph signal reaches passages through nodes); (2) the share of node-to-chunk
             links owned by the largest one percent of nodes is not above the baseline's. Measured by the same code on both
             graphs. REPORTED but not gating: the share of edges stated in one sentence, the number of distinct relation
             strings, the share of nodes in two or more documents (a sentence-checking builder passes these by construction
             or by its vocabulary), the share of edge ends owned by the ten largest nodes (it rises in any graph with fewer
             edges: the pilot's graph had a tenth of the baseline's edges, so it was confounded by sparsity; amended after the
             pilot, before the slice run), edges per node, nodes with no edge, the label check, and the share of chunks that
             carry a relation.
             `no large retrieval drop` means the mean paired nDCG@10 difference is at least -0.05 for the `hybrid` arm AND
             for the `graph` arm; it reads `not_evaluable` when retrieval is descriptive, and then the decision does not rest
             on it. An audit sample (see `audit`: 50 edges per graph, fixed seed) is drawn and read; its result is reported
             beside the gate, not folded into it (model-judged scores are never primary). The gate, with the validity flag and
             the audit, is what Azim reads to decide whether the builder becomes the default for new ingestion; a failed gate
             is a reason to improve the design and measure again (D-34), never to drop the direction.
  Declared differences  the atomic extractor allows 25 concepts and 40 relations per chunk and 3,072 output tokens; the free-form
             baseline allows 30 entities and 40 relations and 2,048. Both are the light tier (Haiku). One build is one sample:
             no temperature is set, so extraction is not reproducible run to run, and builder variance is not measured.
  Spend      `rebuild` is the only paid step (extraction through the LLM seam, under the cap and a ceiling given with
             --max-usd that is enforced on every call, confirmed by Azim beforehand); `compare` computes at most the
             questions' query embeddings.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.container import Container, build_container
from api.core.errors import ArcanaError, SpendCapExceeded
from api.core.logging import configure_logging
from api.core.settings import Settings, load_settings
from api.ingestion import atomic, atomic2
from api.ingestion.embed import CachingEmbedder
from api.ingestion.pipeline import IngestDeps, build_graph
from api.llm.models import ANTHROPIC_MODELS
from api.llm.pricing import estimate_call_cost
from api.llm.service import LLMService
from api.llm.types import LLMRequest
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.sparse import SparseRetriever
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.preflight import check_corpus_parity
from api.vault.types import ClaimDraft
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

EXPECTED_PER_CHUNK_USD = 0.0040
"""The start-of-document projection before anything has been measured in a build: the pilot measured $0.00358 per chunk for
the atomic prompt (35 chunks, 2026-10-07), rounded up. The first estimate, $0.0067, was the cost auditor's guess."""
ARMS_COMPARED = ("graph", "hybrid", "flat")
MAX_NDCG_DROP = 0.05
PAIRED_MIN_FOR_SIGNIFICANCE = 10
VARIANT_FILE = "variant.json"
CLAIMS_FILE = "claims.json"
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


class CeilingReached(ArcanaError):
    """The next call could take this build past its `--max-usd` ceiling; refused before it was sent."""

    code = "spend_cap_exceeded"


class CeilingGuard:
    """Stands in for the LLM seam during a rebuild and enforces the ceiling on every call, not only at the start of a
    document: a call is refused before it is sent if the money already spent in this build, plus the worst case of the
    calls in flight, plus the worst case of this one, would pass the ceiling. The monthly cap is still enforced beneath it by
    the seam's own reserve-before-send."""

    def __init__(self, inner: LLMService, spent_before: float, max_usd: float):
        self._inner, self._spent_before, self._max_usd = inner, spent_before, max_usd
        self._in_flight = 0.0

    def remaining_usd(self) -> float | None:
        return self._inner.remaining_usd()

    async def complete(self, request: LLMRequest, budget: Any = None) -> Any:
        model = ANTHROPIC_MODELS[request.tier]
        worst = estimate_call_cost("anthropic", model, request)
        spent = self._inner._ledger.month_total() - self._spent_before  # pyright: ignore[reportPrivateUsage]
        if spent + self._in_flight + worst > self._max_usd:
            raise CeilingReached(f"the next call could take this build past its ${self._max_usd:.2f} ceiling")
        self._in_flight += worst
        try:
            return await self._inner.complete(request, budget)
        finally:
            self._in_flight -= worst


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
    claims: list[ClaimDraft] = []
    deps = IngestDeps(
        docs=container.docs,
        vectors=container.vectors,
        graph=NetworkXGraphStore(target / "graph.json"),
        embedder=container.embedder,
        llm=CeilingGuard(container.llm, container.ledger.month_total(), max_usd),  # type: ignore[arg-type]
        builder=builder,
        claim_sink=claims,
    )
    deps.graph.save()  # an empty graph file exists even if the ceiling stops the build before the first document
    saved = load_ingestion_report(slice_dir)
    documents: list[dict[str, Any]] = []
    spent_before = container.ledger.month_total()
    per_chunk = 0.0
    for arxiv_id, entry in saved.items():
        chunks = container.docs.chunks_for_document(entry["doc_id"])
        projected = (container.ledger.month_total() - spent_before) + len(chunks) * max(
            per_chunk, EXPECTED_PER_CHUNK_USD
        )
        if projected > max_usd:
            documents.append(
                {"arxiv_id": arxiv_id, "doc_id": entry["doc_id"], "status": "not_built_ceiling", "chunks": len(chunks)}
            )
            break
        before = container.ledger.month_total()
        try:
            nodes, edges, failures, report = await build_graph(chunks, deps)
        except (CeilingReached, SpendCapExceeded) as exc:
            # The half-built document is discarded (the graph is written only when all of a document's chunks return);
            # what was spent on it is on the ledger and in the report.
            documents.append(
                {
                    "arxiv_id": arxiv_id,
                    "doc_id": entry["doc_id"],
                    "status": "not_built_ceiling" if isinstance(exc, CeilingReached) else "not_built_cap",
                    "chunks": len(chunks),
                    "cost_usd": round(container.ledger.month_total() - before, 6),
                }
            )
            break
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
    if builder == "atomic2":  # claim notes belong to the vault: kept beside the graph for `vault_tool.py build`
        (target / CLAIMS_FILE).write_text(
            json.dumps([dataclasses.asdict(c) for c in claims], indent=2), encoding="utf-8"
        )
    info = {
        "builder": builder,
        "prompt_version": {"atomic": atomic.PROMPT_VERSION, "atomic2": atomic2.PROMPT_VERSION}.get(builder),
        "claims": len(claims),
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


COVERAGE_FLOOR = 0.8
"""The variant's concept coverage of the slice's chunks must be at least this fraction of the baseline's."""
EMPTY_GRAPH_LIMIT = 0.5
"""The graph arm is invalid if it returns nothing for more than this share of the answerable questions."""


def registered_gate(
    baseline: dict[str, Any],
    variant: dict[str, Any],
    hybrid_ndcg: dict[str, Any],
    graph_ndcg: dict[str, Any],
    *,
    descriptive_only: bool,
    graph_arm_valid: bool,
) -> dict[str, Any]:
    """The pre-registered gate, evaluated and reported. It states facts; whether to adopt is Azim's decision."""

    def number(value: float | None) -> float:
        return value if value is not None else 0.0

    coverage = number(variant["chunk_coverage"]["with_a_concept"]) >= COVERAGE_FLOOR * number(
        baseline["chunk_coverage"]["with_a_concept"]
    )
    top_percent = number(variant["hub_concentration"]["top_1_percent_share_of_chunk_links"]) <= number(
        baseline["hub_concentration"]["top_1_percent_share_of_chunk_links"]
    )
    structural = coverage and top_percent

    def retrieval_clause() -> dict[str, Any]:
        if descriptive_only:
            return {"status": "not_evaluable", "reason": "fewer than ten answerable questions: descriptive only"}
        hybrid, graph = hybrid_ndcg["mean_difference"], graph_ndcg["mean_difference"]
        ok = all(d is None or d >= -MAX_NDCG_DROP for d in (hybrid, graph))
        return {
            "status": "passed" if ok else "failed",
            "hybrid_mean_ndcg_difference": hybrid,
            "graph_mean_ndcg_difference": graph,
            "threshold": -MAX_NDCG_DROP,
        }

    retrieval = retrieval_clause()
    ready = structural and graph_arm_valid and retrieval["status"] != "failed"
    return {
        "structural_no_regression": {
            "concept_coverage_at_least_0_8_of_baseline": coverage,
            "top_1_percent_link_share_not_higher": top_percent,
            "passed": structural,
        },
        "no_large_retrieval_drop": retrieval,
        "graph_arm_valid": graph_arm_valid,
        "ready_for_azim_to_decide": ready,
        "reported_not_gating": {
            key: {"baseline": baseline[key], "variant": variant[key]}
            for key in (
                "edges_stated_in_one_sentence",
                "distinct_relations",
                "nodes_in_two_or_more_documents",
                "edges_per_node",
                "nodes_with_no_edge",
                "nodes_label_in_own_chunks",
                "hub_concentration",
                "chunk_coverage",
            )
        },
    }


def graph_arm_is_valid(report: dict[str, Any]) -> bool:
    """False if the graph arm returned nothing for more than half of the answerable questions."""
    answerable = report["questions"]
    return not answerable or report["graph_ranking_empty"] / answerable <= EMPTY_GRAPH_LIMIT


def resolution_report(rows: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """How much of each answerable question the graph recognised, and how often the graph arm returned nothing."""
    cells = [r[side]["graph"] for r in rows if not r[side]["graph"]["invalid"]]
    resolved = [c["resolution"] for c in cells if c.get("resolution")]
    empty = sum(1 for c in cells if c["ranking_length"] == 0)
    return {
        "questions": len(cells),
        "graph_ranking_empty": empty,
        "mean_hit_rate": mean([r["hit_rate"] for r in resolved]),
        "mean_exact_hit_rate": mean([r["exact_hit_rate"] for r in resolved]),
        "fraction_with_any_entity": round(sum(1 for r in resolved if r["entities"]) / len(cells), 4) if cells else None,
    }


async def compare_variants(args: argparse.Namespace) -> dict[str, Any]:
    baseline_dir, variant_dir = Path(args.baseline), Path(args.variant)
    base_settings = settings_for(baseline_dir)
    live = is_live(base_settings)
    if live and not args.allow_paid:
        raise RunInvalid("live (paid) mode is configured; pass --allow-paid (it pays only for query embeddings)")
    configure_logging("WARNING")
    recorded = variant_dir / VARIANT_FILE
    if not recorded.exists() or not json.loads(recorded.read_text(encoding="utf-8")).get("complete"):
        raise RunInvalid(
            f"{variant_dir} has no complete rebuild record ({VARIANT_FILE}): a partial graph is not compared"
        )
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
    if control_differs:
        raise RunInvalid(
            "the flat control (dense plus BM25, no graph) differs between the directories: something other than the graph changed"
        )
    resolution = {side: resolution_report(rows, side) for side in ("baseline", "variant")}
    graph_arm_valid = graph_arm_is_valid(resolution["variant"])
    descriptive_only = len(rows) < PAIRED_MIN_FOR_SIGNIFICANCE
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
            "descriptive_only": descriptive_only,
            "control_arm_flat_differs": False,
        },
        "structure": structure,
        "retrieval": {"summary": summary, "per_question": rows},
        "graph_arm_valid": graph_arm_valid,
        "resolution": resolution,
        "gate": registered_gate(
            structure["baseline"],
            structure["variant"],
            summary["hybrid"]["ndcg_at_10"],
            summary["graph"]["ndcg_at_10"],
            descriptive_only=descriptive_only,
            graph_arm_valid=graph_arm_valid,
        ),
    }


# ── choose: the slice rule, as code ───────────────────────────────────────────

SLICE_CHUNK_BUDGET = 450


def choose_papers(
    source: Path, questions_path: Path, gold_dir: Path, budget: int = SLICE_CHUNK_BUDGET
) -> dict[str, Any]:
    """The slice rule of the protocol: greedily add the paper that makes the most not-yet-answerable questions answerable
    per chunk (ties to the lower arxiv id), until the next paper would pass the chunk budget or none adds a question. A
    question is answerable by a paper if one of its gold passages is in a chunk of the paper. No arm is run and nothing
    about any result is used: only the gold and the chunk counts."""
    from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

    docs = SqliteDocStore(make_engine(source / "arcana.db"))
    report = load_ingestion_report(source)
    texts = {a: [c.text for c in docs.chunks_for_document(e["doc_id"])] for a, e in report.items()}
    questions = load_questions(questions_path)
    golds = {q["id"]: metrics.load_gold(gold_dir, q["id"]) for q in questions}
    covers: dict[str, set[str]] = {
        a: {qid for qid, g in golds.items() if g is not None and g.passages and metrics.relevant_count(t, g) > 0}
        for a, t in texts.items()
    }
    chosen: list[str] = []
    answerable: set[str] = set()
    chunks = 0
    while True:
        best: tuple[float, str] | None = None
        for a in sorted(covers):
            gain = len(covers[a] - answerable)
            if a in chosen or not gain or chunks + len(texts[a]) > budget:
                continue
            ratio = gain / max(len(texts[a]), 1)
            if best is None or ratio > best[0]:
                best = (ratio, a)
        if best is None:
            break
        chosen.append(best[1])
        answerable |= covers[best[1]]
        chunks += len(texts[best[1]])
    ordered = sorted(chosen)
    return {
        "rule": f"greedy by newly answerable questions per chunk, ties to the lower arxiv id, chunk budget {budget}",
        "papers": ordered,
        "chunks": chunks,
        "answerable_questions": sorted(answerable),
        "per_paper": {a: {"chunks": len(texts[a]), "answers": sorted(covers[a])} for a in ordered},
        "questions_never_answerable_in_this_budget": sorted(set(golds) - answerable),
    }


# ── audit: a fixed-seed sample of edges for a human to read ───────────────────


def audit_sample(baseline: Path, variant: Path, n: int, seed: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """`n` edges from each graph, drawn with a fixed seed, mixed in one random order with the graph hidden. Each item shows
    the two concepts, the relation as stored and the sentence to judge it against (the stored evidence, or for the baseline the
    first sentence of the source chunk that holds both labels, else the chunk's start). Returns the items and a key (item
    number to graph) kept apart so the reader does not see it."""
    import random

    from api.genui.evidence import label_in_quote
    from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

    rng = random.Random(seed)
    items: list[dict[str, Any]] = []
    for side, directory in (("baseline", baseline), ("variant", variant)):
        graph = NetworkXGraphStore(directory / "graph.json")
        docs = SqliteDocStore(make_engine(directory / "arcana.db"))
        labels = {node.id: node.label for node in graph.nodes()}
        edges = sorted(graph.edges(), key=lambda e: (e.src, e.dst, e.relation, e.chunk_id))
        for e in rng.sample(edges, min(n, len(edges))):
            chunk = docs.get_chunk(e.chunk_id)
            text = " ".join(chunk.text.split()) if chunk else ""
            sentence = e.evidence
            if sentence is None:
                pieces = [p for p in re.split(r"(?<=[.!?])\s+", text) if p]
                sentence = next(
                    (p for p in pieces if label_in_quote(p, labels[e.src]) and label_in_quote(p, labels[e.dst])),
                    text[:240],
                )
            items.append(
                {
                    "graph": side,
                    "concept_a": labels[e.src],
                    "relation": e.relation,
                    "concept_b": labels[e.dst],
                    "sentence": sentence,
                }
            )
    rng.shuffle(items)
    key = {str(i + 1): item.pop("graph") for i, item in enumerate(items)}
    for i, item in enumerate(items):
        item["item"] = i + 1
        item["relation_supported"] = None
        item["direction_supported"] = None
    return items, key


def audit_markdown(items: list[dict[str, Any]]) -> str:
    lines = [
        "# Edge audit sample",
        "",
        "For each item, judge from the sentence alone: is the relation (concept A, relation, concept B) supported, and is its",
        "direction right? Write yes, no or unclear. The graph each item came from is not shown.",
        "",
    ]
    for item in items:
        lines += [
            f"{item['item']}. **{item['concept_a']}** `{item['relation']}` **{item['concept_b']}**",
            f"   > {item['sentence']}",
            "   relation supported: ___   direction right: ___",
            "",
        ]
    return "\n".join(lines)


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
    r.add_argument("--builder", default="atomic", choices=["atomic", "atomic2", "freeform"])
    r.add_argument("--max-usd", type=float, required=True, help="a ceiling for this build, confirmed beforehand")
    r.add_argument("--allow-paid", action="store_true")
    r.add_argument("--allow-dirty", action="store_true", help="for tests only: a result should name committed code")
    ch = sub.add_parser("choose", help="apply the slice rule and print the papers")
    ch.add_argument("--from", dest="source", required=True)
    ch.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    ch.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    ch.add_argument("--budget", type=int, default=SLICE_CHUNK_BUDGET)
    a = sub.add_parser("audit", help="draw the fixed-seed edge sample for a human to read")
    a.add_argument("--baseline", required=True)
    a.add_argument("--variant", required=True)
    a.add_argument("--n", type=int, default=50)
    a.add_argument("--seed", type=int, default=20261007)
    a.add_argument("--out", default=str(ROOT / "eval" / "results"))
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
        if args.command == "choose":
            print(
                json.dumps(
                    choose_papers(Path(args.source), Path(args.questions_file), Path(args.gold_dir), args.budget),
                    indent=2,
                )
            )
            return 0
        if args.command == "audit":
            items, key = audit_sample(Path(args.baseline), Path(args.variant), args.n, args.seed)
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            (out / f"{stamp}-audit-sample.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
            (out / f"{stamp}-audit-sample.md").write_text(audit_markdown(items), encoding="utf-8")
            (out / f"{stamp}-audit-key.json").write_text(
                json.dumps({"seed": args.seed, "n": args.n, "key": key}, indent=2), encoding="utf-8"
            )
            print(f"wrote {len(items)} items to {out}")
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
