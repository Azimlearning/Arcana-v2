"""The Fact Checker mutation suite on a small synthetic corpus: exact checks are asserted, the rest reported."""

import json
from pathlib import Path

import pytest

from api.stores.doc_store import Chunk
from eval.mutation_factcheck import (
    DETERMINISTIC,
    REPORTED,
    SuiteInvalid,
    build_cases,
    main,
    run_mutations,
    usable_sentences,
)

PROSE = {
    "d1": [
        "Dense retrieval encodes every passage into a vector and ranks passages by their similarity to the query vector. "
        "Approximate nearest neighbour indexes make this search fast on very large collections of documents.",
        "Sparse retrieval scores each document by the frequency of the query terms it contains and the rarity of those terms. "
        "It needs no training data and handles rare words well but misses paraphrases that share no vocabulary.",
        "Reciprocal rank fusion merges several ranked lists by adding a score that shrinks with the rank of each passage. "
        "Passages that several lists rank highly therefore rise above passages that only one list likes.",
    ],
    "d2": [
        "A knowledge graph stores entities as nodes and the relations between them as labelled edges extracted from text. "
        "Traversing those edges answers questions that connect several concepts across different documents.",
        "Chunking splits a long document into overlapping windows so that each window fits the context of the embedding model. "
        "Smaller windows locate evidence precisely while larger windows keep more of the surrounding argument.",
        "Evaluation of retrieval compares the ranked passages against a gold set written before any system was run. "
        "Recall at ten and normalised discounted cumulative gain are the two measures reported for every question.",
    ],
}


def corpus() -> dict[str, Chunk]:
    chunks: dict[str, Chunk] = {}
    for doc, texts in PROSE.items():
        for i, text in enumerate(texts):
            cid = f"{doc}-{i}"
            chunks[cid] = Chunk(id=cid, doc_id=doc, ordinal=i, page=i + 1, text=text)
    return chunks


def test_only_plain_prose_sentences_are_usable_as_claims():
    text = "Short one. Table 3 shows 12.5 and 14.7 and 99.1 for the ten systems in the second column of the results. " + PROSE["d1"][0]
    found = usable_sentences(text)
    assert len(found) == 2 and all(s[0].isupper() and len(s.split()) >= 10 for s in found)
    assert all("Table 3" not in s for s in found)  # digits and fragments are not claims


def test_the_exact_checks_catch_every_planted_defect_and_clean_answers_survive():
    result = run_mutations(corpus(), n=20, seed=1)
    assert result["clean_answers"] == {"kept": 20, "of": 20, "pass_rate": 1.0}
    for name in DETERMINISTIC:
        row = result["per_type"][name]
        assert row["detected"] == row["planted"] == 20, name  # non-verbatim quote, wrong chunk, wrong document
    assert set(result["per_type"]) == {*DETERMINISTIC, *REPORTED}


def test_the_lexical_rows_are_reported_not_asserted_and_labelled_so():
    result = run_mutations(corpus(), n=20, seed=1)
    for name in REPORTED:
        row = result["per_type"][name]
        assert 0.0 <= row["detection_rate"] <= 1.0 and "reported" in row["kind"]
    # A negation adds only a stopword, so a word-overlap rule cannot see it: the documented blind spot.
    assert result["per_type"]["negated_claim"]["detection_rate"] == 0.0
    assert "blind spot" in result["caveat"] and "lexical" in result["support_rule"]["kind"]


def test_the_sample_is_reproducible_from_its_seed():
    first = build_cases(corpus(), 10, seed=7)
    again = build_cases(corpus(), 10, seed=7)
    other = build_cases(corpus(), 10, seed=8)
    assert first == again and first != other


def test_a_corpus_that_cannot_support_the_suite_is_refused():
    one_doc = {k: v for k, v in corpus().items() if v.doc_id == "d1"}
    with pytest.raises(SuiteInvalid):
        build_cases(one_doc, 5, seed=1)


def test_a_missing_corpus_is_refused_not_a_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"arxiv_id": "x", "title": "T", "file": "absent.pdf"}]), encoding="utf-8")
    code = main(["--manifest", str(manifest), "--corpus-dir", str(tmp_path), "--out", str(tmp_path / "o.json")])
    assert code == 2 and "SUITE REFUSED" in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()
