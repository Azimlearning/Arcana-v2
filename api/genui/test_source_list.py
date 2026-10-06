"""SourceList: the validator rejects every tampered field with its path, and accepts the store's own listing."""

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import source_list
from api.genui.catalog import cap
from api.genui.generated import SourceList
from api.genui.validate import validate_block
from api.stores.doc_store import Document


def item(doc_id, title, count):
    return {"docId": doc_id, "title": title, "chunkCount": count}


@pytest.fixture
def stored(ingested):
    deps, result = ingested
    document = deps.docs.get_document(result.doc_id)
    assert document is not None
    count = len(deps.docs.chunks_for_document(result.doc_id))
    return deps.docs, document, count


def fails(raw, docs) -> list[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs)
    return [i.path for i in exc.value.issues]


def test_the_stores_own_listing_passes(stored):
    docs, document, count = stored
    block = validate_block(
        source_list("b-sources", "ready", documents=[item(document.id, document.title, count)]), docs
    )
    assert isinstance(block, SourceList) and block.data.documents[0].chunkCount == count


@pytest.mark.parametrize("status", ["empty", "loading"])
def test_placeholders_carry_no_documents(stored, status):
    docs, document, count = stored
    block = validate_block(source_list("b", status), docs)
    assert isinstance(block, SourceList) and block.data.documents == []
    assert fails(source_list("b", status, documents=[item(document.id, document.title, count)]), docs) == ["data"]


def test_a_ready_block_needs_a_document(stored):
    docs, _, _ = stored
    assert fails(source_list("b", "ready", documents=[]), docs) == ["data.documents"]


def test_a_document_that_does_not_exist_is_rejected(stored):
    docs, _, _ = stored
    assert fails(source_list("b", "ready", documents=[item("nope", "Ghost", 3)]), docs) == ["data.documents.0.docId"]


def test_a_title_or_count_that_differs_from_the_store_is_rejected(stored):
    docs, document, count = stored
    assert fails(source_list("b", "ready", documents=[item(document.id, "Other title", count)]), docs) == [
        "data.documents.0.title"
    ]
    assert fails(source_list("b", "ready", documents=[item(document.id, document.title, count + 1)]), docs) == [
        "data.documents.0.chunkCount"
    ]


def test_a_duplicate_id_is_rejected(stored):
    docs, document, count = stored
    twice = [item(document.id, document.title, count)] * 2
    assert fails(source_list("b", "ready", documents=twice), docs) == ["data.documents.1.docId"]


def test_a_document_that_is_not_ready_is_rejected(stored):
    docs, _, _ = stored
    docs.put_document(Document("p1", "Pending paper", "p1.pdf", "pending", 1, None, "t"))
    assert fails(source_list("b", "ready", documents=[item("p1", "Pending paper", 0)]), docs) == [
        "data.documents.0.docId"
    ]


def test_more_than_the_cap_is_rejected(stored):
    docs, _, _ = stored
    items = []
    for i in range(cap("SourceList", "documents") + 1):
        docs.put_document(Document(f"d{i}", f"Paper {i}", f"d{i}.pdf", "ready", 1, None, "t"))
        items.append(item(f"d{i}", f"Paper {i}", 0))
    assert "data.documents" in fails(source_list("b", "ready", documents=items), docs)


def test_an_error_block_needs_its_error_and_no_documents(stored):
    docs, _, _ = stored
    assert fails(source_list("b", "error"), docs) == ["meta.error"]
