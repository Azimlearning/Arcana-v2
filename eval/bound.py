"""The admission-rate study (P2 D2): the first measurement of the bound.

    uv run python eval/bound.py --allow-paid \\
        --expect-graph-sha256 <hash> --expect-vectors-sha256 <hash> --expect-chunks-sha256 <hash>

The MCAIT paper's "bound" says a generative interface can contain only components whose structural precondition the
retrieved evidence can satisfy: X(R) = { c : precondition(c) is satisfiable from R }. This study counts, for each of the
frozen 20 questions and for two retrieval layers, which catalog components the Composer's own `check` functions would
admit, and why not when they would not. It is an admission rate over 20 questions on one ingestion. It is **not** a
quality score; it is **not** a proof of the paper's claim (that the hybrid layer admits a superset of what flat retrieval
admits holds by how the preconditions are written here; what is measured is how often the extra components are
available); and it says nothing about questions unlike these 20.

PROTOCOL (fixed before any run, constraint 9; it changes only by a declared amendment made before a run, never after
seeing results):

  Questions   the frozen 20 in eval/questions.yaml, `q-single-01` included (its expected admission of relational
              components is none: it is the "should find nothing" control).
  Stores      the one-shot live ingestion (data/eval-live-live). The run is refused unless the graph, vector and chunk
              hashes equal the values given with --expect-*-sha256, and unless api/, eval/, packages/ and the lock files
              are committed and clean (the result records the commit).
  Layers      flat   = the dense and BM25 retrievers fused (api/retrieval/arms.py), no graph tools;
              hybrid = dense, BM25 and graph retrieval, plus the Graph agent's deterministic tools (path or
                       neighbourhood, and align_documents) run on the question, which is what a real turn does.
              The Graph agent is run on EVERY question of the hybrid layer, whatever the Orchestrator would have routed,
              so the measurement is the availability of the evidence and not the routing.
  Evidence    retrieval and the Graph agent's deterministic tools only. NO Research agent, NO Fact Checker, NO model
              call. The only paid calls are the query embeddings, computed once per question and shared by the layers.
  Admission   the catalog's own `check` functions at the commit the run records, with the caps in the templates' fences.
              No threshold is tuned after the results are seen. The answer component (`CitedSummary`) needs a Research
              answer, which this study does not produce, so its precondition is approximated by "retrieval returned at
              least one passage"; it is reported for completeness and is not a finding.
  Outputs     per question and layer: the components admitted and, for each refusal, its reason code; per layer: the
              admission count and rate per component and the set X(layer) realised on at least one question; and the
              entity-resolution hit rate per question beside it (the paper's stated ceiling on the graph signal).
  Invariants  `flat` admits only `CitedSummary` and `SourceList` on every question (exit 3 if not); the only ledger
              entries the run adds are `embed` entries (exit 3 if not).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.agents.graph_agent import GRAPH_AGENT
from api.agents.state import TurnContext
from api.container import build_container
from api.core.budget import TokenBudget
from api.core.logging import configure_logging
from api.core.settings import Settings, load_settings
from api.genui.catalog import CATALOG, ComposerEvidence, alignment_grid, concept_path, graph_edges
from api.ingestion.embed import CachingEmbedder
from api.retrieval.arms import ARMS
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever
from api.stores.doc_store import Document
from api.stores.preflight import check_corpus_parity
from eval import frozen
from eval.run_ablation import (
    RunInvalid,
    chunks_sha256,
    git_state,
    load_questions,
    require_expected_hashes,
    resolution_record,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ("flat", "hybrid")
FLAT_ADMITS = frozenset({"CitedSummary", "SourceList"})
"""The only components flat retrieval can admit: it supplies passages and documents, and no entities or relations."""
STUDY_STAMP = {
    "layers": {layer: sorted(ARMS[layer]) for layer in LAYERS},
    "graph_agent_run_on_every_question": True,
    "research_agent": False,
    "fact_checker": False,
    "model_calls": 0,
    "answer_component_proxy": "retrieval returned at least one passage",
}


# ── admission (pure) ──────────────────────────────────────────────────────────


def evidence_for(
    layer: str,
    passages: int,
    graph_payload: dict[str, Any] | None,
    documents: tuple[Document, ...],
    chunk_counts: dict[str, int],
) -> ComposerEvidence:
    """The evidence the Composer would have for this question in this layer. Flat has no graph payload, whatever was
    computed: flat retrieval supplies no entities or relations."""
    answer = {"segments": [{"text": "retrieved", "citationIds": []}], "citations": []} if passages else None
    return ComposerEvidence(
        answer=answer,
        graph=graph_payload if layer == "hybrid" else None,
        documents=documents,
        intent="study",
        chunk_counts=chunk_counts,
    )


def detail(name: str, evidence: ComposerEvidence) -> dict[str, int]:
    """Counts that say how much of a component was available (not a quality measure)."""
    if name == "GraphView":
        return {"drawable_edges": len(graph_edges(evidence.graph))}
    if name == "ComparisonGrid":
        docs, dims, cells = alignment_grid(evidence.graph)
        return {"documents": len(docs), "entities": len(dims), "cells": len(cells)}
    if name == "ConceptMap":
        steps, _ = concept_path(evidence.graph)
        return {"hops": len(steps)}
    if name == "SourceList":
        return {"ready_documents": sum(d.status == "ready" for d in evidence.documents)}
    return {}


def admission(evidence: ComposerEvidence) -> dict[str, dict[str, Any]]:
    """For every catalog component: whether its precondition holds on this evidence, and the reasons if not."""
    out: dict[str, dict[str, Any]] = {}
    for name, template in CATALOG.items():
        result = template.check(evidence)
        out[name] = {"admitted": result.satisfied, "reasons": list(result.reasons), "detail": detail(name, evidence)}
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Admission counts and rates per component and layer, the realised sets X(layer), and the resolution rates."""
    questions = len(rows)
    per_layer: dict[str, Any] = {}
    realised: dict[str, set[str]] = {}
    for layer in LAYERS:
        components: dict[str, Any] = {}
        for name in CATALOG:
            admitted = [r for r in rows if r["layers"][layer]["admission"][name]["admitted"]]
            refusals = Counter(
                reason
                for r in rows
                if not r["layers"][layer]["admission"][name]["admitted"]
                for reason in r["layers"][layer]["admission"][name]["reasons"]
            )
            components[name] = {
                "admitted": len(admitted),
                "rate": round(len(admitted) / questions, 4) if questions else None,
                "refusal_reasons": dict(sorted(refusals.items())),
            }
        realised[layer] = {name for name, c in components.items() if c["admitted"] > 0}
        per_layer[layer] = {"questions": questions, "components": components, "X": sorted(realised[layer])}
    hits = [r["layers"]["hybrid"]["resolution"]["hit_rate"] for r in rows if r["layers"]["hybrid"]["resolution"]]
    flat_graph = sum(
        1
        for r in rows
        for name, a in r["layers"]["flat"]["admission"].items()
        if a["admitted"] and name not in FLAT_ADMITS
    )
    return {
        "per_layer": per_layer,
        "hybrid_only": sorted(realised["hybrid"] - realised["flat"]),
        "flat_not_in_hybrid": sorted(realised["flat"] - realised["hybrid"]),
        "flat_graph_components_admitted": flat_graph,
        "entity_resolution": {
            "mean_hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
            "questions_with_no_entity": sum(
                1 for r in rows if not (r["layers"]["hybrid"]["resolution"] or {}).get("entities")
            ),
        },
    }


