"""The `DocBrief` block (D-43, V3): the validator by planted defects, the status rules, and the catalog and builder entries.

The vault is the handmade one of `api/vault/test_study.py`. No model call anywhere.
"""

import copy

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS, doc_brief
from api.genui.notes_catalog import DOC_BRIEF, NOTES_CATALOG
from api.genui.validate import validate_block
from api.learner.mastery import MasteryScore
from api.vault.brief import brief_caps, derive_doc_brief
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)

MASTERY = {"bm25": MasteryScore(0.1, 3), "dense_retrieval": MasteryScore(0.9, 5)}


def block_of(vault, docs, doc_id="d1", mastery=MASTERY, status="ready"):
    return doc_brief("brief", status, data=derive_doc_brief(vault, docs, doc_id, mastery))


def test_a_derived_brief_passes_the_validator(world):  # noqa: F811
    vault, docs = world
    block = validate_block(block_of(vault, docs), docs, vault=vault, mastery=MASTERY)
    assert block.type == "DocBrief" and block.data.docId == "d1"  # type: ignore[union-attr]


def test_a_brief_is_refused_without_the_vault_it_is_checked_against(world):  # noqa: F811
    vault, docs = world
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault, docs), docs, mastery=MASTERY)


def test_the_learners_mastery_is_part_of_what_is_checked(world):  # noqa: F811
    vault, docs = world
    raw = block_of(vault, docs)
    with pytest.raises(ValidationFailed):  # the next steps are not what the vault derives for a learner who rated other things
        validate_block(raw, docs, vault=vault, mastery={"bm25": MasteryScore(0.95, 9)})


def _defects():
    def point_quote(d):
        d["citations"][0]["quote"] = "BM25 is the best method ever invented, a claim no passage makes."

    def doc_title(d):
        d["docTitle"] = "Another paper"

    def doc_id(d):
        d["docId"] = "d2"

    def citation_page(d):
        d["citations"][0]["page"] = 99

    def citation_chunk(d):
        d["citations"][0]["chunkId"] = "no-such-chunk"

    def citation_other_doc(d):
        d["citations"][0]["docId"] = "d2"

    def point_dropped(d):
        d["keyPoints"].pop()

    def point_added(d):
        d["keyPoints"].append(copy.deepcopy(d["keyPoints"][0]))

    def point_label(d):
        d["keyPoints"][0]["pageLabels"] = ["a concept the sentence does not name"]

    def term_swapped(d):
        d["terms"][0]["citationId"] = next(c["id"] for c in d["citations"] if c["id"] != d["terms"][0]["citationId"])

    def term_label(d):
        d["terms"][0]["pageLabel"] = "BM25 (renamed)"

    def action_added(d):
        d["actions"].insert(0, {"kind": "review", "pageId": "bm25", "pageLabel": "BM25", "reason": "Because I said so."})

    def action_reason(d):
        d["actions"][0]["reason"] = "You should read this now."

    def action_kind(d):
        d["actions"][0]["kind"] = "learn"

    def action_dropped(d):
        d["actions"].pop()

    def claims_count(d):
        d["claimsInDocument"] = 99

    def left_out(d):
        d["leftOut"] = 7

    def unknown_field(d):
        d["summary"] = "A model-written summary."

    return [
        ("quote_not_verbatim", point_quote),
        ("doc_title_changed", doc_title),
        ("doc_changed", doc_id),
        ("page_number_changed", citation_page),
        ("chunk_missing", citation_chunk),
        ("citation_from_another_document", citation_other_doc),
        ("key_point_dropped", point_dropped),
        ("key_point_added", point_added),
        ("concepts_named_changed", point_label),
        ("term_definition_swapped", term_swapped),
        ("term_label_changed", term_label),
        ("next_step_added", action_added),
        ("next_step_reason_changed", action_reason),
        ("next_step_kind_changed", action_kind),
        ("next_step_dropped", action_dropped),
        ("claim_count_changed", claims_count),
        ("left_out_changed", left_out),
        ("unknown_field", unknown_field),
    ]


@pytest.mark.parametrize("name,apply", _defects(), ids=[n for n, _ in _defects()])
def test_every_planted_defect_is_refused(world, name, apply):  # noqa: F811
    vault, docs = world
    raw = block_of(vault, docs)
    validate_block(copy.deepcopy(raw), docs, vault=vault, mastery=MASTERY)  # the undamaged block is accepted
    apply(raw["data"])
    with pytest.raises(ValidationFailed):
        validate_block(raw, docs, vault=vault, mastery=MASTERY)


def test_the_status_rules(world):  # noqa: F811
    vault, docs = world
    ready = block_of(vault, docs)
    nothing = copy.deepcopy(ready)
    nothing["data"].update(keyPoints=[], terms=[], actions=[], citations=[])
    with pytest.raises(ValidationFailed):  # ready with nothing in it
        validate_block(nothing, docs, vault=vault, mastery=MASTERY)
    as_empty = copy.deepcopy(ready)
    as_empty["meta"]["status"] = "empty"  # the vault holds material: it must not claim otherwise
    with pytest.raises(ValidationFailed):
        validate_block(as_empty, docs, vault=vault, mastery=MASTERY)
    loading = copy.deepcopy(ready)
    loading["meta"]["status"] = "loading"  # a placeholder carries nothing
    with pytest.raises(ValidationFailed):
        validate_block(loading, docs, vault=vault, mastery=MASTERY)
    blank = doc_brief("brief", "loading")
    assert validate_block(blank, docs, vault=None).meta.status == "loading"


def test_an_unknown_document_is_refused(world):  # noqa: F811
    vault, docs = world
    raw = block_of(vault, docs)
    raw["data"]["docId"] = "ghost"
    with pytest.raises(ValidationFailed):
        validate_block(raw, docs, vault=vault, mastery=MASTERY)


def test_the_catalog_builder_and_caps_agree():
    assert "DocBrief" in NOTES_CATALOG and BUILDERS["DocBrief"] is doc_brief
    assert DOC_BRIEF.caps == brief_caps() == {"key_points": 6, "terms": 6, "actions": 4, "citations": 12, "label_chars": 120}
    assert DOC_BRIEF.fences.grounding == "vault_rederived" and DOC_BRIEF.precondition.strip()
