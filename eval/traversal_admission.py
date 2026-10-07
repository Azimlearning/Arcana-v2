"""How often a TraversalView is admitted, and what the search followed, on the frozen questions (P2c T3). Free.

    uv run python eval/traversal_admission.py --data-dir data/eval-live-live [--label traversal-admission]

For each of the frozen 20 questions it runs the Graph agent's deterministic traversal over the stores (no retrieval
embedding, no model call, no network) and records: the concepts the question resolved to, the edges followed, how many
the view would show, the passages reached and how each was reached, and whether the TraversalView precondition holds
(with its closed reason if not). It is a measure of availability and of what the graph signal does on these questions.
It is not a quality score and says nothing about questions unlike these 20.

PROTOCOL (fixed before the run): the 20 questions of eval/questions.yaml, unchanged; the stores of the given data
directory (the run records their hashes and is refused if they differ from the pinned values given with --expect-*);
the catalog's own `check` at the recorded commit, with the fences' caps; a clean committed tree.
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
from api.core.budget import TokenBudget
from api.genui.catalog import TRAVERSAL_VIEW, ComposerEvidence
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from eval.run_ablation import ROOT, chunks_sha256, git_state, load_questions, sha256_file


async def _never(_: str):  # the study's context never retrieves
    raise AssertionError("the traversal study must not retrieve")


async def measure_question(text: str, graph: NetworkXGraphStore, docs: SqliteDocStore) -> dict[str, Any]:
    ctx = TurnContext(docs=docs, retrieve=_never, llm=None, budget=TokenBudget(), block_id="study", graph=graph)  # type: ignore[arg-type]
    payload = (await GRAPH_AGENT.run(text, ctx)).payload
    traversal = payload.get("traversal") or {}
    check = TRAVERSAL_VIEW.check(
        ComposerEvidence(answer=None, graph=payload, documents=(), intent="study", chunk_counts={})
    )
    reached = traversal.get("reached") or []
    return {
        "admitted": check.satisfied,
        "reasons": list(check.reasons),
        "seeds": [{"label": s["label"], "match": s["match"]} for s in traversal.get("seeds") or []],
        "steps_followed": int(traversal.get("steps_total") or 0),
        "steps_shown": len(traversal.get("steps") or []),
        "steps_left_out": int(traversal.get("left_out") or 0),
        "reached": len(reached),
        "reached_via": dict(Counter(r["via"] for r in reached)),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = [r for r in rows if r["admitted"]]
    refusals = Counter(reason for r in rows if not r["admitted"] for reason in r["reasons"])
    via = Counter()
    for r in rows:
        via.update(r["reached_via"])
    return {
        "questions": len(rows),
        "admitted": len(admitted),
        "rate": round(len(admitted) / len(rows), 4) if rows else None,
        "refusal_reasons": dict(sorted(refusals.items())),
        "seeds_per_question": sorted(len(r["seeds"]) for r in rows),
        "steps_followed_per_question": sorted(r["steps_followed"] for r in rows),
        "steps_shown_per_question": sorted(r["steps_shown"] for r in rows),
        "reached_via_total": dict(via),
        "approximate_seeds": sum(1 for r in rows for s in r["seeds"] if s["match"] == "approximate"),
        "seeds_total": sum(len(r["seeds"]) for r in rows),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    data_dir = Path(args.data_dir)
    graph = NetworkXGraphStore(data_dir / "graph.json")
    docs = SqliteDocStore(make_engine(data_dir / "arcana.db"))
    hashes = {
        "graph_sha256": sha256_file(data_dir / "graph.json"),
        "chunks_sha256": chunks_sha256(docs.all_chunks()),
    }
    for key, expected in (("graph_sha256", args.expect_graph_sha256), ("chunks_sha256", args.expect_chunks_sha256)):
        if expected and hashes[key] != expected:
            raise SystemExit(f"{key} differs from the pinned value ({hashes[key]} != {expected})")
    questions = load_questions(Path(args.questions_file))
    rows = []
    for q in questions:
        rows.append(
            {
                "question_id": q["id"],
                "category": q["category"],
                **await measure_question(q["question"].strip(), graph, docs),
            }
        )
    started = datetime.now(UTC)
    result = {
        "run": {
            "started": started.isoformat(),
            "label": args.label,
            "code": git_state(),
            "data_dir": str(data_dir),
            "hashes": hashes,
            "model_calls": 0,
            "network_calls": 0,
            "limits": "Availability and what the graph signal does on 20 questions of one corpus; not a quality score.",
        },
        "summary": summarise(rows),
        "results": rows,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="TraversalView admission and traversal sizes on the frozen questions (free)."
    )
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    ap.add_argument("--label", default="traversal-admission")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results"))
    ap.add_argument("--expect-graph-sha256", default=None)
    ap.add_argument("--expect-chunks-sha256", default=None)
    ap.add_argument("--allow-dirty", action="store_true", help="for tests only: a result should name committed code")
    args = ap.parse_args(argv)
    state = git_state()
    if not args.allow_dirty and (state["commit"] is None or state["dirty"] is not False):
        print(f"commit first: the result must name the code it ran on ({state['changed_files']})", file=sys.stderr)
        return 2
    result = asyncio.run(run(args))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result['run']['started'][:19].replace('-', '').replace(':', '')}Z-{args.label}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    s = result["summary"]
    print(f"wrote {path}")
    print(f"admitted {s['admitted']} of {s['questions']}; refusals {s['refusal_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
