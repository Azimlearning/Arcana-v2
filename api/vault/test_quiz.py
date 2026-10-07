"""The quiz from claims (Q1, D-35 A8): every expected value is worked out by hand from the handmade vault below.

Passages (document, page): c1 (d1, 3), c2 (d2, 5), c3 (d1, 7). Pages (kind): dense_retrieval, bm25, rrf "reciprocal rank fusion",
reranking, query_expansion are methods; squad is the only dataset; llm "large language models" and lm "language models" are
concepts. Claims (the sentence names the pages after the arrow):
    claim-1 c1  "Dense retrieval finds passages by ..."          dense_retrieval
    claim-2 c1  "BM25 scores terms by ..."                       bm25
    claim-3 c2  "Reciprocal rank fusion combines ... dense retrieval and BM25 ..."   rrf, dense_retrieval, bm25
    claim-4 c2  "Reranking reorders the top passages ..."        reranking
    claim-5 c3  "The SQuAD benchmark pairs ..."                  squad
    claim-6 c3  "Retrieval- augmented generation helps ..."      rag (a name a PDF broke: no literal blank)
    claim-7 c1  "Dense retrieval needs an index ..."             dense_retrieval
    claim-8 c3  "Large language models are trained on text ..."  llm
By hand: claim-3 has only reranking and query_expansion left as methods that are not in its sentence (two, not three); claim-5 has
no other dataset; claim-6 has no literal name; claim-8's "language models" is made of the same words as the target's, so lm is never a
distractor and the concept pool has no three others.
"""

import hashlib
import json
from pathlib import Path

import pytest

from api.learner.mastery import MasteryScore
from api.stores.doc_store import Chunk, Document
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault import quiz
from api.vault.quiz import check_answer, derive_item, derive_quiz, source_citation
from api.vault.types import ClaimNote, ConceptPage, Vault

TEXT = {
    "c1": (
        "Dense retrieval finds passages by comparing embedding vectors of the query and the text. "
        "BM25 scores terms by their frequency in a passage and their rarity across the corpus. "
        "Dense retrieval needs an index of vectors built ahead of time for speed."
    ),
    "c2": (
        "Reciprocal rank fusion combines the rankings of dense retrieval and BM25 without tuning weights. "
        "Reranking reorders the top passages with a slower and more accurate model. "
        "Query expansion adds related words to the question before it is searched."
    ),
    "c3": (
        "The SQuAD benchmark pairs questions with spans of Wikipedia passages. "
        "Retrieval- augmented generation helps a model answer from outside text. "
        "Large language models are trained on text from the web and from books."
    ),
}
DOC_OF = {"c1": "d1", "c2": "d2", "c3": "d1"}
PAGE_OF = {"c1": 3, "c2": 5, "c3": 7}
SENTENCES = {
    "claim-1": (
        "c1",
        "Dense retrieval finds passages by comparing embedding vectors of the query and the text.",
        ("dense_retrieval",),
    ),
    "claim-2": (
        "c1",
        "BM25 scores terms by their frequency in a passage and their rarity across the corpus.",
        ("bm25",),
    ),
    "claim-3": (
        "c2",
        "Reciprocal rank fusion combines the rankings of dense retrieval and BM25 without tuning weights.",
        ("rrf", "dense_retrieval", "bm25"),
    ),
    "claim-4": (
        "c2",
        "Reranking reorders the top passages with a slower and more accurate model.",
        ("reranking",),
    ),
    "claim-5": (
        "c3",
        "The SQuAD benchmark pairs questions with spans of Wikipedia passages.",
        ("squad",),
    ),
    "claim-6": (
        "c3",
        "Retrieval- augmented generation helps a model answer from outside text.",
        ("rag",),
    ),
    "claim-7": (
        "c1",
        "Dense retrieval needs an index of vectors built ahead of time for speed.",
        ("dense_retrieval",),
    ),
    "claim-8": (
        "c3",
        "Large language models are trained on text from the web and from books.",
        ("llm",),
    ),
}
METHODS = ["dense_retrieval", "bm25", "rrf", "reranking", "query_expansion"]


