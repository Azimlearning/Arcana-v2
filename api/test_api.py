"""The HTTP surface on fakes: /health, /ingest, and /chat as a server-sent event stream."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from api.core.settings import ConfigError, Settings
from api.genui.generated import ErrorEnvelope, IngestResponse, StreamEvent, TurnTrace
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.main import create_app

QUESTION = "How does Dense Retrieval compare with BM25?"
EVENT = TypeAdapter(StreamEvent)


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def ready_client(client: TestClient, pdf_bytes: bytes):
    resp = client.post("/ingest", files={"file": ("hybrid_retrieval.pdf", pdf_bytes, "application/pdf")})
    assert resp.status_code == 200 and resp.json()["status"] == "ready"
    return client


def events(response) -> list:
    """Parse an SSE body: every `data:` line is one StreamEvent, validated against the schema."""
    parsed = []
    for message in response.text.split("\n\n"):
        if not message.strip():
            continue
        assert message.startswith("data: "), f"not an SSE data line: {message!r}"
        parsed.append(EVENT.validate_json(message.removeprefix("data: ")))
    return parsed


def chat(client: TestClient, message: str = QUESTION, **extra):
    return client.post("/chat", json={"message": message, "history": [], **extra})


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_is_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


# ── /ingest ───────────────────────────────────────────────────────────────────


def test_ingest_returns_a_ready_document(client: TestClient, pdf_bytes: bytes, tmp_path: Path):
    response = client.post("/ingest", files={"file": ("hybrid_retrieval.pdf", pdf_bytes, "application/pdf")})
    body = IngestResponse.model_validate(response.json())
    assert response.status_code == 200 and body.status == "ready" and body.error is None
    assert body.chunkCount == 4 and body.title == "Hybrid Retrieval over Knowledge Graphs"
    assert (tmp_path / "data" / "uploads" / f"{body.docId}.pdf").exists()


@pytest.mark.parametrize(
    ("name", "content", "fragment"),
    [
        ("notes.txt", b"%PDF-1.4 hello", "PDF"),
        ("fake.pdf", b"this is not a pdf at all", "does not look like a PDF"),
    ],
)
def test_ingest_rejects_what_is_not_a_pdf_with_the_error_envelope(client, name, content, fragment):
    response = client.post("/ingest", files={"file": (name, content, "application/pdf")})
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 400 and envelope.code == "bad_request" and fragment in envelope.message


def test_ingest_without_a_file_is_a_validation_error_with_a_field_path(client: TestClient):
    response = client.post("/ingest")
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 422 and envelope.code == "validation_failed"
    assert [i.path for i in envelope.issues] == ["file"]


def test_a_pdf_that_cannot_be_read_reports_failure_not_a_server_error(client: TestClient):
    response = client.post("/ingest", files={"file": ("broken.pdf", b"%PDF-1.4 truncated", "application/pdf")})
    body = response.json()
    assert response.status_code == 200 and body["status"] == "failed" and body["error"]


# ── /chat ─────────────────────────────────────────────────────────────────────


def test_chat_streams_a_loading_block_then_a_validated_ready_block_then_done(ready_client: TestClient):
    response = chat(ready_client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"

    stream = events(response)  # every event parsed against the generated schema
    assert [e.type for e in stream] == ["block", "block", "done"]
    loading, final = stream[0].block, stream[1].block  # pyright: ignore[reportAttributeAccessIssue]
    assert loading.meta.status == "loading" and final.meta.status == "ready"
    assert loading.id == final.id  # the second block replaces the first
    assert final.data.segments and final.data.citations
    assert all(c.docTitle == "Hybrid Retrieval over Knowledge Graphs" for c in final.data.citations)


def test_chat_citations_resolve_to_stored_chunks(ready_client: TestClient):
    final = events(chat(ready_client))[1].block  # pyright: ignore[reportAttributeAccessIssue]
    docs = ready_client.app.state.container.docs  # pyright: ignore[reportAttributeAccessIssue]
    stored = docs.get_chunks([c.chunkId for c in final.data.citations])
    assert set(stored) == {c.chunkId for c in final.data.citations}


def test_chat_with_nothing_ingested_streams_an_empty_block(client: TestClient):
    stream = events(chat(client))
    assert stream[1].block.meta.status == "empty"  # pyright: ignore[reportAttributeAccessIssue]


def test_chat_with_the_llm_forced_to_fail_streams_the_error_state_not_a_blank(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    container.llm = LLMService(FakeProvider(fail_with="timeout"), None, container.ledger)
    stream = events(chat(ready_client))
    assert [e.type for e in stream] == ["block", "block", "done"]
    final = stream[1].block  # pyright: ignore[reportAttributeAccessIssue]
    assert final.meta.status == "error" and final.meta.error.code == "provider_unavailable"
    assert final.data.segments == []


def test_chat_records_each_turn(ready_client: TestClient):
    chat(ready_client)
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    (turn,) = container.docs.turns()
    assert turn.outcome == "ok" and turn.query == QUESTION and turn.error_code is None
    container.llm = LLMService(FakeProvider(fail_with="timeout"), None, container.ledger)
    chat(ready_client)
    assert [t.outcome for t in container.docs.turns()] == ["ok", "error"]


@pytest.mark.parametrize(
    ("payload", "status", "path"),
    [
        ({"message": "   ", "history": []}, 400, None),
        ({"message": "x" * 4001, "history": []}, 400, None),
        ({"message": "hi", "history": [{"role": "user", "content": "q"}] * 21}, 400, None),
        ({"history": []}, 422, "message"),
        ({"message": 7, "history": []}, 422, "message"),
        ({"message": "hi", "history": [{"role": "robot", "content": "q"}]}, 422, "history.0.role"),
        ({"message": "hi", "history": [], "surprise": 1}, 422, "surprise"),
    ],
)
def test_chat_rejects_a_bad_request_with_the_error_envelope(client: TestClient, payload, status, path):
    response = client.post("/chat", json=payload)
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == status
    assert envelope.code == ("bad_request" if status == 400 else "validation_failed")
    if path is not None:
        assert path in [i.path for i in envelope.issues]


def test_an_unexpected_server_error_never_leaks_detail(client: TestClient):
    def boom():
        raise RuntimeError("secret internal detail C:\\Users\\x")

    client.app.add_api_route("/__boom", boom)  # pyright: ignore[reportAttributeAccessIssue]
    quiet = TestClient(client.app, raise_server_exceptions=False)
    response = quiet.get("/__boom")
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 500 and envelope.code == "internal"
    assert "secret" not in response.text


def test_the_stream_never_carries_a_stack_trace_or_server_path(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    container.llm = LLMService(FakeProvider(lambda r: "garbage"), None, container.ledger)
    body = chat(ready_client).text
    assert "Traceback" not in body and "api\\" not in body and "api/" not in body


# ── startup ───────────────────────────────────────────────────────────────────


def test_startup_in_live_mode_without_a_key_fails_loudly_naming_the_variable(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "LLM_MONTHLY_CAP_USD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    monkeypatch.setenv("ARCANA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)  # so no real .env is picked up
    with pytest.raises(ConfigError) as exc, TestClient(create_app()):
        pass
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_a_malformed_sse_body_would_be_caught_by_the_test_parser():
    with pytest.raises(AssertionError):
        events(type("R", (), {"text": "event: block\n\n"})())


def test_stream_event_json_round_trips(ready_client: TestClient):
    first = chat(ready_client).text.split("\n\n")[0].removeprefix("data: ")
    assert json.loads(first)["type"] == "block"


# ── /turns/{id}/trace ─────────────────────────────────────────────────────────


def turn_id_of(response) -> str:
    return events(response)[1].block.id  # pyright: ignore[reportAttributeAccessIssue]


def test_a_chat_turn_has_a_trace_listing_every_hop_in_order(ready_client: TestClient):
    turn_id = turn_id_of(chat(ready_client))  # a comparison: orchestrator, graph, research, fact checker
    response = ready_client.get(f"/turns/{turn_id}/trace")
    assert response.status_code == 200
    trace = TurnTrace.model_validate(response.json())  # the generated, strict wire type
    assert trace.turnId == turn_id and trace.outcome == "answered"
    assert [(s.hop, s.agent) for s in trace.steps] == [
        (0, "orchestrator"),
        (1, "graph"),
        (2, "research"),
        (3, "fact_checker"),
    ]
    assert trace.hopsUsed == 4 and trace.steps[0].status == "ok"  # the others may be partial on a small fixture
    assert trace.tokensUsed > 0 and trace.steps[0].tokens >= trace.steps[1].tokens  # inclusive of what it routed to


def test_a_relationship_question_traces_the_graph_hop_too(ready_client: TestClient):
    turn_id = turn_id_of(chat(ready_client, "How is dense retrieval related to reciprocal rank fusion?"))
    trace = TurnTrace.model_validate(ready_client.get(f"/turns/{turn_id}/trace").json())
    assert [s.agent for s in trace.steps] == ["orchestrator", "graph", "research", "fact_checker"]


def test_the_trace_carries_no_question_text(ready_client: TestClient):
    turn_id = turn_id_of(chat(ready_client, "How is dense retrieval related to reciprocal rank fusion?"))
    body = ready_client.get(f"/turns/{turn_id}/trace").text
    assert "dense" not in body.lower() and "fusion" not in body.lower()


def test_a_failed_turn_has_a_trace_with_the_failure_and_an_error_outcome(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    container.llm = LLMService(FakeProvider(fail_with="timeout"), None, container.ledger)
    turn_id = turn_id_of(chat(ready_client))
    trace = TurnTrace.model_validate(ready_client.get(f"/turns/{turn_id}/trace").json())
    assert trace.outcome == "error"
    research = next(s for s in trace.steps if s.agent == "research")
    assert research.status == "failed" and research.note == "provider_unavailable"


def test_a_nothing_ingested_turn_is_traced_as_empty(client: TestClient):
    turn_id = turn_id_of(chat(client))
    assert TurnTrace.model_validate(client.get(f"/turns/{turn_id}/trace").json()).outcome == "empty"


@pytest.mark.parametrize("turn_id", ["turn-never-happened", "x" * 65, "..%2F..%2Fsecrets"])
def test_an_unknown_turn_is_a_not_found_envelope(client: TestClient, turn_id: str):
    response = client.get(f"/turns/{turn_id}/trace")
    assert response.status_code == 404
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.code == "not_found"


def test_a_damaged_stored_trace_is_never_returned_as_a_trace(ready_client: TestClient):
    container = ready_client.app.state.container  # pyright: ignore[reportAttributeAccessIssue]
    container.docs.record_trace("turn-damaged", '{"turnId": "turn-damaged", "steps": "nope"}')
    quiet = TestClient(ready_client.app, raise_server_exceptions=False)
    response = quiet.get("/turns/turn-damaged/trace")
    assert response.status_code == 500 and "steps" not in response.text  # the error envelope, no detail


def test_the_trace_endpoint_is_get_only(client: TestClient):
    assert client.post("/turns/anything/trace").status_code == 405


def test_a_turn_forced_to_one_hop_still_ends_with_a_block_and_a_trace(ready_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from api.agents.framework import TurnLimits
    from api.agents.state import TurnContext
    from api.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "TurnContext", lambda **kw: TurnContext(**kw, limits=TurnLimits(max_hops=1)))
    stream = events(chat(ready_client))
    assert [e.type for e in stream] == ["block", "block", "done"]  # a block, not a hang or a crash
    final = stream[1].block  # pyright: ignore[reportAttributeAccessIssue]
    assert final.meta.status == "error" and final.meta.error.code == "budget_exhausted"
    assert final.data.segments == []  # nothing unchecked or half-answered is shown

    trace = TurnTrace.model_validate(ready_client.get(f"/turns/{final.id}/trace").json())
    assert trace.hopsUsed == 1 and trace.outcome == "error"
    assert trace.steps[0].agent == "orchestrator" and trace.steps[0].status == "ok"
    assert {s.status for s in trace.steps[1:]} == {"refused"}  # every later hop is recorded as refused
