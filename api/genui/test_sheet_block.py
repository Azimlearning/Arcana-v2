"""The `CheatSheet` block (D-43, V4): the validator by planted defects, the status rules, and the catalog and builder entries."""

import copy

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS, cheat_sheet
from api.genui.notes_catalog import CHEAT_SHEET, NOTES_CATALOG
from api.genui.validate import validate_block
from api.vault.sheet import derive_cheat_sheet, sheet_caps
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)


def block_of(vault, docs, focus="rrf", status="ready"):
    return cheat_sheet("sheet", status, data=derive_cheat_sheet(vault, docs, focus))


def test_a_derived_sheet_passes_the_validator(world):  # noqa: F811
    vault, docs = world
    block = validate_block(block_of(vault, docs), docs, vault=vault)
    assert block.type == "CheatSheet" and block.data.entries[0].pageId == "rrf"  # type: ignore[union-attr]


def test_a_sheet_is_refused_without_the_vault_it_is_checked_against(world):  # noqa: F811
    vault, docs = world
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault, docs), docs)


def _defects():
    def quote(d):
        d["citations"][0]["quote"] = "Reciprocal rank fusion is a method that no passage states in these words."

    def title(d):
        d["citations"][0]["docTitle"] = "Another paper"

    def page_number(d):
        d["citations"][0]["page"] = 99

    def chunk(d):
        d["citations"][0]["chunkId"] = "no-such-chunk"

    def entry_dropped(d):
        d["entries"].pop()

    def entry_added(d):
        d["entries"].append(copy.deepcopy(d["entries"][0]))

    def entry_label(d):
        d["entries"][0]["pageLabel"] = "Some other concept"

    def entry_kind(d):
        d["entries"][0]["kind"] = "dataset"

    def entry_sentence(d):
        d["entries"][0]["citationId"] = next(c["id"] for c in d["citations"] if c["id"] != d["entries"][0]["citationId"])

    def focus(d):
        d["focusId"] = "bm25"

    def edge_relation(d):
        d["edges"][0]["relation"] = "invented relation"

    def edge_added(d):
        d["edges"].append({"src": "bm25", "dst": "rrf", "relation": "made up"})

    def edge_dropped(d):
        d["edges"].pop()

    def skipped(d):
        d["skipped"] = 9

    def unknown_field(d):
        d["picture"] = "https://example.com/infographic.png"

    return [
        ("quote_not_verbatim", quote),
        ("title_changed", title),
        ("page_changed", page_number),
        ("chunk_missing", chunk),
        ("entry_dropped", entry_dropped),
        ("entry_added", entry_added),
        ("entry_label_changed", entry_label),
        ("entry_kind_changed", entry_kind),
        ("entry_sentence_swapped", entry_sentence),
        ("focus_changed", focus),
        ("edge_relation_invented", edge_relation),
        ("edge_added", edge_added),
        ("edge_dropped", edge_dropped),
        ("skipped_changed", skipped),
        ("unknown_field", unknown_field),
    ]


@pytest.mark.parametrize("name,apply", _defects(), ids=[n for n, _ in _defects()])
def test_every_planted_defect_is_refused(world, name, apply):  # noqa: F811
    vault, docs = world
    raw = block_of(vault, docs)
    validate_block(copy.deepcopy(raw), docs, vault=vault)  # the undamaged block is accepted
    apply(raw["data"])
    with pytest.raises(ValidationFailed):
        validate_block(raw, docs, vault=vault)


def test_the_status_rules(world):  # noqa: F811
    vault, docs = world
    ready = block_of(vault, docs)
    nothing = copy.deepcopy(ready)
    nothing["data"].update(entries=[], edges=[], citations=[])
    with pytest.raises(ValidationFailed):
        validate_block(nothing, docs, vault=vault)
    as_empty = copy.deepcopy(ready)
    as_empty["meta"]["status"] = "empty"
    with pytest.raises(ValidationFailed):
        validate_block(as_empty, docs, vault=vault)
    loading = copy.deepcopy(ready)
    loading["meta"]["status"] = "loading"
    with pytest.raises(ValidationFailed):
        validate_block(loading, docs, vault=vault)
    assert validate_block(cheat_sheet("sheet", "loading"), docs, vault=None).meta.status == "loading"


def test_the_catalog_builder_and_caps_agree():
    assert "CheatSheet" in NOTES_CATALOG and BUILDERS["CheatSheet"] is cheat_sheet
    assert CHEAT_SHEET.caps == sheet_caps() == {"entries": 8, "edges": 16, "citations": 8, "label_chars": 120}
    assert CHEAT_SHEET.fences.grounding == "vault_rederived" and CHEAT_SHEET.precondition.strip()
