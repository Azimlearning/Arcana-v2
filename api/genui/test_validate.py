"""validate_block fails closed, and names the field path of every violation."""

import copy

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import cited_summary
from api.genui.generated import ErrorEnvelope
from api.genui.validate import validate_block


@pytest.fixture
def ctx(ingested):
    """(docs, a stored chunk, a valid ready-block dict citing it)."""
    deps, result = ingested
    chunk = deps.docs.chunks_for_document(result.doc_id)[1]
    quote = " ".join(chunk.text.split())[:120]
    data = {
        "segments": [{"text": "An answer.", "citationIds": ["c1"]}],
        "citations": [
            {
                "id": "c1",
                "chunkId": chunk.id,
                "docId": chunk.doc_id,
                "docTitle": "Hybrid Retrieval over Knowledge Graphs",
                "page": chunk.page,
                "quote": quote,
            }
        ],
    }
    return deps.docs, chunk, cited_summary("b1", "ready", data=data)


def paths(exc: ValidationFailed) -> list[str]:
    return [i.path for i in exc.issues]


def fails(raw, docs) -> ValidationFailed:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs)
    assert exc.value.to_envelope().code == "validation_failed"
    return exc.value


def test_a_grounded_ready_block_passes(ctx):
    docs, _, raw = ctx
    assert validate_block(raw, docs).id == "b1"


# ── schema layer ──────────────────────────────────────────────────────────────


