"""Saved patterns (P2 E2): save, list and delete through the HTTP surface, content-addressed, strings only."""

# ruff: noqa: F811  (the `client` fixtures are imported from test_api and used by name, the usual pytest pattern)

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.genui import patterns
from api.genui.catalog import CATALOG, ViewComponent
from api.genui.generated import ErrorEnvelope, PatternList, SavedPattern
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.stores.local import sqlite_doc
from api.stores.local.sqlite_doc import SqliteDocStore
from api.test_api import (  # noqa: F401  (fixtures and helpers)
    chat,
    client,
    ready_client,
    turn_id_of,
)

# A question that resolves two entities, so the turn shows a connection graph and a source list.
QUESTION = "How does Dense Retrieval compare with BM25?"


def saved_turn(app_client: TestClient) -> str:
    return turn_id_of(chat(app_client, QUESTION))


def save(app_client: TestClient, turn_id: str, template: str = "GraphView", name: str = "Dense vs BM25"):
    return app_client.post("/patterns", json={"turnId": turn_id, "templateId": template, "name": name})


def listing(app_client: TestClient) -> list[SavedPattern]:
    response = app_client.get("/patterns")
    assert response.status_code == 200
    return PatternList.model_validate(response.json()).patterns


# ── what a turn records ───────────────────────────────────────────────────────


def test_a_turn_records_the_reusable_views_it_showed_with_their_string_parameters(ready_client: TestClient):
    turn_id = saved_turn(ready_client)
    raw = ready_client.app.state.container.docs.get_view(turn_id)  # pyright: ignore[reportAttributeAccessIssue]
    view = patterns.view_from_json(raw)  # pyright: ignore[reportArgumentType]
    assert view is not None
    mode, components = view
    assert mode in ("research", "exploration")
    by_template = {c.template: c for c in components}
    assert set(by_template) == {"SourceList", "GraphView"}  # the answer is not reusable; the grid and path were refused
    assert by_template["GraphView"].params == {"entities": ["Dense Retrieval", "BM25"]}
    assert by_template["SourceList"].params == {} and all(c.verified for c in components)


