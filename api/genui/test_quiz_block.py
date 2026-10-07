"""The `QuizCard` block (Q1.2, D-35 A8): the validator by planted defects, the Composer's `compose_quiz`, and the two routes.

The vault is the handmade one of `api/vault/test_quiz.py` (read its header for the expected items). Over HTTP the same vault and
passages are put into a fresh app's stores, with no model call anywhere.
"""

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.agents.compose import compose_quiz
from api.core.errors import NotFound, ValidationFailed
from api.core.settings import Settings
from api.genui.builders import quiz_card
from api.genui.notes_catalog import NOTES_CATALOG, QUIZ_CARD
from api.genui.validate import validate_block
from api.learner.mastery import MasteryScore
from api.main import create_app
from api.vault.quiz import derive_quiz
from api.vault.test_quiz import fill, small  # noqa: F401  (a fixture)
from api.vault.types import Vault


def block_of(vault, docs, focus=None, mastery=None):
    return quiz_card("quiz", "ready", data=derive_quiz(vault, docs, focus, mastery))


def test_a_derived_quiz_passes_the_validator_with_and_without_a_focus(small):  # noqa: F811
    vault, docs = small
    assert validate_block(block_of(vault, docs), docs, vault=vault).type == "QuizCard"
    focused = block_of(vault, docs, "dense_retrieval")
    assert validate_block(focused, docs, vault=vault).data.focusId == "dense_retrieval"  # type: ignore[union-attr]


def test_a_quiz_is_refused_without_the_vault_it_is_checked_against(small):  # noqa: F811
    vault, docs = small
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault, docs), docs)


def _defects():
    def blank_moved(d):
        d["items"][0]["text"] = (
            "Dense _____ finds passages by comparing embedding vectors of the query and the text."
        )

    def unblanked(d):
        d["items"][0]["text"] = d["items"][0]["text"].replace("_____", "Dense retrieval")

    def option_label(d):
        d["items"][0]["options"][0]["label"] = "Something else"

    def option_id(d):
        d["items"][0]["options"][1]["id"] = "squad"

    def options_order(d):
        d["items"][0]["options"].reverse()

    def option_dropped(d):
        d["items"][0]["options"].pop()

    def option_added(d):
        d["items"][0]["options"].append(copy.deepcopy(d["items"][0]["options"][0]))

    def title(d):
        d["items"][0]["docTitle"] = "Another paper"

    def page(d):
        d["items"][0]["page"] = 99

    def item_id(d):
        d["items"][0]["id"] = "claim-2~bm25"

    def item_dropped(d):
        d["items"].pop()

    def item_added(d):
        d["items"].append(copy.deepcopy(d["items"][0]))

    def items_reordered(d):
        d["items"].reverse()

    def skipped(d):
        d["skipped"] += 1

    def focus(d):
        d["focusId"] = "ghost"

    def focus_changed(d):
        d["focusId"] = "bm25"

    return [
        blank_moved,
        unblanked,
        option_label,
        option_id,
        options_order,
        option_dropped,
        option_added,
        title,
        page,
        item_id,
        item_dropped,
        item_added,
        items_reordered,
        skipped,
        focus,
        focus_changed,
    ]


@pytest.mark.parametrize("defect", _defects(), ids=lambda f: f.__name__)
def test_the_validator_rejects_every_planted_defect(small, defect):  # noqa: F811
    vault, docs = small
    raw = block_of(vault, docs)
    defect(raw["data"])
    with pytest.raises(ValidationFailed) as refused:
        validate_block(raw, docs, vault=vault)
    assert refused.value.issues, "a refusal names the field"


@pytest.mark.parametrize("field", ["answer", "correct", "answerId", "quote", "target"])
def test_a_block_that_names_its_answer_is_refused_by_the_schema(small, field):  # noqa: F811
    vault, docs = small
    raw = block_of(vault, docs)
    raw["data"]["items"][0][field] = "dense_retrieval"
    with pytest.raises(ValidationFailed, match="wire schema"):
        validate_block(raw, docs, vault=vault)
    raw = block_of(vault, docs)
    raw["data"][field] = "dense_retrieval"
    with pytest.raises(ValidationFailed, match="wire schema"):
        validate_block(raw, docs, vault=vault)


