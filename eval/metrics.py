"""Retrieval metrics against hand-annotated gold passages. No LLM, no model-judged score (D-15).

Gold is passage TEXT, not chunk ids: chunk ids change whenever parsing or chunking changes, passages
do not. So "is this chunk relevant" needs a rule, and the rule is fixed here, before any arm is run
(constraint 9) and stamped into every results file:

  A chunk COVERS a gold passage if at least MIN_COVERAGE of the passage's SHINGLE_N-word shingles
  (lowercase ASCII words, the same tokenizer as the BM25 signal) also occur in the chunk.
  A chunk is RELEVANT if it covers at least one gold passage.

  recall@k  = gold passages covered by at least one of the top k chunks / gold passages
  ndcg@k    = DCG over the top k with binary gain, / ideal DCG, where the ideal ranking puts
              min(k, R) relevant chunks first and R is the number of relevant chunks in the whole
              corpus (so a corpus with many relevant chunks is not penalised for returning them)

A question with no gold passages has undefined metrics: they are None, never 0, and the question is
excluded from every aggregate. A failed run is the runner's concern, not this module's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from api.retrieval.sparse import tokenize

SHINGLE_N = 5
MIN_COVERAGE = 0.3
K = 10


@dataclass(frozen=True)
class GoldPassage:
    doc_id: str
    page: int | None
    text: str


@dataclass(frozen=True)
class Gold:
    question_id: str
    status: str
    """"smoke" (format demonstration), "benchmark" (the real annotation) or "unanswerable"."""
    passages: tuple[GoldPassage, ...]
    reason: str | None = None
    approved_by: str | None = None
    """Who approved this file. None means a draft: not frozen, and no live benchmark may run against it."""

    @property
    def approved(self) -> bool:
        return bool(self.approved_by)


def rule_stamp() -> dict[str, object]:
    return {"shingle_n": SHINGLE_N, "min_coverage": MIN_COVERAGE, "k": K, "tokenizer": "api.retrieval.sparse.tokenize"}


def load_gold(directory: Path, question_id: str) -> Gold | None:
    path = directory / f"{question_id}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    passages = tuple(
        GoldPassage(doc_id=p["doc_id"], page=p.get("page"), text=p["text"])
        for p in data.get("reference_contexts") or []
    )
    return Gold(data["question_id"], data["status"], passages, data.get("reason"), data.get("approved_by"))


def shingles(text: str, n: int = SHINGLE_N) -> frozenset[tuple[str, ...]]:
    """All n-word windows of the text. Fewer than n words gives none."""
    words = tokenize(text)
    return frozenset(tuple(words[i : i + n]) for i in range(len(words) - n + 1))


def coverage(chunk_text: str, passage_text: str) -> float:
    """Fraction of the passage's shingles that also occur in the chunk.

    The shingle size comes from the PASSAGE (SHINGLE_N, or fewer words if the passage is shorter) and
    is applied identically to the chunk: shingles of different sizes can never match.
    """
    n = min(SHINGLE_N, len(tokenize(passage_text)))
    if n == 0:
        return 0.0
    wanted = shingles(passage_text, n)
    return len(wanted & shingles(chunk_text, n)) / len(wanted)


def covered_passages(chunk_text: str, gold: Gold) -> set[int]:
    return {i for i, p in enumerate(gold.passages) if coverage(chunk_text, p.text) >= MIN_COVERAGE}


def is_relevant(chunk_text: str, gold: Gold) -> bool:
    return bool(covered_passages(chunk_text, gold))


def recall_at_k(ranked_texts: list[str], gold: Gold, k: int = K) -> float | None:
    if not gold.passages:
        return None
    covered: set[int] = set()
    for text in ranked_texts[:k]:
        covered |= covered_passages(text, gold)
    return len(covered) / len(gold.passages)


def ndcg_at_k(ranked_texts: list[str], gold: Gold, corpus_relevant: int, k: int = K) -> float | None:
    """`corpus_relevant` is the number of relevant chunks in the whole corpus (see relevant_count)."""
    if not gold.passages or corpus_relevant == 0:
        return None
    gains = [1.0 if is_relevant(t, gold) else 0.0 for t in ranked_texts[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, corpus_relevant)))
    return dcg / ideal


def relevant_count(corpus_texts: list[str], gold: Gold) -> int:
    return sum(1 for t in corpus_texts if is_relevant(t, gold))
