"""Write the detailed record of a live corpus ingestion: totals, per-paper cost, per-call statistics, and a CSV
of every ledger row with what it was attributed to.

    uv run python eval/report_ingestion.py --out-dir eval/results --label 2026-10-06-live-ingestion

Reads only local files (the spend ledger and the ingestion report beside the stores); makes no paid call.

How rows are attributed. The pipeline ingests papers one at a time, and within a paper it embeds all chunks
(one or more batches) and then makes exactly one extraction call per chunk, so a paper's ledger rows are
contiguous: its embedding batches, then `chunks` extraction rows. The papers are walked in the order the
ingestion report lists them. Other rows are labelled by what they are (probes, query embeddings, chat turns,
throwaway measurement extractions). Every block is checked against the report's chunk count; a mismatch stops
the report rather than guessing. A query or probe embedding is told apart from a paper's embedding batch by
size (under 100 tokens).
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.core.settings import Settings
from api.ingestion.extract import EXTRACTION_MAX_TOKENS
from api.ingestion.pipeline import EXTRACTION_CONCURRENCY
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from eval import run_ablation

ROOT = Path(__file__).resolve().parents[1]
SMALL_EMBED_TOKENS = 100


class ReportInvalid(Exception):
    pass


def load_rows(ledger: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(ledger)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute("SELECT * FROM spend_ledger ORDER BY id")]


def _is_paper_embed(r: dict[str, Any]) -> bool:
    return r["purpose"] == "embed" and r["status"] == "ok" and r["tokens_in"] >= SMALL_EMBED_TOKENS


def attribute(rows: list[dict[str, Any]], order: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Label every row. Returns (rows with an `attributed_to` field, per-paper blocks)."""
    labelled = [dict(r, attributed_to=None) for r in rows]
    blocks: list[dict[str, Any]] = []
    i = next((k for k, r in enumerate(labelled) if _is_paper_embed(r)), None)
    if i is None:
        raise ReportInvalid("no paper embedding found in the ledger")
    for paper in order:
        while i < len(labelled) and not _is_paper_embed(labelled[i]):
            i += 1  # chat turns, query embeddings, probes between papers
        embeds = []
        while i < len(labelled) and _is_paper_embed(labelled[i]):
            embeds.append(labelled[i])
            i += 1
        extracts = labelled[i : i + paper["chunks"]]
        if len(extracts) != paper["chunks"] or any(r["purpose"] != "extract" or r["status"] != "ok" for r in extracts):
            raise ReportInvalid(f"{paper['arxiv_id']}: expected {paper['chunks']} extraction rows after its embedding batches")
        i += paper["chunks"]
        for r in embeds + extracts:
            r["attributed_to"] = paper["arxiv_id"]
        blocks.append({"paper": paper, "embeds": embeds, "extracts": extracts})
    for r in labelled:
        if r["attributed_to"] is None:
            label = str({
                "probe": "probe (a few-cent test of a route)",
                "research": "chat turn (research)", "check": "chat turn (judge)", "route": "chat turn (routing)",
                "embed": "embedding outside the ingestion (probe or a query)",
                "extract": "throwaway measurement extraction (not part of the benchmark stores)",
            }.get(r["purpose"], r["purpose"]))
            r["attributed_to"] = label + (" [failed call, no cost]" if r["status"] == "failed" else "")
    return labelled, blocks


def _pct(sorted_values: list[int], q: float) -> int:
    return sorted_values[max(int(len(sorted_values) * q) - 1, 0)] if sorted_values else 0


