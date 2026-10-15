"""D-43 V2: do the new writing kinds (literature review, abstract, audio-overview script) hold with a real model?

    uv run python eval/studio_kinds_live.py --data-dir data/eval-live-live --max-usd 0.4 --allow-paid

PROTOCOL (written 2026-10-15, before the run; constraint 9)
-----------------------------------------------------------
Turns: each of the three kinds on each of two fixed topics (below), as one ordinary chat turn through the real graph with the real roster
and live providers, one attempt each, no retry and no prompt change. The corpus and stores are the baseline's, as in `grounding_live.py`.

Measured WITHOUT a model judge, per turn: whether a draft was shown (`ready` or `partial`); its kind; sections and passages; the citations and
whether every quote is a verbatim span of its stored chunk; the documents cited and references built; for a script, whether every line has a
speaker, how many lines each voice has and whether the voices alternate; and what the Fact Checker removed (passages in and kept) and
reported as close to their source.
Not measured: the quality of the writing (constraint 9: no model-judged score is primary). Nothing is paid without `--allow-paid`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.agents.graph import build_turn_graph
from api.container import build_container
from api.core.logging import configure_logging
from api.core.settings import load_settings
from eval.grounding_live import checker_row, run_turn
from eval.run_ablation import RunInvalid, require_clean_code

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ("dense retrieval", "graph-based retrieval augmented generation")
REQUESTS = (
    ("outline", "Write an outline on {t}"),
    ("literature_review", "Write a literature review of {t}"),
    ("abstract", "Write an abstract on {t}"),
    ("script", "Make an audio overview of {t}"),
)


def kind_row(composition: Any, container: Any) -> dict[str, Any]:
    draft = next((b for b in composition.blocks if b.type == "WritingDraft"), None)
    if draft is None:
        return {"draft": None}
    d = draft.data
    stored = container.docs.get_chunks(sorted({c.chunkId for c in d.citations}))
    norm = lambda s: " ".join(s.split())  # noqa: E731
    verbatim = [norm(c.quote) in norm(stored[c.chunkId].text) for c in d.citations if c.chunkId in stored]
    lines = [seg for sec in d.sections for seg in sec.segments]
    speakers = [seg.speaker for seg in lines]
    row: dict[str, Any] = {
        "draft": draft.meta.status,
        "kind": d.kind,
        "sections": len(d.sections),
        "passages": len(lines),
        "citations": len(d.citations),
        "verbatim": f"{sum(verbatim)}/{len(verbatim)}",
        "documents": len({c.docId for c in d.citations}),
        "references": len(d.bibliography),
    }
    if d.kind == "script":
        row["every_line_has_a_speaker"] = all(s in ("host", "guest") for s in speakers)
        row["host_lines"] = speakers.count("host")
        row["guest_lines"] = speakers.count("guest")
        row["alternates"] = all(a != b for a, b in pairwise(speakers))
    return row


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
    start = container.ledger.month_total()
    remaining = container.llm.remaining_usd()
    if remaining is not None and remaining < args.max_usd + 0.1:
        raise RunInvalid(f"the cap leaves ${remaining:.2f}: not enough for a ceiling of ${args.max_usd}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240  (a one-off tool, not a server path)
    rows: list[dict[str, Any]] = []
    stopped: str | None = None
    for topic in args.topic or TOPICS:
        for kind, template in REQUESTS:
            if container.ledger.month_total() - start > args.max_usd:
                stopped = f"stopped at the ceiling of {args.max_usd}"
                break
            row, (ctx, composition) = await run_turn(graph, container, template.format(t=topic))
            row.update({"topic": topic, "asked_kind": kind})
            row.update(kind_row(composition, container))
            row.update(checker_row(ctx))
            rows.append(row)
            print(f"  {kind} on '{topic}': draft={row['draft']} kind={row.get('kind')} ${row['spent_usd']}")
        if stopped:
            break
    result = {
        "run": {"timestamp": datetime.now(UTC).isoformat(), "code": code, "mode": {"llm": base.arcana_llm_mode, "embed": base.arcana_embed_mode}},
        "stopped": stopped,
        "turns": rows,
        "spent_usd": round(container.ledger.month_total() - start, 6),
    }
    path = out_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-studio-kinds-live.json"
    path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {path.name}; spent ${result['spent_usd']}")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--max-usd", type=float, default=0.4)
    p.add_argument("--topic", action="append", help="a topic to write about (repeatable); the fixed topics by default")
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    p.add_argument("--allow-paid", action="store_true")
    args = p.parse_args(argv)
    try:
        asyncio.run(run(args))
    except RunInvalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
