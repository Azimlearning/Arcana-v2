"""Every failure leaves the API as an ErrorEnvelope, including the ones the framework raises itself
(schema review H2, H3, M5)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.core.settings import Settings
from api.genui.generated import ErrorEnvelope
from api.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        yield c


def test_a_route_that_does_not_exist_is_a_not_found_envelope(client: TestClient):
    response = client.get("/nope")
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 404 and envelope.code == "not_found"


def test_the_wrong_method_is_a_bad_request_envelope_keeping_the_allow_header(client: TestClient):
    response = client.get("/chat")
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 405 and envelope.code == "bad_request"
    assert "POST" in response.headers.get("allow", "")


def test_a_500_envelope_carries_cors_headers_so_the_browser_can_read_it(client: TestClient):
    client.app.add_api_route("/__boom", lambda: 1 / 0)  # pyright: ignore[reportAttributeAccessIssue]
    quiet = TestClient(client.app, raise_server_exceptions=False)
    allowed = quiet.get("/__boom", headers={"Origin": "http://localhost:3000"})
    assert allowed.status_code == 500
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    stranger = quiet.get("/__boom", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in stranger.headers


def test_a_body_that_is_not_json_points_at_the_body_not_a_byte_offset(client: TestClient):
    response = client.post("/chat", content=b"{not json", headers={"Content-Type": "application/json"})
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 422 and [i.path for i in envelope.issues] == ["(body)"]


def test_an_oversized_declared_body_is_refused_before_it_is_read(client: TestClient):
    response = client.post(
        "/chat",
        content=b"x",
        headers={"Content-Type": "application/json", "Content-Length": str(10 * 1024 * 1024)},
    )
    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == 413 and envelope.code == "bad_request"


def test_chat_bounds_each_history_message_and_the_total(client: TestClient):
    long_message = {"role": "user", "content": "x" * 4001}
    assert client.post("/chat", json={"message": "hi", "history": [long_message]}).status_code == 400
    many = [{"role": "user", "content": "x" * 3000}] * 14  # 14 messages, each fine, 42,000 in all
    assert client.post("/chat", json={"message": "hi", "history": many}).status_code == 400