def paper_summary(block: dict[str, Any]) -> dict[str, Any]:
    paper, ex, em = block["paper"], block["extracts"], block["embeds"]
    outs = sorted(r["tokens_out"] for r in ex)
    cost_ex, cost_em = sum(r["cost_usd"] for r in ex), sum(r["cost_usd"] for r in em)
    stamps = [datetime.fromisoformat(r["ts"]) for r in em + ex]
    return {
        "arxiv_id": paper["arxiv_id"], "doc_id": paper["doc_id"], "chunks": paper["chunks"],
        "nodes": paper.get("nodes"), "edges": paper.get("edges"), "extraction_failures": paper.get("extraction_failures"),
        "embedding_calls": len(em), "embedding_tokens": sum(r["tokens_in"] for r in em), "embedding_cost_usd": round(cost_em, 6),
        "extraction_calls": len(ex), "extraction_tokens_in": sum(r["tokens_in"] for r in ex),
        "extraction_tokens_out": sum(outs), "extraction_cost_usd": round(cost_ex, 6),
        "total_cost_usd": round(cost_ex + cost_em, 6), "cost_per_chunk_usd": round((cost_ex + cost_em) / paper["chunks"], 6),
        "output_tokens": {"mean": round(sum(outs) / len(outs), 1), "median": outs[len(outs) // 2], "p90": _pct(outs, 0.9),
                          "max": outs[-1], "at_limit": sum(o >= EXTRACTION_MAX_TOKENS for o in outs)},
        "wall_seconds": round((max(stamps) - min(stamps)).total_seconds(), 1),
        "ingested_in_this_ledger_order_position": None,
    }


def build_report(ledger: Path, report_path: Path, data_dir: Path, manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = load_rows(ledger)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    titles = {m["arxiv_id"]: m["title"] for m in manifest}
    if len(saved) != len(manifest):
        raise ReportInvalid(f"the ingestion report has {len(saved)} papers; the manifest has {len(manifest)}")
    labelled, blocks = attribute(rows, saved)
    papers = []
    for pos, b in enumerate(blocks, start=1):
        s = paper_summary(b)
        s["ingestion_order"] = pos
        s["title"] = titles[s["arxiv_id"]]
        s.pop("ingested_in_this_ledger_order_position")
        papers.append(s)

    def total(selector) -> dict[str, Any]:
        sel = [r for r in labelled if selector(r)]
        return {"calls": len(sel), "tokens_in": sum(r["tokens_in"] for r in sel), "tokens_out": sum(r["tokens_out"] for r in sel),
                "cost_usd": round(sum(r["cost_usd"] for r in sel), 6)}

    corpus_rows = [r for r in labelled if r["attributed_to"] in titles]
    by_group: dict[str, dict[str, Any]] = {}
    for r in labelled:
        group = r["attributed_to"] if r["attributed_to"] not in titles else "benchmark corpus ingestion"
        g = by_group.setdefault(group, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        g["calls"] += 1
        g["tokens_in"] += r["tokens_in"]
        g["tokens_out"] += r["tokens_out"]
        g["cost_usd"] = round(g["cost_usd"] + r["cost_usd"], 6)

    chunk_total = sum(p["chunks"] for p in papers)
    failures = sum(p["extraction_failures"] or 0 for p in papers)
    ex_cost = sum(p["extraction_cost_usd"] for p in papers)
    em_cost, em_tokens = sum(p["embedding_cost_usd"] for p in papers), sum(p["embedding_tokens"] for p in papers)
    ex_rows = [r for r in corpus_rows if r["purpose"] == "extract"]
    outs = sorted(r["tokens_out"] for r in ex_rows)
    ins = sorted(r["tokens_in"] for r in ex_rows)
    engine = make_engine(data_dir / "arcana.db")
    docs = SqliteDocStore(engine)
    chunks = docs.all_chunks()
    stamps = [datetime.fromisoformat(r["ts"]) for r in corpus_rows]
    settings = Settings(_env_file=".env")  # pyright: ignore[reportCallIssue]
    summary = {
        "label": "live ingestion of the 16-paper benchmark corpus",
        "models": sorted({r["model"] for r in ex_rows}), "providers": sorted({r["provider"] for r in ex_rows}),
        "settings": {"extraction_max_tokens": EXTRACTION_MAX_TOKENS, "extraction_concurrency": EXTRACTION_CONCURRENCY,
                     "monthly_cap_usd": settings.llm_monthly_cap_usd},
        "totals": {
            "papers": len(papers), "chunks": chunk_total, "extraction_calls": len(ex_rows),
            "extraction_failures": failures, "extraction_failure_rate": round(failures / chunk_total, 5),
            "extraction_cost_usd": round(ex_cost, 4), "embedding_cost_usd": round(em_cost, 4),
            "ingestion_cost_usd": round(ex_cost + em_cost, 4), "cost_per_chunk_usd": round((ex_cost + em_cost) / chunk_total, 6),
            "extraction_cost_per_chunk_usd": round(ex_cost / chunk_total, 6),
            "extraction_tokens_in": sum(ins), "extraction_tokens_out": sum(outs), "embedding_tokens": em_tokens,
            "wall_seconds_first_to_last_call": round((max(stamps) - min(stamps)).total_seconds()),
        },
        "extraction_call_distribution": {
            "tokens_in": {"mean": round(sum(ins) / len(ins), 1), "median": ins[len(ins) // 2], "p90": _pct(ins, 0.9), "max": ins[-1]},
            "tokens_out": {"mean": round(sum(outs) / len(outs), 1), "median": outs[len(outs) // 2], "p90": _pct(outs, 0.9),
                           "p99": _pct(outs, 0.99), "max": outs[-1], "at_limit": sum(o >= EXTRACTION_MAX_TOKENS for o in outs)},
            "cost_per_call_usd": {"mean": round(ex_cost / len(ex_rows), 6),
                                  "min": round(min(r["cost_usd"] for r in ex_rows), 6), "max": round(max(r["cost_usd"] for r in ex_rows), 6)},
        },
        "effective_prices": {
            "embedding_usd_per_million_tokens": round(em_cost / em_tokens * 1e6, 4),
            "extraction_blended_usd_per_million_tokens": round(ex_cost / (sum(ins) + sum(outs)) * 1e6, 4),
            "note": "Booked from api/llm/pricing.py (Haiku 4.5 $1/$5 per million in/out; text-embedding-3-large $0.13 assumed); "
                    "the providers' own invoices were not available to this report.",
        },
        "ledger_by_group": by_group,
        "month_total_usd": round(sum(r["cost_usd"] for r in labelled), 4),
        "failed_calls": [{"id": r["id"], "purpose": r["purpose"], "provider": r["provider"], "model": r["model"]}
                         for r in labelled if r["status"] == "failed"],
        "stores": {
            "graph_nodes": None, "chunks": len(chunks),
            "graph_sha256": run_ablation.sha256_file(data_dir / "graph.json"),
            "vectors_sha256": run_ablation.sha256_file(data_dir / "vectors.npz"),
            "chunks_sha256": run_ablation.chunks_sha256(chunks),
        },
        "papers": papers,
    }
    summary["stores"].pop("graph_nodes")
    return summary, labelled


def write_markdown(s: dict[str, Any], path: Path) -> None:
    t, d, e = s["totals"], s["extraction_call_distribution"], s["effective_prices"]
    lines = [
        "# Live ingestion of the benchmark corpus: process and cost record",
        "",
        "Generated by `eval/report_ingestion.py` from the spend ledger and the ingestion report. Every number below is",
        "read back from those local files, not estimated. Raw per-call data is in the CSV beside this file.",
        "",
        "## What was run",
        "",
        f"- {t['papers']} papers ({t['chunks']:,} chunks of about 1,200 characters, 200 overlap) from the pre-registered manifest, ingested once, one paper at a time, in a data directory used by the benchmark (`data/eval-live-live`).",
        f"- Per paper: embed every chunk with OpenAI `text-embedding-3-large` (3,072 dimensions), then one extraction call per chunk with `{', '.join(s['models'])}` through the LLM seam (provider `{', '.join(s['providers'])}`), schema-free entity and relation extraction, {s['settings']['extraction_concurrency']} calls in flight, output limit {s['settings']['extraction_max_tokens']:,} tokens (ADR D-25).",
        f"- Monthly cap `${s['settings']['monthly_cap_usd']}`. The ledger reserved each call's worst case before sending it.",
        "",
        "## Totals",
        "",
        "| | |",
        "|---|---|",
        f"| Ingestion cost | **${t['ingestion_cost_usd']:.4f}** (extraction ${t['extraction_cost_usd']:.4f}, embeddings ${t['embedding_cost_usd']:.4f}) |",
        f"| Cost per chunk | ${t['cost_per_chunk_usd']:.5f} (extraction alone ${t['extraction_cost_per_chunk_usd']:.5f}); the plan estimated $0.0035 |",
        f"| Extraction calls | {t['extraction_calls']:,}, one per chunk |",
        f"| Extraction failures (reply not valid JSON of the expected shape) | {t['extraction_failures']} of {t['chunks']:,} ({t['extraction_failure_rate']:.2%}); the runner refuses above 5% |",
        f"| Extraction tokens | {t['extraction_tokens_in']:,} in, {t['extraction_tokens_out']:,} out |",
        f"| Embedding tokens | {t['embedding_tokens']:,} (effective ${e['embedding_usd_per_million_tokens']} per million) |",
        f"| Wall time, first to last call | {t['wall_seconds_first_to_last_call']:,} s ({t['wall_seconds_first_to_last_call'] / 60:.1f} min) |",
        f"| All spend this month, every purpose | ${s['month_total_usd']:.4f} of ${s['settings']['monthly_cap_usd']} |",
        "",
        "## Cost by paper",
        "",
        "| # | Paper | Chunks | Nodes | Edges | Fail | Embed $ | Extract $ | Total $ | $/chunk | Out tok mean / p90 / max | At limit | Time |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in s["papers"]:
        o = p["output_tokens"]
        lines.append(
            f"| {p['ingestion_order']} | {p['arxiv_id']} {p['title'][:48]} | {p['chunks']} | {p['nodes']} | {p['edges']} | {p['extraction_failures']} | "
            f"{p['embedding_cost_usd']:.4f} | {p['extraction_cost_usd']:.4f} | {p['total_cost_usd']:.4f} | {p['cost_per_chunk_usd']:.5f} | "
            f"{o['mean']:.0f} / {o['p90']} / {o['max']} | {o['at_limit']} | {p['wall_seconds']:.0f} s |"
        )
    lines += [
        f"| | **Total** | **{t['chunks']:,}** | | | **{t['extraction_failures']}** | **{t['embedding_cost_usd']:.4f}** | **{t['extraction_cost_usd']:.4f}** | **{t['ingestion_cost_usd']:.4f}** | **{t['cost_per_chunk_usd']:.5f}** | | | |",
        "",
        "Paper 1 (Ragas) was ingested first, in an earlier step, with the same code and settings; the other fifteen followed in manifest order.",
        "",
        "## Per extraction call (all calls, one per chunk)",
        "",
        "| | mean | median | p90 | max |",
        "|---|---|---|---|---|",
        f"| Input tokens | {d['tokens_in']['mean']} | {d['tokens_in']['median']} | {d['tokens_in']['p90']} | {d['tokens_in']['max']} |",
        f"| Output tokens | {d['tokens_out']['mean']} | {d['tokens_out']['median']} | {d['tokens_out']['p90']} | {d['tokens_out']['max']} |",
        "",
        f"- Output p99: {d['tokens_out']['p99']} tokens. Replies that reached the {s['settings']['extraction_max_tokens']:,}-token limit: **{d['tokens_out']['at_limit']}**.",
        f"- Cost per call: mean ${d['cost_per_call_usd']['mean']:.5f}, cheapest ${d['cost_per_call_usd']['min']:.5f}, dearest ${d['cost_per_call_usd']['max']:.5f}.",
        f"- Blended extraction price: ${e['extraction_blended_usd_per_million_tokens']} per million tokens. {e['note']}",
        "",
        "## Every ledger row, by what it was for",
        "",
        "| Group | Calls | Tokens in | Tokens out | Cost |",
        "|---|---|---|---|---|",
    ]
    for g, v in sorted(s["ledger_by_group"].items(), key=lambda kv: -kv[1]["cost_usd"]):
        lines.append(f"| {g} | {v['calls']:,} | {v['tokens_in']:,} | {v['tokens_out']:,} | ${v['cost_usd']:.4f} |")
    lines += [
        f"| **All** | | | | **${s['month_total_usd']:.4f}** |",
        "",
        "The rows outside the benchmark ingestion are the few-cent probes of each route, the two throwaway one-paper extractions used to measure cost and truncation before the real run, and the chat turns used to check the agents against a real model. None of them are in the benchmark stores.",
        "",
        "Failed calls (no cost): " + ", ".join(f"#{f['id']} {f['purpose']} via {f['provider']}" for f in s["failed_calls"]) + ".",
        "",
        "## The stores this produced (for `--expect-*-sha256`)",
        "",
        f"- chunks: {s['stores']['chunks']:,}, chunk-store content hash `{s['stores']['chunks_sha256']}`",
        f"- graph hash `{s['stores']['graph_sha256']}`",
        f"- vectors hash `{s['stores']['vectors_sha256']}`",
        "",
        "Extraction has no seed, so a second ingestion would give a different graph. These are the stores the benchmark must run on; never re-ingest between arms.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--ledger", default=str(ROOT / "data" / "ledger.db"))
    p.add_argument("--data-dir", default=str(ROOT / "data" / "eval-live-live"))
    p.add_argument("--manifest", default=str(ROOT / "eval" / "corpus" / "MANIFEST.json"))
    p.add_argument("--out-dir", default=str(ROOT / "eval" / "results"))
    p.add_argument("--md-dir", default=str(ROOT / "refdocs" / "evidence"))
    p.add_argument("--label", default="live-ingestion")
    args = p.parse_args(argv)
    data_dir = Path(args.data_dir)
    try:
        summary, labelled = build_report(Path(args.ledger), data_dir / run_ablation.INGESTION_REPORT, data_dir, Path(args.manifest))
    except ReportInvalid as exc:
        print(f"REPORT REFUSED: {exc}", file=sys.stderr)
        return 2
    out_dir, md_dir = Path(args.out_dir), Path(args.md_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}-cost.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    fields = ["id", "ts", "provider", "model", "purpose", "status", "tokens_in", "tokens_out", "cost_usd", "attributed_to"]
    with (out_dir / f"{args.label}-ledger.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(labelled)
    write_markdown(summary, md_dir / f"{args.label}.md")
    t = summary["totals"]
    print(f"wrote {out_dir / (args.label + '-cost.json')}, {out_dir / (args.label + '-ledger.csv')}, {md_dir / (args.label + '.md')}")
    print(f"  {t['papers']} papers, {t['chunks']} chunks, ${t['ingestion_cost_usd']:.4f} (${t['cost_per_chunk_usd']:.5f}/chunk), "
          f"{t['extraction_failures']} extraction failures, month total ${summary['month_total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
