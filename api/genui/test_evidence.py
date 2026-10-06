"""Quote helpers: every result is a verbatim span of the normalised chunk, and relational quotes hold every label."""

import pytest

from api.genui.evidence import (
    QUOTE_CHARS,
    best_excerpt,
    excerpt_containing,
    label_in_quote,
    normalise,
    verified_quote,
)
from api.genui.validate import MIN_QUOTE_CHARS

CHUNK = (
    "Dense retrieval encodes passages into vectors. HybridRAG combines vector retrieval with a knowledge graph "
    "to answer questions. Sparse retrieval such as BM25 scores exact terms.\n"
    "The knowledge graph links entities. Reciprocal rank fusion merges rankings by rank, not by score."
)


def test_a_sentence_holding_both_labels_is_returned_verbatim():
    quote = excerpt_containing(CHUNK, ["HybridRAG", "knowledge graph"])
    assert quote == "HybridRAG combines vector retrieval with a knowledge graph to answer questions."
    assert quote in normalise(CHUNK)


def test_every_label_must_be_present_or_nothing_is_returned():
    assert excerpt_containing(CHUNK, ["HybridRAG", "Louvain communities"]) is None
    assert excerpt_containing(CHUNK, ["nonexistent entity"]) is None
    assert excerpt_containing(CHUNK, []) is None
    assert excerpt_containing(CHUNK, ["BM25", ""]) is None  # an empty label would match everything


def test_labels_match_ignoring_case_and_whitespace_runs():
    broken = "A note on hybrid  retrieval.\nHybrid\nRAG joins vector search and a knowledge\ngraph in one pipeline."
    quote = excerpt_containing(broken, ["hybrid rag", "KNOWLEDGE GRAPH"])
    assert quote is not None and "Hybrid RAG joins vector search and a knowledge graph" in quote
    assert quote in normalise(broken)  # the line breaks became single spaces, as the validator compares them


def test_labels_in_adjacent_sentences_are_found_as_one_span():
    quote = excerpt_containing(CHUNK, ["BM25", "knowledge graph"])
    assert quote is not None and "BM25" in quote and "knowledge graph" in quote
    assert quote in normalise(CHUNK) and len(quote) <= QUOTE_CHARS


def test_a_span_too_short_to_be_evidence_is_extended_not_returned():
    chunk = "BM25 is fast. It uses a graph of terms to rank pages for a query."
    quote = excerpt_containing(chunk, ["BM25"])
    assert quote is not None and len(quote) >= MIN_QUOTE_CHARS  # "BM25 is fast." (13 characters) is not enough


def test_a_whole_chunk_shorter_than_the_minimum_may_be_returned_whole():
    assert excerpt_containing("Tiny BM25.", ["BM25"]) == "Tiny BM25."


def test_a_pair_of_labels_far_apart_in_one_long_sentence_uses_the_tightest_window():
    filler = " and ".join(f"clause number {i} about unrelated things" for i in range(30))
    chunk = f"Alpha is described first, {filler}, and finally Omega closes the sentence"
    assert excerpt_containing(chunk, ["Alpha", "Omega"]) is None  # farther apart than QUOTE_CHARS: refused, not truncated
    near = f"{filler}, then Alpha relates to Omega in one short clause, {filler}"
    quote = excerpt_containing(near, ["Alpha", "Omega"])
    assert quote is not None and len(quote) <= QUOTE_CHARS and "Alpha" in quote and "Omega" in quote
    assert quote in normalise(near)


@pytest.mark.parametrize("labels", [["HybridRAG"], ["BM25"], ["knowledge graph"], ["Reciprocal rank fusion", "rank"], ["entities", "knowledge graph"]])
def test_whatever_is_returned_is_a_verbatim_span_that_holds_every_label_and_passes_the_length_rules(labels):
    quote = excerpt_containing(CHUNK, labels)
    assert quote is not None
    assert quote in normalise(CHUNK)
    assert all(label_in_quote(quote, label) for label in labels)
    assert MIN_QUOTE_CHARS <= len(quote) <= QUOTE_CHARS


def test_label_in_quote():
    assert label_in_quote("The Knowledge  Graph links entities.", "knowledge graph")
    assert not label_in_quote("The graph links entities.", "knowledge graph")
    assert not label_in_quote("anything", "")
    assert not label_in_quote("anything", "   ")


def test_best_excerpt_is_a_verbatim_sentence_close_to_the_segment():
    quote = best_excerpt(CHUNK, "Reciprocal rank fusion merges rankings")
    assert quote == "Reciprocal rank fusion merges rankings by rank, not by score."
    assert quote in normalise(CHUNK)


def test_best_excerpt_cuts_a_long_sentence_on_a_word_boundary():
    long_sentence = " ".join(["word"] * 200) + "."
    quote = best_excerpt(long_sentence, "word")
    assert len(quote) <= QUOTE_CHARS and quote in normalise(long_sentence) and not quote.endswith(" ")


def test_verified_quote_keeps_a_verbatim_span_and_rejects_the_rest():
    assert verified_quote(CHUNK, "The knowledge graph links entities.") == "The knowledge graph links entities."
    assert verified_quote(CHUNK, "The knowledge  graph\nlinks entities.") == "The knowledge graph links entities."
    assert verified_quote(CHUNK, "The knowledge graph never links entities.") is None  # not in the chunk
    assert verified_quote(CHUNK, "BM25") is None  # verbatim but too short to be evidence
    assert verified_quote(CHUNK, None) is None and verified_quote(CHUNK, 42) is None and verified_quote(CHUNK, "") is None


def test_a_label_matches_whole_words_only():
    assert label_in_quote("AI changes search.", "AI")
    assert not label_in_quote("A chain of events.", "AI")  # "ai" inside "chain" is not a mention
    assert label_in_quote("Scores come from BM25, not vectors.", "BM25")
    assert label_in_quote("The C++ library.", "C++")
    assert excerpt_containing("A long chain of events ties the graph together in one sentence.", ["AI"]) is None