def test_a_quiz_is_checked_against_the_mastery_snapshot_it_was_built_from(small):  # noqa: F811
    vault, docs = small
    snapshot = {"reranking": MasteryScore(0.1, 2)}
    raw = block_of(vault, docs, None, snapshot)
    assert raw["data"]["items"][0]["id"] == "claim-4~reranking"
    assert validate_block(raw, docs, vault=vault, mastery=snapshot).type == "QuizCard"
    with pytest.raises(
        ValidationFailed
    ):  # the order depends on the learner: another snapshot gives another quiz
        validate_block(raw, docs, vault=vault)


def test_placeholders_carry_nothing_and_an_empty_quiz_must_really_be_empty(small):  # noqa: F811
    vault, docs = small
    assert validate_block(quiz_card("quiz", "loading"), docs, vault=vault).meta.status == "loading"
    assert (
        validate_block(quiz_card("quiz", "empty"), docs).meta.status == "empty"
    )  # no vault: nothing to derive
    loaded = block_of(vault, docs)
    loaded["meta"]["status"] = "loading"
    with pytest.raises(ValidationFailed):
        validate_block(loaded, docs, vault=vault)
    loaded["meta"]["status"] = "empty"  # the vault can make questions here
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(loaded, docs, vault=vault)
    with pytest.raises(ValidationFailed):
        validate_block(quiz_card("quiz", "ready"), docs, vault=vault)  # ready with nothing to ask
    bare = Vault(vault.version, vault.n_chunks, vault.pages, [], [])
    nothing = quiz_card("quiz", "empty", data=derive_quiz(bare, docs, None))
    assert validate_block(nothing, docs, vault=bare).meta.status == "empty"


def test_compose_quiz_places_the_quiz_in_chat_and_the_graph_beside_it_in_the_studio(small):  # noqa: F811
    vault, docs = small
    layout, blocks = compose_quiz(vault, docs, None)
    assert [(b.type, b.id, b.meta.status) for b in blocks] == [
        ("QuizCard", "quiz", "ready"),
        ("NotesGraph", "notes-graph", "ready"),
    ]
    where = {p.blockId: (p.panel, p.region) for p in layout.placements}
    assert where == {"quiz": ("chat", "main"), "notes-graph": ("studio", "main")}
    _, focused = compose_quiz(vault, docs, "dense_retrieval")
    assert focused[0].data.focusId == "dense_retrieval"  # type: ignore[union-attr]
    assert focused[1].data.focusId == "dense_retrieval"  # type: ignore[union-attr]


def test_compose_quiz_with_no_vault_no_claims_or_an_unknown_page(small):  # noqa: F811
    vault, docs = small
    _, blocks = compose_quiz(None, docs, None)
    assert [(b.type, b.meta.status) for b in blocks] == [("QuizCard", "empty")]
    bare = Vault(vault.version, vault.n_chunks, vault.pages, [], [])
    _, blocks = compose_quiz(bare, docs, None)
    assert [(b.type, b.meta.status) for b in blocks] == [
        ("QuizCard", "empty"),
        ("NotesGraph", "ready"),
    ]
    with pytest.raises(NotFound):
        compose_quiz(vault, docs, "ghost")


def test_the_quiz_spec_is_in_the_notes_registry_with_its_fences():
    assert NOTES_CATALOG["QuizCard"] is QUIZ_CARD
    assert QUIZ_CARD.caps == {"items": 5, "options": 4, "label_chars": 120}
    assert QUIZ_CARD.placement.panel == "chat" and QUIZ_CARD.supplied_by == ("vault",)


# ── over HTTP: the same vault and passages in a fresh app, no model ────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        container = c.app.state.container  # type: ignore[attr-defined]
        container.vault_store.put_vault(fill(container.docs))
        yield c


def _first_item(client, page=None):
    params = {"page": page} if page else {}
    body = client.get("/vault/quiz", params=params).json()
    return body, body["blocks"][0]["data"]["items"][0]


def test_the_quiz_route_serves_a_validated_quiz_that_carries_no_answer(client):
    body, item = _first_item(client)
    assert [b["type"] for b in body["blocks"]] == ["QuizCard", "NotesGraph"]
    assert item["id"] == "claim-1~dense_retrieval" and "_____" in item["text"]
    assert set(item) == {"id", "text", "options", "docTitle", "page"}
    focused = client.get("/vault/quiz", params={"page": "bm25"}).json()
    assert focused["blocks"][0]["data"]["focusId"] == "bm25"
    assert client.get("/vault/quiz", params={"page": "ghost"}).json()["code"] == "not_found"
    assert client.get("/vault/quiz", params={"page": "x" * 500}).status_code == 422


