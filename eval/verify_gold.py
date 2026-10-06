"""Check gold files against the papers they quote. Reads the PDFs only; no retrieval, no model.

    uv run python eval/verify_gold.py --corpus-dir ../Arcana/eval/corpus [--status benchmark]

For every passage of every gold file it checks that (1) the document is in the manifest, (2) the text is
a verbatim, whitespace-collapsed span of that document's text on the stated page, and (3) at least one
corpus chunk COVERS it under the frozen relevance rule (eval/metrics.py). A passage that fails (3) can
never be retrieved by any arm, so it is reported: either the passage straddles a chunk boundary or it is
too short to match. Exit 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.ingestion.parse import parse
from eval import metrics
from eval.mutation_factcheck import load_chunks

ROOT = Path(__file__).resolve().parents[1]
_WS = re.compile(r"\s+")


def norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def page_texts(manifest: list[dict], corpus_dir: Path) -> dict[str, dict[int, str]]:
    return {
        e["arxiv_id"]: {p.page: norm(p.text) for p in parse((corpus_dir / e["file"]).read_bytes()).pages} for e in manifest
    }


def verify(gold_dir: Path, manifest: list[dict], corpus_dir: Path, status: str | None) -> list[str]:
    pages = page_texts(manifest, corpus_dir)
    chunk_texts = [c.text for c in load_chunks(manifest, corpus_dir).values()]
    problems: list[str] = []
    for path in sorted(gold_dir.glob("*.yaml")):
        gold = metrics.load_gold(gold_dir, path.stem)
        if gold is None or (status and gold.status != status):
            continue
        for i, p in enumerate(gold.passages):
            where = f"{path.stem} passage {i + 1} ({p.doc_id} p{p.page})"
            doc = pages.get(p.doc_id)
            if doc is None:
                problems.append(f"{where}: document not in the manifest")
                continue
            text = norm(p.text)
            if p.page is None or text not in doc.get(p.page, ""):
                found = [n for n, t in doc.items() if text in t]
                problems.append(f"{where}: not verbatim on that page" + (f" (found on page {found})" if found else " (not in the paper)"))
                continue
            n_cover = sum(metrics.coverage(c, p.text) >= metrics.MIN_COVERAGE for c in chunk_texts)
            if n_cover == 0:
                problems.append(f"{where}: no chunk covers this passage under the relevance rule (it straddles a chunk boundary or is too short)")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--manifest", default=str(ROOT / "eval" / "corpus" / "MANIFEST.json"))
    p.add_argument("--corpus-dir", default=str(ROOT / "eval" / "corpus"))
    p.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    p.add_argument("--status", help="only check files with this status (e.g. benchmark)")
    args = p.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    problems = verify(Path(args.gold_dir), manifest, Path(args.corpus_dir), args.status)
    for line in problems:
        print("FAIL", line)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
