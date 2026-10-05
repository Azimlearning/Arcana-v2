"""Regenerates hybrid_retrieval.pdf, the small fixture used by ingestion, retrieval and API tests.

    uv run python api/tests/fixtures/make_fixture_pdf.py

The text is original and written for this repo. Capitalised technical terms recur across pages on
purpose, so the fake extractor links chunks through shared graph nodes the way a real model would.
"""

from pathlib import Path

import pymupdf

TITLE = "Hybrid Retrieval over Knowledge Graphs"

PAGES = [
    """Hybrid Retrieval over Knowledge Graphs

Abstract. Retrieval augmented generation grounds a language model in evidence fetched from a corpus. Dense Retrieval embeds passages and queries into one vector space and ranks by cosine similarity. It finds paraphrases well but can miss rare terms. BM25 is a sparse method that scores exact term overlap. It is strong on identifiers and names but blind to synonyms. Neither method knows how concepts relate across documents.

A Knowledge Graph stores entities and the relations between them. When every relation records the passage it was extracted from, a graph hit can be traced back to evidence. This paper studies Hybrid Retrieval, which combines Dense Retrieval, BM25 and graph traversal, and asks whether the graph signal adds measurable recall on questions that span several documents.

Introduction. Single document questions are usually answered by one good passage. Cross document questions are different: the answer needs facts that live in separate papers, linked only by a shared concept. Dense Retrieval tends to return several passages about the same paper. Graph Expansion can instead walk from a concept to every passage that mentions it, in any document.""",
    """Method. Each document is split into overlapping chunks of fixed size. Every chunk is embedded for Dense Retrieval and indexed for BM25. A language model reads each chunk once and names the entities and relations it contains, with no fixed schema. Entity Resolution then canonicalises names, so that the plural and singular forms of a concept, or different capitalisation, become one node in the Knowledge Graph.

Fusion. The three rankings are merged with Reciprocal Rank Fusion. A passage at rank r in a list contributes one over the sum of a constant k and r, and contributions add across lists. Reciprocal Rank Fusion needs no score calibration, which matters because cosine similarity, BM25 scores and graph distances live on different scales. With k set to sixty the step from rank one to rank two is tiny, one over sixty one against one over sixty two, so agreement between lists counts for more than any single list's top rank.

Graph Retrieval. A query is matched to graph nodes by Entity Resolution. The retriever then expands one hop from each matched node and ranks the passages attached to the edges it reaches. If no query term resolves to a node, the graph signal returns nothing and Hybrid Retrieval degrades to the other two signals.""",
    """Evaluation. Questions are split into single document and cross document groups. Gold passages are annotated by hand before any retrieval arm is run, so no arm can influence its own reference. Recall at ten and normalised discounted cumulative gain are computed per question, and arms are compared with a paired Wilcoxon test. Model judged answer quality is reported only as a secondary measure, because it mixes retrieval quality with generation quality.

Ablation. Five arms isolate each signal: Dense Retrieval alone, BM25 alone, Graph Retrieval alone, a flat arm that fuses Dense Retrieval and BM25, and the full Hybrid Retrieval arm. The comparison of the flat arm with the full arm is the one that measures the contribution of the Knowledge Graph.

Limitations. Entity Resolution is approximate. If query entities fail to match graph nodes, Graph Retrieval silently contributes nothing, which looks like a null result. The resolution hit rate is therefore logged for every query, so a failed match can be told apart from a true absence of graph signal. Louvain community detection on the graph is left for future work on global questions.""",
]


def build(path: Path) -> None:
    doc = pymupdf.open()
    for text in PAGES:
        page = doc.new_page(width=595, height=842)
        rect = pymupdf.Rect(50, 50, 545, 792)
        leftover = page.insert_textbox(rect, text, fontsize=10, fontname="helv")
        assert leftover >= 0, "page text overflowed the textbox"
    doc.set_metadata({"title": TITLE})
    doc.save(str(path), deflate=True, garbage=3)
    doc.close()


if __name__ == "__main__":
    out = Path(__file__).parent / "hybrid_retrieval.pdf"
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