def page(pid: str, label: str, kind: str, chunks: tuple[str, ...]) -> ConceptPage:
    return ConceptPage(pid, label, (), (pid,), kind, ("d1",), chunks, ())


@pytest.fixture
def small(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "quiz.db"))
    for d, title in (("d1", "Paper One"), ("d2", "Paper Two")):
        docs.put_document(Document(d, title, f"{d}.pdf", "ready", 1, None, "2026-10-07"))
    docs.put_chunks([Chunk(c, DOC_OF[c], i, PAGE_OF[c], TEXT[c]) for i, c in enumerate(TEXT)])
    pages = [
        page("dense_retrieval", "dense retrieval", "method", ("c1", "c2")),
        page("bm25", "BM25", "method", ("c1", "c2")),
        page("rrf", "reciprocal rank fusion", "method", ("c2",)),
        page("reranking", "reranking", "method", ("c2",)),
        page("query_expansion", "query expansion", "method", ("c2",)),
        page("squad", "SQuAD", "dataset", ("c3",)),
        page("rag", "retrieval-augmented generation", "concept", ("c3",)),
        page("llm", "large language models", "concept", ("c3",)),
        page("lm", "language models", "concept", ("c3",)),
    ]
    claims = [ClaimNote(cid, c, DOC_OF[c], s, ids) for cid, (c, s, ids) in SENTENCES.items()]
    return Vault("vault-1", 3, {p.id: p for p in pages}, [], claims), docs


def h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def test_an_item_blanks_the_first_whole_word_occurrence_and_offers_three_fair_distractors(small):
    vault, docs = small
    item = derive_item(vault, docs, "claim-1~dense_retrieval")
    assert item is not None
    assert (
        item.text
        == "_____ finds passages by comparing embedding vectors of the query and the text."
    )
    assert item.quote == SENTENCES["claim-1"][1] and item.target == "dense_retrieval"
    others = sorted((m for m in METHODS if m != "dense_retrieval"), key=lambda p: h(item.id, p))
    assert set(item.options) == {"dense_retrieval", *others[:3]}
    assert list(item.options) == sorted(
        item.options, key=lambda p: h(item.id, "order", p)
    )  # a fixed, hashed order


def test_a_distractor_is_never_a_page_named_in_the_sentence_or_made_of_the_same_words(small):
    vault, docs = small
    item = derive_item(vault, docs, "claim-8~llm")
    assert (
        item is None
    )  # only "language models" shares the kind; its words are inside the target's, so it is not offered
    both = derive_item(vault, docs, "claim-3~dense_retrieval")
    assert both is None  # bm25 and rrf are in the sentence: two methods are left, not three


def test_the_quiz_takes_claims_in_claim_order_when_nothing_is_rated_one_item_per_page(small):
    vault, docs = small
    data = derive_quiz(vault, docs, None)
    assert data is not None
    # unrated pages all count 0.5: claim id order. claim-3 (two distractors), claim-5 (no other dataset) are passed over; claim-7
    # names the same page as claim-1 and is not an item (not a failure); claim-6 has no literal name and claim-8 no fair options
    assert [i["id"] for i in data["items"]] == [
        "claim-1~dense_retrieval",
        "claim-2~bm25",
        "claim-4~reranking",
    ]
    assert data["focusId"] is None
    assert (
        data["skipped"] == 1 + 2 + 1
    )  # claim-6 (no blank); claim-3, claim-5 (looked at); claim-8 (looked at)


def test_the_weakest_concepts_come_first(small):
    vault, docs = small
    mastery = {"reranking": MasteryScore(0.1, 2), "bm25": MasteryScore(0.9, 3)}
    data = derive_quiz(vault, docs, None, mastery)
    assert data is not None
    assert [i["id"] for i in data["items"]] == [
        "claim-4~reranking",
        "claim-1~dense_retrieval",
        "claim-2~bm25",
    ]


def test_a_quiz_about_one_page_uses_its_claims_and_blanks_that_page(small):
    vault, docs = small
    data = derive_quiz(vault, docs, "dense_retrieval")
    assert data is not None and data["focusId"] == "dense_retrieval"
    assert [i["id"] for i in data["items"]] == [
        "claim-1~dense_retrieval",
        "claim-7~dense_retrieval",
    ]
    assert data["skipped"] == 1  # claim-3 names it but has no fair distractors
    assert derive_quiz(vault, docs, "ghost") is None


