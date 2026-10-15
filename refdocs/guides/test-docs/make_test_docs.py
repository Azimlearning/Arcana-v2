"""Generate the three small PDFs the manual test guide uses (`refdocs/guides/manual-testing.md`).

    uv run python refdocs/guides/test-docs/make_test_docs.py

The papers are invented for testing: short, in plain definition-and-claim sentences, so a tester can predict what the system should
extract and say. Nothing here is a real publication. Two sentences are copied word for word from the papers the labs recognise
(`F1@k` and RankNet), so the Labs screen has something to offer; one definition of dense retrieval deliberately differs between two papers,
so the notes lint has something to report.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

OUT = Path(__file__).resolve().parent

PAPERS: dict[str, tuple[str, list[tuple[str, list[str]]]]] = {
    "dense_retrieval_basics.pdf": (
        "Dense Retrieval Basics",
        [
            (
                "1 Introduction",
                [
                    "Dense retrieval is a method that finds passages by comparing embedding vectors of the query and the passages.",
                    "A bi-encoder is a model that encodes the query and each passage separately into vectors.",
                    "Cosine similarity is a measure of the angle between two embedding vectors.",
                ],
            ),
            (
                "2 Strengths and costs",
                [
                    "Dense retrieval captures meaning that shares no words with the query.",
                    "Dense retrieval needs an index of vectors built ahead of time.",
                    "Approximate nearest neighbour search makes dense retrieval fast on large collections.",
                    "Dense retrieval can miss rare names and acronyms that a keyword method finds easily.",
                ],
            ),
        ],
    ),
    "sparse_retrieval_and_bm25.pdf": (
        "Sparse Retrieval and BM25",
        [
            (
                "1 Keyword retrieval",
                [
                    "BM25 is a ranking function that scores a passage by the frequency of the query terms in it and their rarity across the corpus.",
                    "TF-IDF is a weighting scheme that multiplies how often a term occurs in a passage by how rare the term is in the corpus.",
                    "An inverted index is a structure that maps each term to the passages that contain it.",
                ],
            ),
            (
                "2 Behaviour",
                [
                    "BM25 matches exact terms, so it handles acronyms and rare names well.",
                    "Sparse retrieval fails when the query and the passage use different words for the same idea.",
                    "BM25 needs no training and no vector index.",
                    "Dense retrieval is a technique that maps text to vectors and ranks passages by their similarity to the query.",
                ],
            ),
        ],
    ),
    "fusion_reranking_and_metrics.pdf": (
        "Fusion, Reranking and Metrics",
        [
            (
                "1 Combining retrievers",
                [
                    "Reciprocal rank fusion is a method that combines several ranked lists by summing one over a constant plus the rank of each passage.",
                    "Hybrid retrieval combines dense retrieval and BM25 to cover both meaning and exact terms.",
                    "A cross-encoder is a model that reads the query and a passage together and scores their relevance.",
                    "Reranking reorders the top passages with a slower and more accurate model.",
                ],
            ),
            (
                "2 Measuring retrieval",
                [
                    "Recall at k is the share of the relevant passages that appear in the top k results.",
                    "Precision at k is the share of the top k results that are relevant.",
                    "F1@k: The harmonic mean of precision and recall",
                    "RankNet is a pairwise loss that measures the correctness of relative passage orders",
                    "Reranking can improve precision at k but it cannot recover a passage the first stage never retrieved.",
                ],
            ),
        ],
    ),
}


def build(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    y = 72.0
    page.insert_text((72, y), title, fontsize=18, fontname="helv")
    y += 36
    for heading, sentences in sections:
        page.insert_text((72, y), heading, fontsize=13, fontname="helv")
        y += 22
        body = " ".join(s if s.endswith((".", "k", "s")) or s[-1].isalpha() else s for s in sentences)
        # one paragraph per section, wrapped by the text box
        rect = fitz.Rect(72, y, 523, y + 220)
        leftover = page.insert_textbox(rect, body, fontsize=11, fontname="helv")
        assert leftover >= 0, f"{path.name}: a section did not fit the page"
        y += 220 - leftover + 16
    doc.set_metadata({"title": title, "author": "Arcana manual test", "subject": "invented test paper"})
    doc.save(path)
    doc.close()


def main() -> None:
    for name, (title, sections) in PAPERS.items():
        build(OUT / name, title, sections)
        print("wrote", name)


if __name__ == "__main__":
    main()
