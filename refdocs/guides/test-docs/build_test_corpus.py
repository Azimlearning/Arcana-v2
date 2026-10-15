"""Build a data directory from the three test PDFs in which the Studio's vault tools have material (`refdocs/guides/manual-testing.md`).

    ARCANA_LLM_MODE=live uv run python refdocs/guides/test-docs/build_test_corpus.py --out data/manual-test --allow-paid

Why this exists: uploading a PDF in the app builds a graph with the default (free-form) extractor, which states no claims and no
definitions, so quiz, flashcards, blurting, Cornell notes, Socratic questions, brief and cheat sheet have nothing to derive from. Those
tools run on a corpus built with the atomic builder (D-34, D-35). This script does the same steps the project's own tools do, for these
three small papers:

  1. ingest the PDFs into a staging directory (no model is paid: the free-form graph it makes is replaced in step 2; embeddings follow
     ARCANA_EMBED_MODE, fake by default, which is enough to answer questions over three papers);
  2. rebuild the graph with the atomic2 builder over the stored passages (a live model, a few cents; refused without --allow-paid and
     stopped at --max-usd), which also writes the claim notes;
  3. compile the vault from that graph and the claims.

Then run the app on the result:  ARCANA_DATA_DIR=data/manual-test uv run uvicorn api.main:app --reload
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from api.container import build_container  # noqa: E402
from api.core.logging import configure_logging  # noqa: E402
from api.core.settings import load_settings  # noqa: E402
from api.ingestion.pipeline import ingest_pdf  # noqa: E402
from eval.graph_variant import rebuild_graph  # noqa: E402
from eval.vault_tool import build as build_vault  # noqa: E402

DOCS = Path(__file__).resolve().parent


async def stage(staging: Path) -> list[dict[str, str]]:
    """Ingest the PDFs into `staging` and return the ingestion report entries the rebuild tool reads."""
    settings = load_settings().model_copy(update={"arcana_data_dir": staging, "arcana_llm_mode": "fake"})
    container = build_container(settings)
    report: list[dict[str, str]] = []
    for pdf in sorted(DOCS.glob("*.pdf")):
        result = await ingest_pdf(pdf.read_bytes(), pdf.name, container.ingest_deps)
        if result.status != "ready":
            raise SystemExit(f"{pdf.name} did not ingest: {result.error}")
        report.append({"arxiv_id": pdf.stem, "doc_id": result.doc_id, "title": result.title, "chunks": result.chunk_count})
        print(f"ingested {pdf.name}: {result.chunk_count} passage(s)")
    container.graph.save()
    (staging / "ingestion_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: pick a new directory")
    configure_logging("WARNING")
    work = out.with_name(out.name + "-work")
    staging, atomic = work / "staged", work / "atomic2"
    if work.exists():
        shutil.rmtree(work)
    staging.mkdir(parents=True)
    await stage(staging)
    record = await rebuild_graph(staging, atomic, "atomic2", args.max_usd, args.allow_paid)
    print(f"atomic2 rebuild: {record.get('claims', '?')} claim(s), spent ${record.get('spent_usd', '?')}")
    stats = build_vault(atomic, out)["stats"]
    print(f"vault: {stats.get('pages', '?')} pages, {stats.get('claims', '?')} claims -> {out}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, help="a new data directory the app will run on")
    p.add_argument("--max-usd", type=float, default=0.3)
    p.add_argument("--allow-paid", action="store_true")
    args = p.parse_args()
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