def test_a_right_answer_records_quiz_correct_for_the_blanked_page_and_returns_the_source(client):
    _, item = _first_item(client)
    reply = client.post("/quiz/answer", json={"itemId": item["id"], "chosenId": "dense_retrieval"})
    assert reply.status_code == 200
    got = reply.json()
    assert got["correct"] is True and got["answer"] == {
        "id": "dense_retrieval",
        "label": "dense retrieval",
    }
    assert (
        got["citation"]["quote"].startswith("Dense retrieval finds passages")
        and got["citation"]["docTitle"] == "Paper One"
    )
    assert got["mastery"] == {"score": 0.6667, "events": 1}  # one quiz_correct: A=1, B=0
    events = client.app.state.container.learner_store.events("dense_retrieval")  # type: ignore[attr-defined]
    assert [e.signal for e in events] == ["quiz_correct"]


def test_a_wrong_answer_records_quiz_wrong_for_the_blanked_page_not_the_chosen_one(client):
    _, item = _first_item(client)
    wrong = next(o["id"] for o in item["options"] if o["id"] != "dense_retrieval")
    got = client.post("/quiz/answer", json={"itemId": item["id"], "chosenId": wrong}).json()
    assert got["correct"] is False and got["answer"]["id"] == "dense_retrieval"
    assert got["mastery"] == {"score": 0.3333, "events": 1}
    store = client.app.state.container.learner_store  # type: ignore[attr-defined]
    assert [e.signal for e in store.events("dense_retrieval")] == ["quiz_wrong"]
    assert store.events(wrong) == []


def test_the_graph_beside_the_quiz_recolours_after_an_answer(client):
    _, item = _first_item(client)
    client.post("/quiz/answer", json={"itemId": item["id"], "chosenId": "dense_retrieval"})
    graph = client.get("/vault/quiz").json()["blocks"][1]
    mastery = {n["id"]: n["mastery"] for n in graph["data"]["nodes"]}
    assert mastery["dense_retrieval"] == 0.6667 and mastery["bm25"] is None


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"itemId": "claim-99~bm25", "chosenId": "bm25"}, 404, "not_found"),
        ({"itemId": "claim-2~dense_retrieval", "chosenId": "bm25"}, 404, "not_found"),
        ({"itemId": "garbage", "chosenId": "bm25"}, 404, "not_found"),
        ({"itemId": "claim-2~bm25", "chosenId": "squad"}, 422, "validation_failed"),
        ({"itemId": "claim-2~bm25", "chosenId": "ghost"}, 422, "validation_failed"),
        ({"itemId": "claim-2~bm25"}, 422, "validation_failed"),
        (
            {"itemId": "claim-2~bm25", "chosenId": "bm25", "signal": "quiz_correct"},
            422,
            "validation_failed",
        ),
    ],
)
def test_a_forged_answer_is_refused_and_records_nothing(client, body, status, code):
    reply = client.post("/quiz/answer", json=body)
    assert reply.status_code == status and reply.json()["code"] == code
    store = client.app.state.container.learner_store  # type: ignore[attr-defined]
    assert store.mastery(["bm25", "dense_retrieval", "squad"]) == {}


def test_the_rating_route_still_refuses_a_quiz_signal(client):
    for signal in ("quiz_correct", "quiz_wrong"):
        reply = client.post("/learner/events", json={"pageId": "bm25", "signal": signal})
        assert reply.status_code == 422


def test_an_oversized_answer_body_is_refused_before_it_is_read(client):
    reply = client.post(
        "/quiz/answer",
        content=b"x" * 5000,
        headers={"content-type": "application/json", "content-length": "5000"},
    )
    assert reply.status_code == 413


def test_with_no_vault_the_quiz_is_empty_and_an_answer_is_not_found(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "bare")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        blocks = c.get("/vault/quiz").json()["blocks"]
        assert [(b["type"], b["meta"]["status"]) for b in blocks] == [("QuizCard", "empty")]
        assert (
            c.post("/quiz/answer", json={"itemId": "claim-1~bm25", "chosenId": "bm25"}).status_code
            == 404
        )