def test_a_malformed_block_is_rejected_with_its_field_path(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"][0]["page"] = "1"  # a string where an int is declared: no coercion
    assert paths(fails(raw, docs)) == ["data.citations.0.page"]


def test_every_violation_is_reported_not_just_the_first(ctx):
    docs, _, raw = ctx
    raw["meta"]["status"] = "great"
    raw["data"]["citations"][0]["page"] = "3"
    raw["surprise"] = True
    assert sorted(paths(fails(raw, docs))) == sorted(["meta.status", "data.citations.0.page", "surprise"])


def test_a_missing_field_and_a_wrong_type_tag_are_located(ctx):
    docs, _, raw = ctx
    del raw["data"]
    assert paths(fails(raw, docs)) == ["data"]
    raw = cited_summary("b", "ready")
    raw["type"] = "NoSuchBlock"
    assert paths(fails(raw, docs)) == ["type"]


def test_an_empty_block_is_rejected_not_crashed():
    with pytest.raises(ValidationFailed):
        validate_block({}, docs=None)  # pyright: ignore[reportArgumentType]


def test_schema_failure_never_reaches_the_content_rules(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"][0]["page"] = 1.5
    assert all(not p.startswith("data.segments") for p in paths(fails(raw, docs)))


# ── content rules ─────────────────────────────────────────────────────────────


def test_error_status_and_error_envelope_go_together(ctx):
    docs, _, _ = ctx
    envelope = ErrorEnvelope(code="internal", message="m", issues=[], retryable=False)
    assert validate_block(cited_summary("b", "error", error=envelope), docs).meta.status == "error"

    no_reason = cited_summary("b", "error")
    assert paths(fails(no_reason, docs)) == ["meta.error"]

    stray = cited_summary("b", "empty")
    stray["meta"]["error"] = envelope.model_dump()
    assert paths(fails(stray, docs)) == ["meta.error"]


@pytest.mark.parametrize("status", ["empty", "loading", "error"])
def test_placeholder_statuses_carry_no_content(ctx, status):
    docs, _, ready = ctx
    raw = cited_summary("b", status, data=ready["data"])
    if status == "error":
        raw["meta"]["error"] = ErrorEnvelope(code="internal", message="m", issues=[], retryable=False).model_dump()
    assert "data" in paths(fails(raw, docs))


def test_a_ready_block_needs_content(ctx):
    docs, _, _ = ctx
    assert paths(fails(cited_summary("b", "ready"), docs)) == ["data.segments"]


def test_a_segment_must_cite_something_that_exists_in_the_block(ctx):
    docs, _, raw = ctx
    raw["data"]["segments"].append({"text": "Uncited claim.", "citationIds": []})
    raw["data"]["segments"].append({"text": "Bad cite.", "citationIds": ["c1", "c9"]})
    assert paths(fails(raw, docs)) == [
        "data.segments.1.citationIds",
        "data.segments.2.citationIds.1",
    ]


def test_citation_ids_must_be_unique(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"].append(copy.deepcopy(raw["data"]["citations"][0]))
    assert "data.citations" in paths(fails(raw, docs))


def test_a_citation_must_resolve_to_a_stored_chunk(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"][0]["chunkId"] = "no_such_chunk"
    assert paths(fails(raw, docs)) == ["data.citations.0.chunkId"]


def test_a_citation_must_name_the_chunks_own_document(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"][0]["docId"] = "some_other_doc"
    assert paths(fails(raw, docs)) == ["data.citations.0.docId"]


def test_a_quote_must_be_a_verbatim_span_of_the_cited_chunk(ctx):
    docs, _, raw = ctx
    raw["data"]["citations"][0]["quote"] = "words the chunk never contained"
    assert paths(fails(raw, docs)) == ["data.citations.0.quote"]
    raw["data"]["citations"][0]["quote"] = "   "
    assert paths(fails(raw, docs)) == ["data.citations.0.quote"]


def test_quote_matching_ignores_whitespace_layout_only(ctx):
    docs, chunk, raw = ctx
    words = chunk.text.split()[:8]
    raw["data"]["citations"][0]["quote"] = "\n".join(words)  # same words, different whitespace
    assert validate_block(raw, docs)
    raw["data"]["citations"][0]["quote"] = " ".join(reversed(words))  # reordered: not verbatim
    assert paths(fails(raw, docs)) == ["data.citations.0.quote"]


def test_a_partial_block_is_held_to_grounding_but_may_be_short(ctx):
    docs, _, raw = ctx
    partial = copy.deepcopy(raw)
    partial["meta"]["status"] = "partial"
    assert validate_block(partial, docs)
    assert validate_block({**cited_summary("b", "partial")}, docs)  # no content yet is fine
    partial["data"]["segments"][0]["citationIds"] = ["c7"]
    # c7 does not exist, and the real citation c1 is now cited by nothing: both are reported
    assert sorted(paths(fails(partial, docs))) == ["data.citations.0", "data.segments.0.citationIds.0"]


# ── rules added after the second schema review (M1, M2, M3) ───────────────────


def test_a_citation_must_carry_the_stored_title_and_page(ctx):
    docs, chunk, raw = ctx
    raw["data"]["citations"][0]["docTitle"] = "A Different Paper"
    raw["data"]["citations"][0]["page"] = (chunk.page or 1) + 5
    assert sorted(paths(fails(raw, docs))) == ["data.citations.0.docTitle", "data.citations.0.page"]


def test_a_missing_page_where_the_chunk_has_one_is_rejected(ctx):
    docs, chunk, raw = ctx
    assert chunk.page is not None
    raw["data"]["citations"][0]["page"] = None
    assert paths(fails(raw, docs)) == ["data.citations.0.page"]


@pytest.mark.parametrize("quote", ["a", ".", "the", "Dense"])
def test_a_trivial_quote_is_not_evidence(ctx, quote):
    docs, chunk, raw = ctx
    assert quote in chunk.text  # a real substring, yet too short to support a claim
    raw["data"]["citations"][0]["quote"] = quote
    assert paths(fails(raw, docs)) == ["data.citations.0.quote"]


def test_a_chunk_shorter_than_the_minimum_may_be_quoted_whole(ingested):
    from api.stores.doc_store import Chunk

    deps, result = ingested
    deps.docs.put_chunks([Chunk("tiny", result.doc_id, 99, 3, "Short one.")])
    raw = cited_summary(
        "b",
        "ready",
        data={
            "segments": [{"text": "x", "citationIds": ["c1"]}],
            "citations": [
                {"id": "c1", "chunkId": "tiny", "docId": result.doc_id, "docTitle": "Hybrid Retrieval over Knowledge Graphs", "page": 3, "quote": "Short one."}
            ],
        },
    )
    assert validate_block(raw, deps.docs)


def test_a_citation_no_segment_uses_is_rejected(ctx):
    docs, _, raw = ctx
    extra = copy.deepcopy(raw["data"]["citations"][0])
    extra["id"] = "c2"
    raw["data"]["citations"].append(extra)
    assert paths(fails(raw, docs)) == ["data.citations.1"]


def test_an_id_cited_twice_in_one_segment_is_rejected(ctx):
    docs, _, raw = ctx
    raw["data"]["segments"][0]["citationIds"] = ["c1", "c1"]
    assert paths(fails(raw, docs)) == ["data.segments.0.citationIds.1"]


def test_an_empty_id_is_rejected(ctx):
    docs, _, raw = ctx
    raw["id"] = "  "
    assert paths(fails(raw, docs)) == ["id"]
