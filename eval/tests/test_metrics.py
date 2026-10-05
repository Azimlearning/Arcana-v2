import math
import re
from pathlib import Path

import pytest

from eval import metrics
from eval.metrics import Gold, GoldPassage

GOLD_DIR = Path(__file__).resolve().parents[1] / "gold"


def gold(*texts: str) -> Gold:
    return Gold("q", "smoke", tuple(GoldPassage("d", 1, t) for t in texts))


P1 = "Reciprocal rank fusion adds one over the sum of a constant and the rank for each list a passage appears in."
P2 = "Dense retrieval embeds the query and every passage into one vector space and ranks by inner product."


def test_coverage_is_whole_for_the_same_text_and_ignores_case_and_punctuation():
    assert metrics.coverage(P1, P1) == 1.0
    assert metrics.coverage(P1.upper().replace(" ", "\n"), P1) == 1.0
    assert metrics.coverage("Entirely unrelated words about zebras and giraffes in the savanna.", P1) == 0.0


def test_coverage_counts_the_share_of_the_passage_present():
    half = " ".join(P1.split()[: len(P1.split()) // 2])
    assert 0.35 < metrics.coverage(half, P1) < 0.65


def test_a_passage_shorter_than_the_shingle_is_still_comparable():
    assert metrics.coverage("the quick fox", "quick fox") == 1.0  # the passage's own size is used for both
    assert metrics.coverage("fox", "quick fox") == 0.0  # a chunk shorter than the shingle matches nothing
    assert metrics.coverage("", "anything at all") == 0.0
    assert metrics.coverage("anything", "") == 0.0


def test_a_chunk_is_relevant_exactly_at_the_frozen_threshold():
    g = gold(P1)
    words = P1.split()  # 21 words, so 17 five-word shingles; 0.3 of them needs 10 words
    assert not metrics.is_relevant(" ".join(words[:9]), g)  # 0.294
    assert metrics.is_relevant(" ".join(words[:10]), g)  # 0.353
    assert not metrics.is_relevant(" ".join(words[:5]), g)  # one shingle is far too little
    assert metrics.MIN_COVERAGE == 0.3 and metrics.SHINGLE_N == 5 and metrics.K == 10


def test_recall_counts_gold_passages_covered_within_k():
    g = gold(P1, P2)
    texts = ["noise one", P1 + " extra words", "noise two", P2]
    assert metrics.recall_at_k(texts, g, k=10) == 1.0
    assert metrics.recall_at_k(texts, g, k=2) == 0.5  # P2 is at rank 4, outside the cut
    assert metrics.recall_at_k(["noise"], g) == 0.0


def test_one_chunk_covering_two_passages_counts_for_both():
    g = gold(P1, P2)
    assert metrics.recall_at_k([P1 + " " + P2], g) == 1.0


def test_recall_is_undefined_not_zero_without_gold():
    assert metrics.recall_at_k(["anything"], Gold("q", "unanswerable", ())) is None


def test_ndcg_matches_a_hand_computed_value():
    g = gold(P1)
    ranked = [P1, "noise", P1 + " again"]  # relevant at ranks 1 and 3
    dcg = 1 / math.log2(2) + 1 / math.log2(4)  # 1 + 0.5
    ideal = 1 / math.log2(2) + 1 / math.log2(3)  # two relevant chunks exist in the corpus
    assert metrics.ndcg_at_k(ranked, g, corpus_relevant=2) == pytest.approx(dcg / ideal)
    assert metrics.ndcg_at_k(ranked, g, corpus_relevant=2) == pytest.approx(0.9197, abs=1e-3)


def test_ndcg_is_one_for_a_perfect_ranking_and_zero_for_none_relevant():
    g = gold(P1)
    assert metrics.ndcg_at_k([P1, P1 + " x"], g, corpus_relevant=2) == pytest.approx(1.0)
    assert metrics.ndcg_at_k(["noise", "more noise"], g, corpus_relevant=2) == 0.0


def test_ndcg_ideal_is_capped_at_k():
    g = gold(P1)
    perfect_ten = [P1] * 10
    assert metrics.ndcg_at_k(perfect_ten, g, corpus_relevant=500) == pytest.approx(1.0)


def test_ndcg_is_undefined_without_gold_or_without_relevant_chunks_in_the_corpus():
    assert metrics.ndcg_at_k(["x"], Gold("q", "unanswerable", ()), corpus_relevant=3) is None
    assert metrics.ndcg_at_k(["x"], gold(P1), corpus_relevant=0) is None


def test_relevant_count_scans_the_corpus():
    assert metrics.relevant_count([P1, "noise", P1 + " more", P2], gold(P1)) == 2


# ── the real gold files ──────────────────────────────────────────────────────


def test_the_gold_files_load_with_the_statuses_they_claim():
    cross = metrics.load_gold(GOLD_DIR, "q-cross-01")
    single = metrics.load_gold(GOLD_DIR, "q-single-02")
    unanswerable = metrics.load_gold(GOLD_DIR, "q-single-01")
    assert cross and cross.status == "smoke" and len(cross.passages) == 3
    assert single and single.status == "smoke" and len(single.passages) == 3
    assert unanswerable and unanswerable.status == "unanswerable" and unanswerable.passages == ()
    assert unanswerable.reason and "Reciprocal Rank Fusion" in unanswerable.reason
    assert metrics.load_gold(GOLD_DIR, "q-cross-99") is None


def test_smoke_gold_is_labelled_as_not_the_benchmark_gold():
    for qid in ("q-cross-01", "q-single-02"):
        text = (GOLD_DIR / f"{qid}.yaml").read_text(encoding="utf-8")
        assert "NOT the benchmark gold" in text


V1_CORPUS = Path(__file__).resolve().parents[2].parent / "Arcana" / "eval" / "corpus"


@pytest.mark.skipif(not V1_CORPUS.exists(), reason="v1 corpus PDFs are not on this machine")
def test_every_smoke_gold_passage_is_verbatim_in_its_paper():
    import json

    import pymupdf

    manifest = {m["arxiv_id"]: m["file"] for m in json.loads((GOLD_DIR.parent / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))}
    for qid in ("q-cross-01", "q-single-02"):
        g = metrics.load_gold(GOLD_DIR, qid)
        assert g is not None
        for p in g.passages:
            assert p.page is not None
            doc = pymupdf.open(V1_CORPUS / manifest[p.doc_id])
            page = re.sub(r"\s+", " ", str(doc[p.page - 1].get_text("text")))
            doc.close()
            assert p.text in page, f"{qid}: passage is not verbatim on {p.doc_id} p{p.page}"
