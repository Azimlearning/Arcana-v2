"""The cheat sheet (D-43, V4): the derivation by properties over the handmade vault of `api/vault/test_study.py`. No model call."""

from api.genui.text import normalise
from api.vault.sheet import MAX_EDGES, MAX_ENTRIES, default_focus, derive_cheat_sheet
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)


def test_an_unknown_or_missing_focus_is_no_sheet(world):  # noqa: F811
    vault, docs = world
    assert derive_cheat_sheet(vault, docs, "ghost") is None
    assert derive_cheat_sheet(vault, docs, None) is None


def test_the_focus_comes_first_with_its_neighbours_and_the_links_between_them(world):  # noqa: F811
    vault, docs = world
    data = derive_cheat_sheet(vault, docs, "rrf")
    assert data is not None and data["focusId"] == "rrf"
    ids = [e["pageId"] for e in data["entries"]]
    assert ids[0] == "rrf" and "dense_retrieval" in ids and len(ids) == len(set(ids))
    link = next(e for e in data["edges"] if {e["src"], e["dst"]} == {"rrf", "dense_retrieval"})
    assert link["relation"] == "combines"  # the asserted relation is preferred over a co-mention
    assert all(e["src"] in ids and e["dst"] in ids for e in data["edges"])  # an edge joins two entries on the sheet


def test_every_sentence_is_a_verbatim_cited_span_of_a_stored_passage(world):  # noqa: F811
    vault, docs = world
    data = derive_cheat_sheet(vault, docs, "rrf")
    assert data is not None
    used = {e["citationId"] for e in data["entries"]}
    assert used == {c["id"] for c in data["citations"]}
    for c in data["citations"]:
        assert normalise(c["quote"]) in normalise(docs.get_chunks([c["chunkId"]])[c["chunkId"]].text)


def test_it_is_capped_deterministic_and_counts_what_it_passed_over(world):  # noqa: F811
    vault, docs = world
    first = derive_cheat_sheet(vault, docs, "rrf")
    assert first == derive_cheat_sheet(vault, docs, "rrf")
    assert first is not None and len(first["entries"]) <= MAX_ENTRIES and len(first["edges"]) <= MAX_EDGES
    assert first["skipped"] >= 0


def test_a_page_with_no_citable_sentence_gives_an_empty_sheet_not_an_error(world):  # noqa: F811
    vault, docs = world
    vault.claims.clear()
    data = derive_cheat_sheet(vault, docs, "lm")  # a page no sentence defines once the claims are gone
    assert data is not None and data["entries"] == [] and data["skipped"] >= 1


def test_the_default_focus_is_a_connected_page_that_has_something_citable(world):  # noqa: F811
    vault, _ = world
    page_id = default_focus(vault)
    assert page_id is not None and (vault.pages[page_id].definitions or vault.claims_of(page_id))
