"""Mutation suite for the Fact Checker (P1 A7).

    uv run python eval/mutation_factcheck.py --corpus-dir ../Arcana/eval/corpus

Starts from answers that are valid by construction (one sentence of a stored chunk, quoted verbatim from
it), checks that the checker leaves them alone, then plants one known defect at a time and records
whether the checker caught it:

    non_verbatim_quote       a word is inserted into the quote            deterministic: must be 100%
    wrong_chunk_citation     the citation names a chunk the quote is not in   deterministic: must be 100%
    wrong_document           the citation names another document          deterministic: must be 100%
    invented_other_document  the claim is a sentence from a different paper (quote and citation unchanged)
    invented_same_document   the claim is a sentence from another chunk of the same paper
    negated_claim            the claim keeps its own words and gains a "not": the vocabulary still matches

The first three are exact checks and are ASSERTED by the tests. The last three depend on the lexical
support rule and are only REPORTED: they are the measured detection rate, not a promise. negated_claim is
expected to go UNDETECTED by a word-overlap rule (it adds only a stopword). That is the known blind spot
the model judge exists for, and it is in the report so the lexical fallback is not read as more than it is.

What this does and does not measure. It runs the checker's deterministic core (`screen_answer` and
`finalize` with no model verdicts), so the support figures are for the LEXICAL FALLBACK only; the model
judge is not exercised (it costs money and is not reproducible). An "invented" claim here is a real
sentence from elsewhere in the corpus, not a model hallucination, and sentences from papers on the same
topic share vocabulary, so these rates are likely optimistic for subtle fabrications. Sampling is seeded.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.agents.fact_checker import SUPPORT_OVERLAP, screen_answer
from api.ingestion.chunk import chunk as chunk_pages
from api.ingestion.parse import parse
from api.ingestion.types import doc_id_for
from api.stores.doc_store import Chunk

ROOT = Path(__file__).resolve().parents[1]
DETERMINISTIC = ("non_verbatim_quote", "wrong_chunk_citation", "wrong_document")
REPORTED = ("invented_other_document", "invented_same_document", "negated_claim")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WS = re.compile(r"\s+")
MIN_WORDS, MAX_WORDS = 10, 40


class SuiteInvalid(Exception):
    pass


def usable_sentences(text: str) -> list[str]:
    """Plain prose sentences: long enough to be a claim, not tables, formulae or reference lists."""
    out: list[str] = []
    for sentence in _SENTENCE.split(_WS.sub(" ", text).strip()):
        words = sentence.split()
        letters = sum(ch.isalpha() or ch == " " for ch in sentence)
        if MIN_WORDS <= len(words) <= MAX_WORDS and letters / max(len(sentence), 1) >= 0.9 and sentence[0].isupper():
            out.append(sentence)
    return out


def load_chunks(manifest: list[dict[str, Any]], corpus_dir: Path) -> dict[str, Chunk]:
    chunks: dict[str, Chunk] = {}
    for entry in manifest:
        path = corpus_dir / entry["file"]
        if not path.exists():
            raise SuiteInvalid(f"corpus PDF missing: {path}")
        raw = path.read_bytes()
        for c in chunk_pages(parse(raw).pages, doc_id=doc_id_for(raw)):
            chunks[c.id] = c
    return chunks


def answer(claim: str, chunk: Chunk, quote: str) -> dict[str, Any]:
    return {
        "segments": [{"text": claim, "citationIds": ["c1"]}],
        "citations": [
            {"id": "c1", "chunkId": chunk.id, "docId": chunk.doc_id, "docTitle": "T", "page": chunk.page or 1, "quote": quote}
        ],
    }


def build_cases(chunks: dict[str, Chunk], n: int, seed: int) -> list[dict[str, Any]]:
    """Up to `n` base answers, each with the five mutations that apply to it."""
    rng = random.Random(seed)
    by_doc: dict[str, list[Chunk]] = {}
    for c in sorted(chunks.values(), key=lambda c: c.id):  # sorted: the sample does not depend on dict order
        if usable_sentences(c.text):
            by_doc.setdefault(c.doc_id, []).append(c)
    if len(by_doc) < 2:
        raise SuiteInvalid("need prose chunks from at least two documents")
    docs = sorted(by_doc)
    cases: list[dict[str, Any]] = []
    for _ in range(n * 3):  # draws can be skipped (no suitable partner); stop at n cases
        if len(cases) == n:
            break
        doc = rng.choice(docs)
        base = rng.choice(by_doc[doc])
        claim = rng.choice(usable_sentences(base.text))
        other_docs = [d for d in docs if d != doc]
        other = rng.choice(by_doc[rng.choice(other_docs)])
        siblings = [c for c in by_doc[doc] if c.id != base.id]
        if not siblings or claim in _WS.sub(" ", other.text):
            continue
        sibling = rng.choice(siblings)
        sibling_claim = rng.choice(usable_sentences(sibling.text))
        if sibling_claim in _WS.sub(" ", base.text):
            continue  # an overlapping chunk repeats the sentence: not a different claim
        words = claim.split()
        spot = rng.randrange(1, len(words) - 1)
        broken_quote = " ".join([*words[:spot], "invariably", *words[spot:]])
        negated = " ".join([*words[:spot], "not", *words[spot:]])
        base_answer = answer(claim, base, claim)
        wrong_chunk = answer(claim, other, claim)  # the quote is not in the chunk the citation names
        wrong_doc = answer(claim, base, claim)
        wrong_doc["citations"][0]["docId"] = other.doc_id
        cases.append(
            {
                "base": base_answer,
                "mutations": {
                    "non_verbatim_quote": answer(claim, base, broken_quote),
                    "wrong_chunk_citation": wrong_chunk,
                    "wrong_document": wrong_doc,
                    "invented_other_document": answer(rng.choice(usable_sentences(other.text)), base, claim),
                    "invented_same_document": answer(sibling_claim, base, claim),
                    "negated_claim": answer(negated, base, claim),
                },
            }
        )
    if len(cases) < n:
        raise SuiteInvalid(f"could only build {len(cases)} of {n} cases from this corpus")
    return cases


def detected(data: dict[str, Any], chunks: dict[str, Chunk]) -> bool:
    """True if the checker removed the (only) segment: it caught the defect."""
    return screen_answer(data, chunks).finalize().data is None


def run_mutations(chunks: dict[str, Chunk], n: int = 50, seed: int = 20261006) -> dict[str, Any]:
    cases = build_cases(chunks, n, seed)
    clean_kept = sum(not detected(c["base"], chunks) for c in cases)
    per_type: dict[str, dict[str, Any]] = {}
    for name in (*DETERMINISTIC, *REPORTED):
        caught = sum(detected(c["mutations"][name], chunks) for c in cases)
        per_type[name] = {
            "kind": "deterministic" if name in DETERMINISTIC else "lexical (reported, not asserted)",
            "planted": len(cases),
            "detected": caught,
            "detection_rate": round(caught / len(cases), 4),
        }
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
        "cases": len(cases),
        "support_rule": {"kind": "lexical overlap only, no model judge", "threshold": SUPPORT_OVERLAP},
        "clean_answers": {"kept": clean_kept, "of": len(cases), "pass_rate": round(clean_kept / len(cases), 4)},
        "per_type": per_type,
        "caveat": (
            "Lexical fallback only; the model judge is not measured here. Invented claims are real sentences "
            "from the corpus, not model hallucinations, so the invented-claim rates are likely optimistic. "
            "negated_claim shows the lexical rule's blind spot: a claim that keeps the evidence's words "
            "passes it."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--manifest", default=str(ROOT / "eval" / "corpus" / "MANIFEST.json"))
    p.add_argument("--corpus-dir", default=str(ROOT / "eval" / "corpus"))
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--seed", type=int, default=20261006)
    p.add_argument("--out", default=str(ROOT / "eval" / "results" / "mutation-factcheck.json"))
    args = p.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = run_mutations(load_chunks(manifest, Path(args.corpus_dir)), args.n, args.seed)
    except SuiteInvalid as exc:
        print(f"SUITE REFUSED: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"  clean answers kept: {result['clean_answers']['kept']}/{result['cases']}")
    for name, row in result["per_type"].items():
        print(f"  {name:25} {row['detected']}/{row['planted']}  ({row['kind']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
