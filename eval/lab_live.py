"""P4 V9: does a live model write a function the verifier accepts? One call per attempt through the LLM seam (spend booked, cap applied).

    uv run python eval/lab_live.py --data-dir data/eval-live-live --repeats 2 --max-usd 0.15 --allow-paid

Protocol (written before the run, constraint 9). For each of the four contracts and each repeat, the live generator (`api/labs/live_generator.py`,
prompt `live-lab-1`) is asked once, with no retry and no feedback from the verifier, and its source goes through `compose_lab`: the evidence
precondition, the AST checker, the verifier (reference cases, properties, the full slider grid, seeded fuzz), the store. Measured: the share of
first attempts the verifier accepts, the stage and reason of each refusal, tokens, model and cost. Nothing is tuned between attempts. The labs
are built into a throwaway store, not the product's `labs.db`. The result is descriptive (4 contracts, a few attempts): it says whether the gate
admits what a real model writes, not how good the model is.

Cost: a few cents (about 600 tokens in and 150 out per call at the standard tier); `--max-usd` stops the run when the month's total has grown by
more than that.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anyio import to_thread

from api.agents.compose import compose_lab
from api.container import build_container
from api.core.logging import configure_logging
from api.core.settings import load_settings
from api.labs.contract import CONTRACTS
from api.labs.live_generator import LIVE_PROMPT_VERSION, LiveLabGenerator
from api.labs.store import SqliteLabStore
from eval.run_ablation import RunInvalid, require_clean_code

ROOT = Path(__file__).resolve().parents[1]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    base = load_settings()
    if base.arcana_llm_mode != "live":
        raise RunInvalid("this measures a live model: set ARCANA_LLM_MODE=live")
    if not args.allow_paid:
        raise RunInvalid("live (paid) mode: pass --allow-paid")
    code = require_clean_code(True, False)
    data_dir = Path(args.data_dir)
    settings = base.model_copy(update={"arcana_data_dir": data_dir})
    configure_logging("WARNING")
    container = build_container(settings)
    before = container.ledger.month_total()
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        labs = SqliteLabStore(Path(tmp) / "labs.db")
        for contract_id in CONTRACTS:
            for attempt in range(1, args.repeats + 1):
                spent = container.ledger.month_total() - before
                if spent > args.max_usd:
                    raise RunInvalid(f"stopped: spent {spent:.4f} of the {args.max_usd} ceiling")
                generator = LiveLabGenerator(container.llm, container.docs)
                ledger_before = container.ledger.rows()
                n_before = len(ledger_before)
                _, blocks = await to_thread.run_sync(compose_lab, container.docs, labs, generator, contract_id)
                block = blocks[0]
                new = container.ledger.rows()[n_before:]
                row: dict[str, Any] = {
                    "contract": contract_id,
                    "attempt": attempt,
                    "status": block.meta.status,
                    "calls": len(new),
                    "tokens_in": sum(r["tokens_in"] for r in new),
                    "tokens_out": sum(r["tokens_out"] for r in new),
                    "cost_usd": round(sum(r["cost_usd"] for r in new), 6),
                    "models": sorted({f"{r['provider']}:{r['model']}" for r in new}),
                }
                error = getattr(block.meta, "error", None)
                if error is not None:
                    row["stage"] = error.issues[0].path if error.issues else None
                    row["reason"] = error.message[:240]
                rows.append(row)
                print(f"  {contract_id} #{attempt}: {row['status']} {row.get('stage', '')} {row.get('reason', '')[:100]}")
        rejected = labs.rejected()
    result = {
        "run": {
            "timestamp": datetime.now(UTC).isoformat(),
            "code": code,
            "prompt_version": LIVE_PROMPT_VERSION,
            "mode": {"llm": base.arcana_llm_mode},
            "repeats": args.repeats,
        },
        "attempts": rows,
        "accepted": sum(r["status"] == "ready" for r in rows),
        "total": len(rows),
        "spent_usd": round(container.ledger.month_total() - before, 6),
        "rejected_records": rejected,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--max-usd", type=float, default=0.15)
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
    path = out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-lab-live.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{result['accepted']} of {result['total']} first attempts accepted; spent ${result['spent_usd']}; wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
