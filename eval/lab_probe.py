"""P4 V1 probe (D-36): which scoring or loss formulas appear, with their symbolic form, in the stored passages?

Read-only and free: no model call, no embedding, no write. It reads the chunks of a data directory (`arcana.db`) and, for each
candidate (retrieval formulas the plan first assumed, then the losses and scores the corpus turned out to hold), lists the passages
that name it and hold a symbolic form of it, with the sentence. The first VerifiedLab contract is chosen from this evidence, not
from taste.

    uv run python eval/lab_probe.py data/m2/full-freeform-vault1
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.text import split_sentences


@dataclass(frozen=True)
class Candidate:
    name: str
    names: re.Pattern[str]
    """A passage must name the method."""
    forms: re.Pattern[str]
    """...and hold a symbolic form of it in the same passage."""


CANDIDATES = (
    Candidate(
        "ranknet_pairwise_loss",
        re.compile(r"RankNet", re.IGNORECASE),
        re.compile(r"log\s*\(\s*1\s*\+\s*exp"),
    ),
    Candidate(
        "pointwise_bce",
        re.compile(r"\bBCE\b|binary\s+cross-entropy", re.IGNORECASE),
        re.compile(r"log\s*σ|σ\s*\(\s*x\s*\)|logistic\s+function"),  # noqa: RUF001  (the passages use the Greek letter)
    ),
    Candidate(
        "info_nce",
        re.compile(r"InfoNCE", re.IGNORECASE),
        re.compile(r"min\s*L\s*=|[−-]\s*log\s*ϕ"),  # noqa: RUF001  (the passages use these characters)
    ),
    Candidate(
        "answer_relevance_score",
        re.compile(r"answer\s+relevance", re.IGNORECASE),
        re.compile(r"\bAR\s*="),
    ),
    Candidate(
        "reciprocal_rank_fusion",
        re.compile(r"reciprocal\s+rank\s+fusion|\bRRF\b", re.IGNORECASE),
        re.compile(r"1\s*/\s*\(\s*k\s*\+|\bk\s*=\s*60\b|\bk\s*\+\s*rank|\bk\s*\+\s*r\b", re.IGNORECASE),
    ),
    Candidate(
        "bm25",
        re.compile(r"\bBM25\b|Okapi", re.IGNORECASE),
        re.compile(
            r"\bk1\b|\bk_1\b|\bb\s*=\s*0\.75|\bavgdl\b|term\s+frequency\s+saturation|length\s+normali[sz]ation",
            re.IGNORECASE,
        ),
    ),
    Candidate(
        "cosine_similarity",
        re.compile(r"cosine\s+similarity", re.IGNORECASE),
        re.compile(r"cos\s*\(|\|\|\s*\w\s*\|\||dot\s+product|\bcos\s*θ|\bu\s*[·⋅]\s*v\b", re.IGNORECASE),
    ),
)


def probe(docs: SqliteDocStore) -> dict[str, list[dict[str, object]]]:
    found: dict[str, list[dict[str, object]]] = {c.name: [] for c in CANDIDATES}
    for chunk in docs.all_chunks():
        for candidate in CANDIDATES:
            if not (candidate.names.search(chunk.text) and candidate.forms.search(chunk.text)):
                continue
            sentence = next((s for s in split_sentences(chunk.text) if candidate.forms.search(s)), None)
            found[candidate.name].append(
                {
                    "chunk_id": chunk.id,
                    "doc_id": chunk.doc_id,
                    "page": chunk.page,
                    "sentence": (sentence or "")[:300],
                }
            )
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = Path(argv[1])
    docs = SqliteDocStore(make_engine(data / "arcana.db"))
    found = probe(docs)
    summary = {
        name: {"passages": len(rows), "documents": len({str(r["doc_id"]) for r in rows})}
        for name, rows in found.items()
    }
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(json.dumps({"data": str(data), "summary": summary, "found": found}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
