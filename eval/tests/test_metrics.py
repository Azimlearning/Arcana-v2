import math
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


def test_every_question_has_a_gold_file_with_a_status_it_can_defend():
    import yaml

    questions = yaml.safe_load((GOLD_DIR.parent / "questions.yaml").read_text(encoding="utf-8"))
    ids = [q["id"] for q in (questions["questions"] if isinstance(questions, dict) else questions)]
    assert len(ids) == 20
    statuses = {}
    for qid in ids:
        g = metrics.load_gold(GOLD_DIR, qid)
        assert g is not None, f"{qid} has no gold file"
        statuses[qid] = g
    assert not [q for q, g in statuses.items() if g.status == "smoke"]  # the smoke files were replaced
    unanswerable = statuses["q-single-01"]
    assert unanswerable.status == "unanswerable" and unanswerable.passages == ()
    assert unanswerable.reason and "Reciprocal Rank Fusion" in unanswerable.reason
    for qid, g in statuses.items():
        if qid != "q-single-01":
            assert g.status == "benchmark" and len(g.passages) >= 3, qid
            assert all(p.page and p.doc_id and len(p.text) >= 40 for p in g.passages), qid
    assert metrics.load_gold(GOLD_DIR, "q-cross-99") is None


def test_benchmark_gold_records_its_method_and_whether_it_is_approved():
    import yaml

    for path in sorted(GOLD_DIR.glob("q-*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["status"] != "benchmark":
            continue
        assert "approved_by" in data, path.name  # None means a draft, a name means approved
        assert "Retrieval output was never consulted" in data["note"], path.name


V1_CORPUS = Path(__file__).resolve().parents[2].parent / "Arcana" / "eval" / "corpus"


@pytest.mark.skipif(not V1_CORPUS.exists(), reason="v1 corpus PDFs are not on this machine")
def test_every_gold_passage_is_verbatim_in_its_paper_and_reachable_by_a_chunk():
    import json

    from eval.verify_gold import verify

    manifest = json.loads((GOLD_DIR.parent / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert verify(GOLD_DIR, manifest, V1_CORPUS, None) == []