def test_a_turn_that_failed_records_no_views(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    container.llm = LLMService(FakeProvider(fail_with="timeout"), None, container.ledger)
    turn_id = saved_turn(ready_client)
    assert container.docs.get_view(turn_id) is None
    assert save(ready_client, turn_id).status_code == 404


# ── save, list, delete ────────────────────────────────────────────────────────


def test_save_list_and_delete_round_trip(ready_client: TestClient):
    assert listing(ready_client) == []
    response = save(ready_client, saved_turn(ready_client))
    assert response.status_code == 200
    pattern = SavedPattern.model_validate(response.json())  # the generated, strict wire type
    assert (pattern.name, pattern.templateId, pattern.templateVersion) == ("Dense vs BM25", "GraphView", 1)
    assert pattern.state == "saved" and pattern.useCount == 0 and pattern.lastUsedAt is None
    assert [(p.key, p.values) for p in pattern.params] == [("entities", ["Dense Retrieval", "BM25"])]
    assert pattern.layoutMode in ("research", "exploration")
    assert listing(ready_client) == [pattern]

    assert ready_client.delete(f"/patterns/{pattern.id}").status_code == 204
    assert listing(ready_client) == []
    gone = ready_client.delete(f"/patterns/{pattern.id}")
    assert gone.status_code == 404 and ErrorEnvelope.model_validate(gone.json()).code == "not_found"


def test_the_same_view_saved_twice_is_one_pattern_and_keeps_its_first_name(ready_client: TestClient):
    turn_id = saved_turn(ready_client)
    first = SavedPattern.model_validate(save(ready_client, turn_id, name="First name").json())
    second = SavedPattern.model_validate(save(ready_client, turn_id, name="Second name").json())
    assert first.id == second.id and second.name == "First name"
    other_turn = saved_turn(ready_client)  # another turn that showed the same view
    third = SavedPattern.model_validate(save(ready_client, other_turn, name="Third").json())
    assert third.id == first.id and len(listing(ready_client)) == 1


def test_different_views_have_different_ids(ready_client: TestClient):
    turn_id = saved_turn(ready_client)
    graph = SavedPattern.model_validate(save(ready_client, turn_id).json())
    sources = SavedPattern.model_validate(save(ready_client, turn_id, "SourceList", "My sources").json())
    assert graph.id != sources.id and len(listing(ready_client)) == 2
    assert patterns.pattern_id("GraphView", 1, {"entities": ["A", "B"]}, "research") != patterns.pattern_id(
        "GraphView", 1, {"entities": ["B", "A"]}, "research"
    )  # the order of values matters
    assert patterns.pattern_id("GraphView", 1, {"entities": ["A"]}, "research") == patterns.pattern_id(
        "GraphView", 1, {"entities": ["A"]}, "research"
    )
    assert patterns.pattern_id("GraphView", 2, {"entities": ["A"]}, "research") != patterns.pattern_id(
        "GraphView", 1, {"entities": ["A"]}, "research"
    )


# ── refusals ──────────────────────────────────────────────────────────────────


def record(app_client: TestClient, turn_id: str, components: list[ViewComponent], mode: str = "research"):
    app_client.app.state.container.docs.record_view(turn_id, patterns.view_to_json(mode, components))  # pyright: ignore[reportAttributeAccessIssue]


def refused(response, code: str = "bad_request", status: int = 400):
    assert response.status_code == status
    assert ErrorEnvelope.model_validate(response.json()).code == code


def test_a_view_that_was_not_verified_is_refused(client: TestClient):
    record(client, "turn-x", [ViewComponent("GraphView", 1, {"entities": ["A", "B"]}, False)])
    refused(save(client, "turn-x"))
    assert listing(client) == []


def test_a_view_the_turn_did_not_show_or_a_template_that_cannot_be_saved_is_refused(client: TestClient):
    record(client, "turn-x", [ViewComponent("GraphView", 1, {"entities": ["A"]}, True)])
    refused(save(client, "turn-x", "ConceptMap"))  # not shown on that turn
    refused(save(client, "turn-x", "CitedSummary"))  # the answer needs Research: not reusable
    refused(save(client, "turn-x", "NoSuchTemplate"))


def test_a_stale_view_record_is_refused(client: TestClient):
    record(client, "turn-x", [ViewComponent("GraphView", 0, {"entities": ["A"]}, True)])  # an older template version
    refused(save(client, "turn-x"))


@pytest.mark.parametrize(
    "params",
    [
        {"entities": ["A"], "colour": ["red"]},  # not one of the template's slots
        {"entities": []},  # too few values
        {"entities": ["A", "B", "C"]},  # too many
        {"entities": ["A", "A"]},  # repeats a value
        {"entities": ["x" * 121]},  # too long
        {"entities": ["bad\nvalue"]},  # not plain text
        {"entities": [" "]},
    ],
)
def test_a_parameter_that_is_not_one_of_the_templates_slots_or_not_valid_is_refused(client: TestClient, params):
    record(client, "turn-x", [ViewComponent("GraphView", 1, params, True)])
    refused(save(client, "turn-x"))
    assert patterns.validate_params(CATALOG["GraphView"], params)  # and the check itself names a problem


def test_the_parameter_check_accepts_valid_parameters_and_checks_document_ids():
    assert patterns.validate_params(CATALOG["GraphView"], {"entities": ["Dense Retrieval", "BM25"]}) == []
    assert patterns.validate_params(CATALOG["SourceList"], {}) == []
    grid = CATALOG["ComparisonGrid"]
    assert patterns.validate_params(grid, {"entities": ["A", "B"], "documents": ["doc-1"]}) == []
    assert patterns.validate_params(grid, {"entities": ["A", "B"], "documents": ["../etc"]})  # not a document id


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "bad\x00name", "two\nlines"])
def test_a_name_that_is_empty_too_long_or_not_plain_text_is_refused(ready_client: TestClient, name: str):
    refused(save(ready_client, saved_turn(ready_client), name=name))
    assert listing(ready_client) == []


