"""P5 S6: does the whole system, with a real model, answer from the documents and say nothing it cannot cite?

    uv run python eval/grounding_live.py --data-dir data/eval-live-live --max-usd 1.5 --allow-paid

PROTOCOL (written 2026-10-15, before the first run; constraint 9)
-----------------------------------------------------------------
Turns: every question of the frozen set (20, `q-single-01` the control that has no answer in the corpus) and of the declared extension (19),
each as one ordinary chat turn through the real graph with the real roster (Orchestrator, Graph where the intent asks, Research, Fact Checker,
Composer) and live providers; then 8 `write` turns on the fixed topics below (Studio and the Fact Checker's draft checks). One attempt per
turn, no retry, no prompt change between turns. The corpus and stores are the baseline's (hashes checked by the tool as the other live tools do).

Measured WITHOUT a model judge:
  - verbatim:     every citation's quote is a span of its stored chunk (the validator guarantees it; this re-checks the shipped block);
  - citation precision / gold recall: a cited chunk is relevant when it covers a gold passage under the frozen 30 percent shingle rule
                  (`eval/metrics.py`); precision is relevant cited chunks over cited chunks, recall the gold passages covered by the cited chunks;
  - answer rate:  the share of answerable questions whose terminal block is `ready` or `partial`; and for the control, the share that is `empty`
                  (an answer to a question the corpus cannot answer is a failure of grounding, reported as such);
  - what the Fact Checker removed: segments in and kept, quotes the model chose against quotes the server replaced, judged by model and by rule;
  - drafts:       per write turn, whether a draft passed the checker, its sections and passages in and kept, the documents cited, and passages
                  reported as close to their source.
Not measured: answer quality or faithfulness by a model (constraint 9: never primary); no pairing against another system.

COST: about 47 turns at a few cents each; `--max-usd` stops the run when the month's total has grown by more than that (the ledger is on every
paid call). Nothing is paid if `--allow-paid` is not given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.agents.graph import build_turn_graph
from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.container import build_container
from api.core.budget import TokenBudget
from api.core.logging import configure_logging
from api.core.settings import load_settings
from eval import metrics
from eval.run_ablation import RunInvalid, load_questions, require_clean_code

ROOT = Path(__file__).resolve().parents[1]
WRITE_TOPICS = (
    "dense retrieval versus sparse retrieval",
    "knowledge graphs in retrieval-augmented generation",
    "how retrieval-augmented generation reduces hallucination",
    "evaluating retrieval-augmented generation",
    "chunking strategies for retrieval",
    "query rewriting and expansion",
    "multi-hop question answering",
    "hybrid retrieval with graphs and vectors",
)


def _norm(text: str) -> str:
    return " ".join(text.split())


async def run_turn(graph: Any, container: Any, question: str) -> tuple[dict[str, Any], Any]:
    ctx = TurnContext(
        docs=container.docs,
        retrieve=container.retrieve,
        llm=container.llm,
        budget=TokenBudget(),
        block_id=f"grounding-{uuid.uuid4().hex[:10]}",
        roster=default_roster(),
        graph=container.graph,
        vault=None,
        learner=None,
    )
    before = container.ledger.month_total()
    started = time.perf_counter()
    state = await graph.ainvoke({"question": question}, context=ctx)
    composition = state["composition"]
    primary = composition.primary
    row: dict[str, Any] = {
        "intent": ctx.intent,
        "status": primary.meta.status,
        "latency_s": round(time.perf_counter() - started, 2),
        "tokens": ctx.budget.used,
        "spent_usd": round(container.ledger.month_total() - before, 6),
        "blocks": [b.type for b in composition.blocks],
        "steps": [(s.agent, s.status, s.note) for s in (ctx.steps[i] for i in sorted(ctx.steps))],
    }
    return row, (ctx, composition)


def citation_row(composition: Any, container: Any, gold: metrics.Gold | None) -> dict[str, Any]:
    primary = composition.primary
    citations = list(primary.data.citations) if primary.meta.status in ("ready", "partial") else []
    chunk_ids = sorted({c.chunkId for c in citations})
    stored = container.docs.get_chunks(chunk_ids)
    verbatim = [_norm(c.quote) in _norm(stored[c.chunkId].text) for c in citations if c.chunkId in stored]
    out: dict[str, Any] = {
        "segments": len(primary.data.segments) if citations else 0,
        "citations": len(citations),
        "cited_chunks": len(chunk_ids),
        "cited_documents": len({c.docId for c in citations}),
        "verbatim": f"{sum(verbatim)}/{len(verbatim)}",
    }
    if gold is not None and gold.passages and chunk_ids:
        texts = [stored[c].text for c in chunk_ids if c in stored]
        relevant = [t for t in texts if metrics.is_relevant(t, gold)]
        covered: set[int] = set()
        for t in texts:
            covered |= metrics.covered_passages(t, gold)
        out["citation_precision"] = round(len(relevant) / len(texts), 4)
        out["gold_recall"] = round(len(covered) / len(gold.passages), 4)
    return out


def checker_row(ctx: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    research = ctx.results.get("research")
    if research is not None:
        out["research"] = research.payload.get("stats", {})
    checker = ctx.results.get("fact_checker")
    if checker is not None:
        out["answer_check"] = checker.payload.get("report", {})
        if "draft_report" in checker.payload:
            out["draft_check"] = checker.payload["draft_report"]
        out["checker_note"] = checker.note
    return out


def draft_row(composition: Any) -> dict[str, Any]:
    draft = next((b for b in composition.blocks if b.type == "WritingDraft"), None)
    if draft is None:
        return {"draft": None}
    d = draft.data
    return {
        "draft": draft.meta.status,
        "sections": len(d.sections),
        "passages": sum(len(s.segments) for s in d.sections),
        "citations": len(d.citations),
        "documents": len({c.docId for c in d.citations}),
        "references": len(d.bibliography),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    base = load_settings()
    if base.arcana_llm_mode != "live":
        raise RunInvalid("this measures a live model: set ARCANA_LLM_MODE=live")
    if not args.allow_paid:
        raise RunInvalid("live (paid) mode: pass --allow-paid")
    code = require_clean_code(True, False)
    settings = base.model_copy(update={"arcana_data_dir": Path(args.data_dir)})
    configure_logging("WARNING")
    container = build_container(settings)
    graph = build_turn_graph()
    start_total = container.ledger.month_total()
    remaining = container.llm.remaining_usd()
    if remaining is not None and remaining < args.max_usd + 0.15:
        raise RunInvalid(f"the cap leaves ${remaining:.2f}: not enough for a ceiling of ${args.max_usd} and one turn of overshoot")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240  (a one-off tool, not a server path)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rows_path = out_dir / f"{stamp}-grounding-live.rows.jsonl"  # every paid-for row is on disk as soon as it exists
    stopped: str | None = None

    def keep(kind: str, row: dict[str, Any]) -> None:
        with rows_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, **row}, default=str) + chr(10))

    questions: list[dict[str, Any]] = []
    for qfile, gdir in (("questions.yaml", "gold"), ("questions_ext.yaml", "gold_ext")):
        for q in load_questions(ROOT / "eval" / qfile):
            questions.append({**q, "gold": metrics.load_gold(ROOT / "eval" / gdir, q["id"])})
    if args.limit:
        questions = questions[: args.limit]
    rows: list[dict[str, Any]] = []
    for q in questions:
        spent = container.ledger.month_total() - start_total
        if spent > args.max_usd:
            stopped = f"stopped at the ceiling: spent {spent:.4f} of {args.max_usd}"
            break
        row, (ctx, composition) = await run_turn(graph, container, q["question"])
        row.update({"id": q["id"], "category": q["category"], "answerable": bool(q["gold"] and q["gold"].passages)})
        row.update(citation_row(composition, container, q["gold"]))
        row.update(checker_row(ctx))
        rows.append(row)
        keep("question", row)
        if any(note in ("spend_cap_exceeded", "budget_exhausted") for _, _, note in row["steps"]):
            stopped = "stopped: the spend seam refused a call"
            break
        print(f"  {q['id']}: {row['intent']} {row['status']} cites={row['citations']} ${row['spent_usd']}")
    writes: list[dict[str, Any]] = []
    topics = WRITE_TOPICS[: args.write_topics]
    for topic in topics:
        spent = container.ledger.month_total() - start_total
        if stopped is not None or spent > args.max_usd:
            stopped = stopped or f"stopped at the ceiling: spent {spent:.4f} of {args.max_usd}"
            break
        row, (ctx, composition) = await run_turn(graph, container, f"Write an outline on {topic}")
        row.update({"topic": topic})
        row.update(draft_row(composition))
        row.update(checker_row(ctx))
        writes.append(row)
        keep("write", row)
        print(f"  write '{topic}': {row['intent']} draft={row['draft']} ${row['spent_usd']}")

    answerable = [r for r in rows if r["answerable"]]
    control = [r for r in rows if not r["answerable"]]
    answered = [r for r in answerable if r["status"] in ("ready", "partial")]
    precisions = [r["citation_precision"] for r in answered if "citation_precision" in r]
    recalls = [r["gold_recall"] for r in answered if "gold_recall" in r]
    summary = {
        "answerable_turns": len(answerable),
        "answered": len(answered),
        "answer_rate": round(len(answered) / len(answerable), 4) if answerable else None,
        "control_turns": len(control),
        "control_empty": sum(r["status"] == "empty" for r in control),
        "control_answered": sum(r["status"] in ("ready", "partial") for r in control),
        "verbatim_all": all(r["verbatim"].split("/")[0] == r["verbatim"].split("/")[1] for r in rows if r["citations"]),
        "mean_citation_precision": round(sum(precisions) / len(precisions), 4) if precisions else None,
        "mean_gold_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "drafts_shown": sum(1 for w in writes if w.get("draft") in ("ready", "partial")),
        "write_turns": len(writes),
    }
    return {
        "run": {
            "timestamp": datetime.now(UTC).isoformat(),
            "code": code,
            "mode": {"llm": base.arcana_llm_mode, "embed": base.arcana_embed_mode},
            "turns": len(rows) + len(writes),
        },
        "summary": summary,
        "stopped": stopped,
        "rows_file": rows_path.name,
        "turns": rows,
        "writes": writes,
        "spent_usd": round(container.ledger.month_total() - start_total, 6),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--max-usd", type=float, default=1.5)
    p.add_argument("--limit", type=int, default=0, help="only the first N questions (a smoke run)")
    p.add_argument("--write-topics", type=int, default=len(WRITE_TOPICS))
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    p.add_argument("--allow-paid", action="store_true")
    args = p.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except RunInvalid as exc:
        print(f"RUN REFUSED: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result['rows_file'].split('.rows')[0]}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"spent ${result['spent_usd']}; wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
