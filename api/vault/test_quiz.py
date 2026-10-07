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


def fill(docs) -> Vault:
    """Put the two documents and three passages into `docs` and return the handmade vault over them."""
    for d, title in (("d1", "Paper One"), ("d2", "Paper Two")):
        docs.put_document(Document(d, title, f"{d}.pdf", "ready", 1, None, "2026-10-07"))
    docs.put_chunks([Chunk(c, DOC_OF[c], i, PAGE_OF[c], TEXT[c]) for i, c in enumerate(TEXT)])
    pages = [
        page("dense_retrieval", "dense retrieval", "method", ("c1", "c2")),
        page("bm25", "BM25", "method", ("c1", "c2")),
        page("rrf", "reciprocal rank fusion", "method", ("c2", "c3")),
        page("reranking", "reranking", "method", ("c2", "c3")),
        page("query_expansion", "query expansion", "method", ("c2", "c3")),
        page("squad", "SQuAD", "dataset", ("c3", "c1")),
        page("rag", "retrieval-augmented generation", "concept", ("c3", "c1")),
        page("llm", "large language models", "concept", ("c3", "c1")),
        page("lm", "language models", "concept", ("c3", "c1")),
    ]
    claims = [ClaimNote(cid, c, DOC_OF[c], s, ids) for cid, (c, s, ids) in SENTENCES.items()]
    return Vault("vault-1", 3, {p.id: p for p in pages}, [], claims)


@pytest.fixture
def small(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "quiz.db"))
    return fill(docs), docs


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
    # unrated pages all count 0.5: claim id order. Every page has two passages, so claim-3's three pages tie on specificity and the
    # smaller id (bm25) is its target, which already has an item (claim-2): it is not an item and not a failure. claim-7 names
    # the same page as claim-1 and likewise. claim-5 (no other dataset) and claim-8 (no three other concepts) are looked at
    # and passed over; claim-6 has no literal name.
    assert [i["id"] for i in data["items"]] == [
        "claim-1~dense_retrieval",
        "claim-2~bm25",
        "claim-4~reranking",
    ]
    assert data["focusId"] is None
    assert data["skipped"] == 1 + 2  # claim-6 (no blank); claim-5 and claim-8 (looked at)


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


def test_a_one_off_mention_and_a_paper_title_are_never_offered_as_wrong_answers(small):
    vault, docs = small
    extra = [
        page("once", "one-off method", "method", ("c1",)),  # a single passage
        page(
            "long", "A method whose name runs to seven words", "method", ("c1", "c2")
        ),  # reads as a title
        page("colon", "Retrieval: a survey", "method", ("c1", "c2")),
        page("ask", "Which method is best?", "method", ("c1", "c2")),
    ]
    wider = Vault(
        vault.version, vault.n_chunks, {**vault.pages, **{p.id: p for p in extra}}, [], vault.claims
    )
    for claim in ("claim-1~dense_retrieval", "claim-2~bm25", "claim-4~reranking"):
        item = derive_item(wider, docs, claim)
        assert item is not None
        assert set(item.options) <= set(METHODS), (
            f"{claim} offered {set(item.options) - set(METHODS)}"
        )
    # they can still be the answer: a claim naming such a page blanks it, whatever its name looks like
    claims = [
        *vault.claims,
        ClaimNote(
            "claim-9",
            "c1",
            "d1",
            SENTENCES["claim-2"][1].replace("BM25", "one-off method"),
            ("once",),
        ),
    ]
    docs.put_chunks(
        [Chunk("c1", "d1", 0, 3, TEXT["c1"].replace("BM25 scores", "one-off method scores"))]
    )
    again = Vault(vault.version, vault.n_chunks, wider.pages, [], claims)
    target = derive_item(again, docs, "claim-9~once")
    assert target is not None and target.target == "once" and "_____ scores terms" in target.text


def test_a_hyphen_is_a_space_when_names_are_compared_for_the_same_words(small):
    vault, _ = small
    extra = [
        page(
            "rag_plain", "Retrieval Augmented Generation", "concept", ("c1", "c2")
        ),  # the same words as the target's
        page(
            "rag_active", "Active retrieval-augmented generation", "concept", ("c1", "c2")
        ),  # the target's words inside it
    ]
    wider = Vault(
        vault.version, vault.n_chunks, {**vault.pages, **{p.id: p for p in extra}}, [], vault.claims
    )
    chosen = quiz._distractors(
        wider, wider.pages["rag"], "A sentence that names none of them at all here.", "claim-x~rag"
    )
    assert sorted(chosen) == [
        "llm",
        "lm",
    ]  # neither spelling of the answer is offered as a wrong answer


# ── the answer must not show in the blanked sentence or the title (schema-guardian, Q1.4) ──────────────────────────────


def _every_item(vault, docs):
    for claim in vault.claims:
        for page_id in claim.page_ids:
            item = derive_item(vault, docs, f"{claim.id}~{page_id}")
            if item is not None:
                yield item


def test_no_name_of_the_blanked_page_is_left_in_any_item(small):
    from api.vault.text import fold, occurs

    vault, docs = small
    items = list(_every_item(vault, docs))
    assert items  # the corpus-level check is not vacuous
    for item in items:
        page = vault.pages[item.target]
        names = [fold(n) for n in [page.label, *page.aliases] if n]
        assert not any(occurs(fold(item.text), n) for n in names), item.text


def test_every_occurrence_of_every_name_is_blanked_and_a_title_that_gives_it_away_is_left_out(
    small,
):
    vault, docs = small
    pages = dict(vault.pages)
    pages["bm25"] = ConceptPage(
        "bm25", "BM25", ("Okapi BM25",), ("bm25",), "method", ("d1",), ("c1", "c2"), ()
    )
    sentence = (
        "BM25 ranks by term statistics, and Okapi BM25 is the usual form of bm25 in search engines."
    )
    claim = ClaimNote("claim-9", "c1", "d1", sentence, ("bm25",))
    docs.put_chunks([Chunk("c1", "d1", 0, 3, TEXT["c1"] + " " + sentence)])
    docs.put_document(
        Document(
            "d1", "Dense retrieval and BM25 in practice", "d1.pdf", "ready", 1, None, "2026-10-07"
        )
    )
    world = Vault(vault.version, vault.n_chunks, pages, [], [*vault.claims, claim])
    item = derive_item(world, docs, "claim-9~bm25")
    assert item is not None
    assert (
        item.text
        == "_____ ranks by term statistics, and _____ is the usual form of _____ in search engines."
    )
    data = derive_quiz(world, docs, "bm25")
    assert data is not None and data["items"]
    assert {i["docTitle"] for i in data["items"]} == {""}  # the title holds the words "BM25"
    other = derive_quiz(world, docs, "dense_retrieval")
    assert other is not None and {i["docTitle"] for i in other["items"]} == {
        ""
    }  # and "dense retrieval"
    docs.put_document(Document("d1", "Paper One", "d1.pdf", "ready", 1, None, "2026-10-07"))
    assert {i["docTitle"] for i in derive_quiz(world, docs, "bm25")["items"]} == {"Paper One"}  # type: ignore[index]


def test_a_sentence_that_already_holds_a_blank_makes_no_item(small):
    vault, docs = small
    quote = "BM25 fills a _____ in the sentence that is already there for another reason."
    docs.put_chunks([Chunk("c1", "d1", 0, 3, TEXT["c1"] + " " + quote)])
    claim = ClaimNote("claim-9", "c1", "d1", quote, ("bm25",))
    world = Vault(vault.version, vault.n_chunks, vault.pages, [], [claim])
    assert derive_item(world, docs, "claim-9~bm25") is None
