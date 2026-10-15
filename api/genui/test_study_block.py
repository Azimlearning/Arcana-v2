"""The `StudySet` block (P5 S2, D-42): the validator by planted defects, and the catalog and builder entries.

The vault is the handmade one of `api/vault/test_study.py` (read its header for the expected sets). No model call anywhere.
"""

import copy

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS, study_set
from api.genui.notes_catalog import NOTES_CATALOG, STUDY_SET
from api.genui.validate import validate_block
from api.learner.mastery import MasteryScore
from api.vault.study import MAX_ITEMS, MAX_NOTES, STUDY_KINDS, StudyKind, derive_study_set
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)


def block_of(vault, docs, kind: StudyKind = "cornell", focus: str | None = "bm25", mastery=None, status="ready"):
    return study_set("study", status, data=derive_study_set(vault, docs, kind, focus, mastery))


def test_a_derived_set_of_every_kind_passes_the_validator(world):  # noqa: F811
    vault, docs = world
    for kind in STUDY_KINDS:
        focus = "rrf" if kind == "socratic" else "dense_retrieval"
        block = validate_block(block_of(vault, docs, kind, focus), docs, vault=vault)
        assert block.type == "StudySet" and block.data.kind == kind  # type: ignore[union-attr]
    unfocused = validate_block(block_of(vault, docs, "flashcard", None), docs, vault=vault)
    assert unfocused.data.focusId is None and len(unfocused.data.items) <= MAX_ITEMS  # type: ignore[union-attr]


def test_the_ordering_by_mastery_is_part_of_what_is_checked(world):  # noqa: F811
    vault, docs = world
    mastery = {"bm25": MasteryScore(0.9, 4), "dense_retrieval": MasteryScore(0.1, 3)}
    raw = block_of(vault, docs, "flashcard", None, mastery)
    assert validate_block(raw, docs, vault=vault, mastery=mastery).type == "StudySet"
    with pytest.raises(ValidationFailed):  # the same block is not what the vault derives for a learner who knows other things
        validate_block(raw, docs, vault=vault, mastery={"dense_retrieval": MasteryScore(0.95, 9)})


def test_a_set_is_refused_without_the_vault_it_is_checked_against(world):  # noqa: F811
    vault, docs = world
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault, docs), docs)


def _defects():
    def prompt(d):
        d["items"][0]["prompt"] = "What is BM25?"

    def hint_stating_the_answer(d):
        d["items"][0]["hint"] = d["citations"][0]["quote"]

    def prompt_stating_the_answer(d):
        d["items"][0]["prompt"] = d["citations"][0]["quote"]

    def note_swapped(d):
        d["items"][0]["notes"][0]["citationId"] = d["items"][0]["notes"][1]["citationId"]

    def note_added(d):
        d["items"][0]["notes"].append(copy.deepcopy(d["items"][0]["notes"][0]))

    def note_dropped(d):
        d["items"][0]["notes"].pop()

    def quote(d):
        d["citations"][0]["quote"] = "BM25 scores terms by an invented rule that no passage states."

    def title(d):
        d["citations"][0]["docTitle"] = "Another paper"

    def page_number(d):
        d["citations"][0]["page"] = 99

    def chunk(d):
        d["citations"][0]["chunkId"] = "no-such-chunk"

    def citation_added(d):
        d["citations"].append({**d["citations"][0], "id": "c99"})

    def item_id(d):
        d["items"][0]["id"] = "forged-id"

    def page_label(d):
        d["items"][0]["pageLabel"] = "Some other concept"

    def item_dropped(d):
        d["items"].pop()

    def item_added(d):
        d["items"].append(copy.deepcopy(d["items"][0]))

    def summary_removed(d):
        d["summary"] = None

    def summary_changed(d):
        d["summary"] = {"citationId": d["items"][0]["notes"][1]["citationId"]}  # a note that is not the definition

    def kind(d):
        d["kind"] = "flashcard"

    def focus(d):
        d["focusId"] = "dense_retrieval"

    def skipped(d):
        d["skipped"] = 7

    def unknown_field(d):
        d["answer"] = "BM25"

    return [
        ("prompt_changed", prompt),
        ("hint_states_what_it_withholds", hint_stating_the_answer),
        ("prompt_states_what_it_withholds", prompt_stating_the_answer),
        ("note_swapped", note_swapped),
        ("note_added", note_added),
        ("note_dropped", note_dropped),
        ("quote_not_verbatim", quote),
        ("title_changed", title),
        ("page_changed", page_number),
        ("chunk_missing", chunk),
        ("citation_added", citation_added),
        ("item_id_forged", item_id),
        ("page_label_changed", page_label),
        ("item_dropped", item_dropped),
        ("item_added", item_added),
        ("summary_removed", summary_removed),
        ("summary_changed", summary_changed),
        ("kind_switched", kind),
        ("focus_changed", focus),
        ("skipped_changed", skipped),
        ("unknown_field", unknown_field),
    ]


@pytest.mark.parametrize("name,apply", _defects(), ids=[n for n, _ in _defects()])
def test_every_planted_defect_is_refused(world, name, apply):  # noqa: F811
    vault, docs = world
    raw = block_of(vault, docs, "cornell", "bm25")
    validate_block(copy.deepcopy(raw), docs, vault=vault)  # the undamaged block is accepted
    apply(raw["data"])
    with pytest.raises(ValidationFailed):
        validate_block(raw, docs, vault=vault)


def test_the_status_rules(world):  # noqa: F811
    vault, docs = world
    ready = block_of(vault, docs, "flashcard", "dense_retrieval")
    ready_empty = copy.deepcopy(ready)
    ready_empty["data"].update(items=[], citations=[], summary=None)
    with pytest.raises(ValidationFailed):  # ready with nothing in it
        validate_block(ready_empty, docs, vault=vault)
    as_empty = copy.deepcopy(ready)
    as_empty["meta"]["status"] = "empty"  # the vault can make items here: it must not claim otherwise
    with pytest.raises(ValidationFailed):
        validate_block(as_empty, docs, vault=vault)
    loading = copy.deepcopy(ready)
    loading["meta"]["status"] = "loading"  # a placeholder carries nothing
    with pytest.raises(ValidationFailed):
        validate_block(loading, docs, vault=vault)
    blank = study_set("study", "loading", kind="flashcard")
    assert validate_block(blank, docs, vault=None).meta.status == "loading"


def test_the_nothing_to_show_case_is_an_empty_block_the_vault_agrees_with(world):  # noqa: F811
    vault, docs = world
    data = derive_study_set(vault, docs, "flashcard", "lm")
    assert data is not None and data["items"] == []
    block = validate_block(study_set("study", "empty", data=data), docs, vault=vault)
    assert block.meta.status == "empty" and block.data.skipped == 1  # type: ignore[union-attr]


def test_the_catalog_builder_and_caps_agree():
    assert "StudySet" in NOTES_CATALOG and BUILDERS["StudySet"] is study_set
    assert STUDY_SET.caps == {"items": MAX_ITEMS, "notes": MAX_NOTES, "label_chars": 120}
    assert STUDY_SET.fences.grounding == "vault_rederived" and STUDY_SET.precondition.strip()