def test_a_name_at_the_cap_is_kept_trimmed(ready_client: TestClient):
    pattern = SavedPattern.model_validate(
        save(ready_client, saved_turn(ready_client), name="  " + "x" * 80 + "  ").json()
    )
    assert pattern.name == "x" * 80


def test_an_unknown_turn_or_a_malformed_request_is_refused(client: TestClient):
    refused(save(client, "turn-never-happened"), "not_found", 404)
    refused(save(client, "x" * 65), "not_found", 404)
    bad = client.post("/patterns", json={"turnId": "t", "name": "n"})  # no templateId
    assert bad.status_code == 422 and bad.json()["code"] == "validation_failed"
    assert (
        client.post("/patterns", json={"turnId": "t", "templateId": "GraphView", "name": "n", "extra": 1}).status_code
        == 422
    )
    refused(client.delete("/patterns/" + "x" * 65), "not_found", 404)


# ── what is stored ────────────────────────────────────────────────────────────


def test_the_stored_pattern_holds_no_document_text_or_block_data(ready_client: TestClient):
    saved = SavedPattern.model_validate(save(ready_client, saved_turn(ready_client)).json())
    docs = ready_client.app.state.container.docs  # pyright: ignore[reportAttributeAccessIssue]
    stored = docs.get_pattern(saved.id)
    body = ready_client.get("/patterns").text + json.dumps(stored.__dict__)
    for chunk in docs.all_chunks():  # no sentence of any stored chunk, however short a run of it
        for start in range(0, max(1, len(chunk.text) - 30), 15):
            assert chunk.text[start : start + 30] not in body
    for forbidden in ("citations", "quote", "chunkId", "segments", "nodes", "edges"):
        assert forbidden not in body  # no block data
    assert set(json.loads(stored.params_json)[0]) == {"key", "values"}  # strings and their keys, nothing else


def test_a_database_created_before_the_tables_existed_opens_and_gains_them(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    old_tables = [sqlite_doc.documents, sqlite_doc.chunks, sqlite_doc.turns, sqlite_doc.turn_traces]
    sqlite_doc.metadata.create_all(engine, tables=old_tables)  # as a data directory from before saved patterns
    assert "ui_patterns" not in sqlite_doc.metadata.tables or not _has_table(engine, "ui_patterns")
    store = SqliteDocStore(engine)  # opening it creates the missing tables
    assert _has_table(engine, "ui_patterns") and _has_table(engine, "turn_views")
    assert store.list_patterns() == [] and store.get_view("t") is None


def _has_table(engine, name: str) -> bool:
    from sqlalchemy import inspect

    return name in inspect(engine).get_table_names()


def test_a_damaged_stored_pattern_is_an_error_envelope_never_half_a_pattern(ready_client: TestClient):
    from api.stores.doc_store import StoredPattern

    docs = ready_client.app.state.container.docs  # pyright: ignore[reportAttributeAccessIssue]
    docs.put_pattern(StoredPattern("bad", "n", "GraphView", 1, '{"not": "a list"}', "research", "saved", 0, "t", None))
    quiet = TestClient(ready_client.app, raise_server_exceptions=False)
    response = quiet.get("/patterns")
    assert response.status_code == 500 and "not" not in response.text and response.json()["code"] == "internal"


def test_a_pattern_of_a_template_that_no_longer_exists_is_still_listed_so_it_can_be_deleted(ready_client: TestClient):
    from api.stores.doc_store import StoredPattern

    docs = ready_client.app.state.container.docs  # pyright: ignore[reportAttributeAccessIssue]
    docs.put_pattern(
        StoredPattern(
            "old", "n", "RemovedThing", 3, '[{"key": "entities", "values": ["A"]}]', "research", "saved", 0, "t", None
        )
    )
    assert [p.id for p in listing(ready_client)] == ["old"]
    assert ready_client.delete("/patterns/old").status_code == 204


def test_the_endpoints_make_no_model_call(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    turn_id = saved_turn(ready_client)
    provider = FakeProvider(fail_with="timeout")
    container.llm = LLMService(provider, None, container.ledger)
    saved = SavedPattern.model_validate(save(ready_client, turn_id).json())
    listing(ready_client)
    ready_client.delete(f"/patterns/{saved.id}")
    assert provider.calls == []
