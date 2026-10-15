"""The document brief (D-43, V3): the derivation by properties over the handmade vault of `api/vault/test_study.py` (its `world`
fixture: documents d1 (passages c1, c3) and d2 (c2); definitions for dense_retrieval and bm25 in d1). No model call anywhere.
"""

import pytest

from api.genui.text import normalise
from api.learner.mastery import MasteryScore
from api.stores.doc_store import DocStore
from api.vault.brief import (
    MAX_ACTIONS,
    MAX_POINTS,
    MAX_TERMS,
    REVIEW_BELOW,
    default_doc_id,
    derive_doc_brief,
)
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)


def _passage_text(docs: DocStore, citation: dict) -> str:
    return normalise(docs.get_chunks([citation["chunkId"]])[citation["chunkId"]].text)


def test_the_default_document_is_the_one_with_most_claims(world):  # noqa: F811
    vault, _ = world
    counts: dict[str, int] = {}
    for claim in vault.claims:
        counts[claim.doc_id] = counts.get(claim.doc_id, 0) + 1
    assert default_doc_id(vault) == sorted(counts, key=lambda d: (-counts[d], d))[0]


def test_no_such_document_is_no_brief(world):  # noqa: F811
    vault, docs = world
    assert derive_doc_brief(vault, docs, "ghost") is None


def test_every_sentence_is_a_verbatim_cited_span_of_this_document(world):  # noqa: F811
    vault, docs = world
    for doc_id in ("d1", "d2"):
        data = derive_doc_brief(vault, docs, doc_id)
        assert data is not None and data["docId"] == doc_id
        by_id = {c["id"]: c for c in data["citations"]}
        used = [p["citationId"] for p in data["keyPoints"]] + [t["citationId"] for t in data["terms"]]
        assert used and set(used) == set(by_id), "every citation is used, and every use is a citation"
        for citation in by_id.values():
            assert citation["docId"] == doc_id  # a brief of one document shows no other document's sentence
            assert normalise(citation["quote"]) in _passage_text(docs, citation)


def test_it_is_capped_and_says_how_much_it_left_out(world):  # noqa: F811
    vault, docs = world
    data = derive_doc_brief(vault, docs, "d1")
    assert data is not None
    assert len(data["keyPoints"]) <= MAX_POINTS and len(data["terms"]) <= MAX_TERMS and len(data["actions"]) <= MAX_ACTIONS
    assert data["claimsInDocument"] == sum(1 for c in vault.claims if c.doc_id == "d1")
    assert data["leftOut"] >= 0


def test_key_terms_are_the_pages_the_document_defines(world):  # noqa: F811
    vault, docs = world
    data = derive_doc_brief(vault, docs, "d1")
    assert data is not None
    assert {t["pageId"] for t in data["terms"]} == {"dense_retrieval", "bm25"}
    assert derive_doc_brief(vault, docs, "d2")["terms"] == []  # type: ignore[index]  # d2 defines nothing


def test_next_steps_follow_the_mastery_rule_and_end_with_a_quiz(world):  # noqa: F811
    vault, docs = world
    unrated = derive_doc_brief(vault, docs, "d1", None)
    assert unrated is not None
    kinds = [a["kind"] for a in unrated["actions"]]
    assert kinds[:-1] == ["learn"] * (len(kinds) - 1) and kinds[-1] == "quiz"
    mastery = {"bm25": MasteryScore(0.1, 3), "dense_retrieval": MasteryScore(0.9, 5)}
    rated = derive_doc_brief(vault, docs, "d1", mastery)
    assert rated is not None
    steps = [(a["kind"], a["pageId"]) for a in rated["actions"]]
    assert steps[0] == ("review", "bm25")  # rated under the threshold: review, weakest first
    assert ("review", "dense_retrieval") not in steps and ("learn", "dense_retrieval") not in steps  # known well: left alone
    assert steps[-1][0] == "quiz"
    assert all(a["reason"] for a in rated["actions"])
    assert REVIEW_BELOW == 0.5


def test_the_same_inputs_give_the_same_brief(world):  # noqa: F811
    vault, docs = world
    assert derive_doc_brief(vault, docs, "d1") == derive_doc_brief(vault, docs, "d1")


@pytest.mark.parametrize("doc_id", ["d1", "d2"])
def test_a_document_with_nothing_citable_gives_an_empty_brief_not_an_error(world, doc_id):  # noqa: F811
    vault, docs = world
    vault.claims.clear()
    for page_id, page in list(vault.pages.items()):
        vault.pages[page_id] = type(page)(**{**page.__dict__, "definitions": ()})
    data = derive_doc_brief(vault, docs, doc_id)
    assert data is not None and not data["keyPoints"] and not data["terms"] and data["claimsInDocument"] == 0
