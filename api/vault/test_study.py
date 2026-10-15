"""Study sets from the vault (P5 S2, D-42): every expected value is worked out by hand from the handmade vault of `test_quiz.py`, with
two additions made here: a stored definition for two pages and one asserted link (reciprocal rank fusion combines dense retrieval).

By hand, with the quiz's vault (passages c1, c2, c3; claims 1 to 8) plus:
    definition of dense_retrieval  c1  "Dense retrieval finds passages by comparing embedding vectors of the query and the text."
    definition of bm25             c1  "BM25 scores terms by their frequency in a passage and their rarity across the corpus."
    link rrf -> dense_retrieval    asserted, "combines", evidenced by the c2 sentence "Reciprocal rank fusion combines the rankings of
                                   dense retrieval and BM25 without tuning weights."
"""

from dataclasses import replace
from pathlib import Path

import pytest

from api.learner.mastery import MasteryScore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.study import MAX_ITEMS, STUDY_KINDS, derive_study_set
from api.vault.test_quiz import SENTENCES, fill
from api.vault.types import Definition, PageLink

DEF_DENSE = SENTENCES["claim-1"][1]
DEF_BM25 = SENTENCES["claim-2"][1]
LINK_SENTENCE = SENTENCES["claim-3"][1]


@pytest.fixture
def world(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "study.db"))
    vault = fill(docs)
    vault.pages["dense_retrieval"] = replace(vault.pages["dense_retrieval"], definitions=(Definition(DEF_DENSE, "c1", "d1"),))
    vault.pages["bm25"] = replace(vault.pages["bm25"], definitions=(Definition(DEF_BM25, "c1", "d1"),))
    vault.links.append(PageLink("rrf", "dense_retrieval", "asserted", "combines", ("c2",), LINK_SENTENCE))
    vault.__post_init__()
    return vault, docs


def quotes_of(data) -> list[str]:
    by_id = {c["id"]: c["quote"] for c in data["citations"]}
    return [by_id[n["citationId"]] for item in data["items"] for n in item["notes"]]


def test_a_flashcard_is_the_pages_name_and_its_definition(world):
    vault, docs = world
    data = derive_study_set(vault, docs, "flashcard", "dense_retrieval")
    assert data is not None and data["kind"] == "flashcard" and data["focusId"] == "dense_retrieval"
    assert [(i["prompt"], i["pageId"], i["hint"]) for i in data["items"]] == [("dense retrieval", "dense_retrieval", None)]
    assert quotes_of(data) == [DEF_DENSE]
    assert data["summary"] is None and data["skipped"] == 0


def test_a_flashcard_falls_back_to_a_claim_when_the_page_has_no_definition(world):
    vault, docs = world
    data = derive_study_set(vault, docs, "flashcard", "reranking")
    assert data is not None and quotes_of(data) == [SENTENCES["claim-4"][1]]


def test_blurting_reveals_the_definition_then_claims_and_dedupes(world):
    vault, docs = world
    data = derive_study_set(vault, docs, "blurt", "dense_retrieval")
    assert data is not None
    (item,) = data["items"]
    assert item["prompt"].startswith("Write down what you remember about dense retrieval")
    # the definition equals claim-1's sentence, so it is shown once; then the page's other claims in (document, passage) order: claim-7 (c1), claim-3 (c2)
    assert quotes_of(data) == [DEF_DENSE, SENTENCES["claim-7"][1], SENTENCES["claim-3"][1]]


def test_cornell_notes_are_claims_first_with_the_definition_as_the_summary(world):
    vault, docs = world
    data = derive_study_set(vault, docs, "cornell", "bm25")
    assert data is not None
    (item,) = data["items"]
    assert item["prompt"] == "What do your documents state about BM25?"
    assert quotes_of(data) == [SENTENCES["claim-2"][1], SENTENCES["claim-3"][1]]  # claim-2 (c1) then claim-3 (c2); the definition equals claim-2
    summary_cid = data["summary"]["citationId"]
    assert next(c["quote"] for c in data["citations"] if c["id"] == summary_cid) == DEF_BM25


def test_a_socratic_item_asks_about_a_link_and_points_at_the_source_without_stating_it(world):
    vault, docs = world
    data = derive_study_set(vault, docs, "socratic", "rrf")
    assert data is not None
    (item,) = data["items"]
    assert item["prompt"] == "How do reciprocal rank fusion and dense retrieval relate? Say it in your own words, then check."
    assert item["hint"] == "Look at Paper Two, page 5."
    assert quotes_of(data) == [LINK_SENTENCE]
    assert "combines" not in item["prompt"] and "combines" not in (item["hint"] or "")


def test_without_a_focus_pages_come_least_known_first_and_the_set_is_capped(world):
    vault, docs = world
    mastery = {"bm25": MasteryScore(0.9, 4), "dense_retrieval": MasteryScore(0.1, 3)}
    data = derive_study_set(vault, docs, "flashcard", None, mastery)
    assert data is not None and data["focusId"] is None
    labels = [i["pageLabel"] for i in data["items"]]
    assert len(labels) <= MAX_ITEMS
    assert labels[0] == "dense retrieval"  # the page the learner knows least comes first
    assert "BM25" not in labels  # and the one known well is pushed past the cap of five


def test_an_unknown_focus_is_none_and_a_page_with_nothing_citable_is_counted_not_shown(world):
    vault, docs = world
    assert derive_study_set(vault, docs, "flashcard", "no-such-page") is None
    data = derive_study_set(vault, docs, "flashcard", "lm")  # no definition and no claim names it
    assert data is not None and data["items"] == [] and data["skipped"] == 1


@pytest.mark.parametrize("kind", STUDY_KINDS)
def test_no_prompt_or_hint_ever_holds_a_sentence_it_withholds(world, kind):
    vault, docs = world
    for focus in (None, "dense_retrieval", "bm25", "rrf", "reranking"):
        data = derive_study_set(vault, docs, kind, focus)
        assert data is not None
        by_id = {c["id"]: c["quote"].lower() for c in data["citations"]}
        for item in data["items"]:
            for text in (item["prompt"], item["hint"] or ""):
                for note in item["notes"]:
                    assert by_id[note["citationId"]] not in " ".join(text.lower().split())


@pytest.mark.parametrize("kind", STUDY_KINDS)
def test_a_set_is_deterministic_and_every_citation_is_a_verbatim_stored_span(world, kind):
    vault, docs = world
    a = derive_study_set(vault, docs, kind, "dense_retrieval")
    b = derive_study_set(vault, docs, kind, "dense_retrieval")
    assert a == b
    assert a is not None
    stored = docs.get_chunks([c["chunkId"] for c in a["citations"]])
    for c in a["citations"]:
        assert " ".join(c["quote"].split()) in " ".join(stored[c["chunkId"]].text.split())
        assert c["docTitle"] in ("Paper One", "Paper Two")