def test_only_the_items_looked_at_are_counted_as_skipped(small, monkeypatch):
    vault, docs = small
    monkeypatch.setattr(quiz, "MAX_ITEMS", 2)
    data = derive_quiz(vault, docs, None)
    assert data is not None
    assert [i["id"] for i in data["items"]] == ["claim-1~dense_retrieval", "claim-2~bm25"]
    assert data["skipped"] == 1  # claim-6 has no literal name; claim-3 onwards were not looked at


def test_a_name_broken_by_a_hyphen_makes_no_item(small):
    vault, docs = small
    assert derive_item(vault, docs, "claim-6~rag") is None


def test_the_block_never_carries_the_answer_or_the_unblanked_sentence(small):
    vault, docs = small
    data = derive_quiz(vault, docs, None)
    assert data is not None
    for item in data["items"]:
        assert set(item) == {"id", "text", "options", "docTitle", "page"}
        assert all(set(o) == {"id", "label"} for o in item["options"]) and len(item["options"]) == 4
        assert "_____" in item["text"]
    first = data["items"][0]
    assert (first["docTitle"], first["page"]) == ("Paper One", 3)
    assert (
        "Dense retrieval" not in json.dumps(first)
        and "dense retrieval finds" not in json.dumps(first).lower()
    )


def test_it_is_deterministic_and_does_not_depend_on_the_order_of_pages_or_claims(small):
    vault, docs = small
    first = derive_quiz(vault, docs, None)
    reordered = Vault(
        vault.version,
        vault.n_chunks,
        dict(reversed(list(vault.pages.items()))),
        [],
        list(reversed(vault.claims)),
    )
    assert derive_quiz(reordered, docs, None) == first == derive_quiz(vault, docs, None)


def test_an_answer_is_checked_against_the_derived_item(small):
    vault, docs = small
    item = derive_item(vault, docs, "claim-2~bm25")
    assert item is not None
    right = check_answer(vault, docs, item.id, "bm25")
    assert right is not None and right.correct and right.item.target == "bm25"
    wrong = next(p for p in item.options if p != "bm25")
    result = check_answer(vault, docs, item.id, wrong)
    assert result is not None and not result.correct and result.item.target == "bm25"


@pytest.mark.parametrize(
    ("item_id", "chosen"),
    [
        ("claim-2~bm25", "squad"),  # not one of the four options
        ("claim-2~bm25", "ghost"),
        ("claim-2~dense_retrieval", "bm25"),  # the claim does not name that page
        ("claim-99~bm25", "bm25"),
        ("claim-2~", "bm25"),
        ("~bm25", "bm25"),
        ("claim-2", "bm25"),
        ("", ""),
    ],
)
def test_a_forged_item_or_choice_is_refused(small, item_id, chosen):
    vault, docs = small
    assert check_answer(vault, docs, item_id, chosen) is None


def test_the_source_is_the_unblanked_sentence_as_a_verbatim_citation(small):
    vault, docs = small
    item = derive_item(vault, docs, "claim-2~bm25")
    assert item is not None
    assert source_citation(docs, item) == {
        "id": "c1",
        "chunkId": "c1",
        "docId": "d1",
        "docTitle": "Paper One",
        "page": 3,
        "quote": SENTENCES["claim-2"][1],
    }
    assert SENTENCES["claim-2"][1] in TEXT["c1"]


def test_an_item_is_refused_when_the_passage_no_longer_holds_the_sentence(small):
    vault, docs = small
    changed = ClaimNote(
        "claim-2", "c1", "d1", "BM25 scores terms by a rule that is not in the passage.", ("bm25",)
    )
    vault.claims[1] = changed
    assert derive_item(vault, docs, "claim-2~bm25") is None


def test_no_claims_gives_an_empty_quiz(small):
    vault, docs = small
    bare = Vault(vault.version, vault.n_chunks, vault.pages, [], [])
    assert derive_quiz(bare, docs, None) == {"focusId": None, "items": [], "skipped": 0}