# ── the run ───────────────────────────────────────────────────────────────────


def require_clean(allow_dirty: bool) -> dict[str, Any]:
    """The result must trace to committed code: refuse an uncommitted api/, eval/, packages/ or lock file."""
    state = git_state()
    if not allow_dirty and (state["commit"] is None or state["dirty"] is not False):
        raise RunInvalid(
            f"the study needs a committed, clean tree so the result names the code it ran on "
            f"(commit {state['commit']}, changed: {state['changed_files']}); commit first"
        )
    return state


async def _never_called(_: str):  # the study runs no retrieval through the Composer's context
    raise AssertionError("the study's Graph agent context must not retrieve")


def write_results(out: dict[str, Any], results_dir: Path, started: datetime, label: str) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}-{label}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return path


async def run(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    base = load_settings()
    live = "live" in (base.arcana_llm_mode, base.arcana_embed_mode)
    if live and not args.allow_paid:
        raise RunInvalid("live (paid) mode is configured; pass --allow-paid to run (it pays only for query embeddings)")
    data_dir = (
        Path(args.data_dir)
        if args.data_dir
        else ROOT / "data" / f"eval-{base.arcana_llm_mode}-{base.arcana_embed_mode}"
    )
    settings: Settings = base.model_copy(update={"arcana_data_dir": data_dir})
    configure_logging("WARNING")

    questions_path, manifest_path, gold_dir = Path(args.questions_file), Path(args.manifest), Path(args.gold_dir)
    questions = load_questions(questions_path)
    if not args.allow_unfrozen:
        drift = frozen.check_frozen(questions_path, manifest_path, gold_dir, [q["id"] for q in questions])
        if drift:
            raise RunInvalid("the frozen benchmark assets changed: " + "; ".join(drift))
    code = require_clean(args.allow_dirty)
    if not args.allow_unpinned and not (
        args.expect_graph_sha256 and args.expect_vectors_sha256 and args.expect_chunks_sha256
    ):
        raise RunInvalid(
            "pass --expect-graph-sha256, --expect-vectors-sha256 and --expect-chunks-sha256 (the study measures one ingestion)"
        )

    if not (data_dir / "graph.json").exists() or not (data_dir / "vectors.npz").exists():
        raise RunInvalid(f"no stores in {data_dir}: the study measures an existing ingestion and never ingests")
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
    require_expected_hashes(
        store_hashes,
        {
            "graph_sha256": args.expect_graph_sha256,
            "vectors_sha256": args.expect_vectors_sha256,
            "chunks_sha256": args.expect_chunks_sha256,
        },
    )

    documents = tuple(container.docs.list_documents())
    chunk_counts = {d.id: len(container.docs.chunks_for_document(d.id)) for d in documents if d.status == "ready"}
    cached = CachingEmbedder(container.embedder)
    retrievers = {
        "dense": DenseRetriever(vectors=container.vectors, docs=container.docs, embedder=cached),
        "sparse": SparseRetriever(docs=container.docs),
        "graph": GraphRetriever(graph=container.graph, docs=container.docs),
    }
    ledger_before = {"total_usd": container.ledger.month_total(), "rows": len(container.ledger.rows())}

    rows: list[dict[str, Any]] = []
    for q in questions:
        text = q["question"].strip()
        layers: dict[str, Any] = {}
        graph_payload: dict[str, Any] | None = None
        for layer in LAYERS:
            result = await hybrid_retrieve(text, **retrievers, signals=ARMS[layer])
            if result.failed:
                raise RunInvalid(f"a signal failed on {q['id']} ({layer}): {list(result.failed)}")
            if layer == "hybrid":
                ctx = TurnContext(
                    docs=container.docs,
                    retrieve=_never_called,  # type: ignore[arg-type]
                    llm=container.llm,
                    budget=TokenBudget(),
                    block_id="study",
                    graph=container.graph,
                )
                graph_payload = (await GRAPH_AGENT.run(text, ctx)).payload
            layers[layer] = {
                "retrieved": len(result.chunks),
                "resolution": resolution_record(result),
                "admission": admission(evidence_for(layer, len(result.chunks), graph_payload, documents, chunk_counts)),
            }
        rows.append({"question_id": q["id"], "category": q["category"], "layers": layers})

    ledger_after = container.ledger.rows()
    new_entries = ledger_after[ledger_before["rows"] :]
    ledger = {
        "before_usd": ledger_before["total_usd"],
        "after_usd": container.ledger.month_total(),
        "delta_usd": round(container.ledger.month_total() - ledger_before["total_usd"], 6),
        "new_entries": len(new_entries),
        "new_purposes": sorted({e.get("purpose", "?") for e in new_entries}),
    }
    started = datetime.now(UTC)
    out = {
        "run": {
            "timestamp": started.isoformat(),
            "label": args.label,
            "mode": {"llm": settings.arcana_llm_mode, "embed": settings.arcana_embed_mode},
            "code": code,
            "study": STUDY_STAMP,
            "templates": {name: {"version": t.version, "caps": t.fences.caps} for name, t in CATALOG.items()},
            "hashes": {"questions_sha256": sha256_file(questions_path), **store_hashes},
            "query_embeddings_computed": cached.inner_calls,
            "ledger": ledger,
            "questions": [q["id"] for q in questions],
            "limits": (
                "An admission rate over 20 questions on one ingestion. Not a quality score; not a proof of the paper's "
                "claim (X(flat) being inside X(hybrid) holds by how the preconditions are written); nothing about "
                "questions unlike these 20. The answer component's admission is a proxy (retrieval returned a passage)."
            ),
        },
        "results": rows,
        "summary": summarise(rows),
    }
    return write_results(out, Path(args.out), started, args.label), out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    p.add_argument("--manifest", default=str(ROOT / "eval" / "corpus" / "MANIFEST.json"))
    p.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    p.add_argument("--data-dir", help="store location (default: data/eval-<llm>-<embed>)")
    p.add_argument("--label", default="bound")
    p.add_argument(
        "--allow-paid", action="store_true", help="permit live providers (the study pays only for query embeddings)"
    )
    p.add_argument(
        "--allow-dirty", action="store_true", help="permit an uncommitted tree (the result records it; tests only)"
    )
    p.add_argument("--allow-unpinned", action="store_true", help="run without --expect-* hashes (tests only)")
    p.add_argument("--allow-unfrozen", action="store_true", help="skip the frozen-asset check (tests only)")
    p.add_argument("--expect-graph-sha256")
    p.add_argument("--expect-vectors-sha256")
    p.add_argument("--expect-chunks-sha256")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path, out = asyncio.run(run(args))
    except RunInvalid as exc:
        print(f"RUN REFUSED: {exc}", file=sys.stderr)
        return 2
    summary = out["summary"]
    print(f"wrote {path}")
    for layer, s in summary["per_layer"].items():
        admitted = ", ".join(f"{n}={c['admitted']}/{s['questions']}" for n, c in s["components"].items())
        print(f"  {layer:6} X={s['X']}  {admitted}")
    print(
        f"  hybrid only: {summary['hybrid_only']}   mean entity-resolution hit rate: {summary['entity_resolution']['mean_hit_rate']}"
    )
    print(f"  ledger delta ${out['run']['ledger']['delta_usd']:.6f}, purposes {out['run']['ledger']['new_purposes']}")
    if summary["flat_graph_components_admitted"]:
        print("INVARIANT BROKEN: flat retrieval admitted a graph component.", file=sys.stderr)
        return 3
    if set(out["run"]["ledger"]["new_purposes"]) - {"embed"}:
        print("INVARIANT BROKEN: the study spent on something other than embeddings.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
