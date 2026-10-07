"""The learner layer (M2.7, D-35 A6): the mastery rule by hand, the store, the snapshot the blocks are checked against, the routes.

Rule: each event adds (a, b): know (1, 0), unsure (0.5, 0.5), dont_know (0, 1), quiz_correct (1, 0), quiz_wrong (0, 1), times
0.5 ** (whole days / 14); score = (A + 1) / (A + B + 2), rounded to 4 places; no events, no mastery.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.core.errors import ValidationFailed
from api.core.settings import Settings
from api.genui.builders import concept_page, notes_graph
from api.genui.validate import validate_block
from api.learner.mastery import (
    ACCEPTED_NOW,
    HALF_LIFE_DAYS,
    LearnerEvent,
    MasteryScore,
    decay,
    mastery_of,
)
from api.learner.store import MAX_EVENTS_PER_PAGE, SqliteLearnerStore
from api.main import create_app
from api.vault.compile import compile_vault
from api.vault.test_compile import world
from api.vault.view import derive_concept_page, derive_notes_graph

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def ev(signal: str, days_ago: float = 0, page: str = "p") -> LearnerEvent:
    return LearnerEvent(page, signal, NOW - timedelta(days=days_ago))  # type: ignore[arg-type]


# ── the rule, by hand ─────────────────────────────────────────────────────────


def test_no_events_means_no_mastery_not_a_middling_one():
    assert mastery_of([], NOW) is None


@pytest.mark.parametrize(
    ("events", "score"),
    [
        ([ev("know")], 0.6667),  # A=1, B=0: 2/3
        ([ev("dont_know")], 0.3333),  # A=0, B=1: 1/3
        ([ev("unsure")], 0.5),  # A=0.5, B=0.5: 1.5/3
        ([ev("know"), ev("know"), ev("dont_know")], 0.6),  # A=2, B=1: 3/5
        ([ev("quiz_correct"), ev("quiz_correct")], 0.75),  # A=2: 3/4
        ([ev("quiz_wrong")], 0.3333),
        ([ev("know", 14)], 0.6),  # one half-life: A=0.5, B=0: 1.5/2.5
        ([ev("know", 28)], 0.5556),  # two half-lives: A=0.25: 1.25/2.25
        ([ev("dont_know", 14)], 0.4),  # A=0, B=0.5: 1/2.5
    ],
)
def test_the_score_is_a_decayed_beta_belief(events, score):
    got = mastery_of(events, NOW)
    assert got == MasteryScore(score, len(events))


def test_decay_counts_whole_days_and_an_event_from_the_future_counts_as_today():
    assert decay(NOW - timedelta(days=13, hours=23), NOW) == pytest.approx(
        0.5 ** (13 / HALF_LIFE_DAYS)
    )  # not yet 14 days
    assert decay(NOW - timedelta(days=14), NOW) == pytest.approx(0.5)
    assert decay(NOW + timedelta(days=3), NOW) == 1.0
    assert mastery_of([ev("know", -3)], NOW) == MasteryScore(0.6667, 1)


def test_old_praise_fades_towards_ignorance_and_recent_doubt_outweighs_it():
    old = mastery_of([ev("know", 140)], NOW)
    assert old is not None and 0.5 < old.score < 0.501  # ten half-lives: back to about 0.5
    mixed = mastery_of([ev("know", 28), ev("dont_know", 0)], NOW)
    assert mixed is not None and mixed.score < 0.5  # A=0.25, B=1: 1.25/3.25... below one half


def test_the_route_accepts_only_the_learners_own_ratings_until_the_studio_exists():
    assert ACCEPTED_NOW == ("know", "unsure", "dont_know")


# ── the store ─────────────────────────────────────────────────────────────────


def test_events_are_kept_in_order_per_page_and_survive_reopening(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    store.record(ev("know", 2, "a"))
    store.record(ev("unsure", 1, "a"))
    store.record(ev("dont_know", 0, "b"))
    assert [e.signal for e in store.events("a")] == ["know", "unsure"] and [
        e.signal for e in store.events("b")
    ] == ["dont_know"]
    again = SqliteLearnerStore(tmp_path / "learner.db")
    assert [e.signal for e in again.events("a")] == ["know", "unsure"]
    got = again.mastery(["a", "b", "c"], NOW)
    assert set(got) == {"a", "b"}  # a page with no events is absent, not zero
    assert got["b"] == MasteryScore(0.3333, 1)


def test_only_the_latest_events_of_a_page_are_kept(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    for i in range(MAX_EVENTS_PER_PAGE + 5):
        store.record(ev("know" if i >= 5 else "dont_know", 0, "a"))
    events = store.events("a")
    assert len(events) == MAX_EVENTS_PER_PAGE and all(
        e.signal == "know" for e in events
    )  # the five oldest are gone


def test_mastery_of_many_pages_batches_its_queries_and_an_unknown_signal_is_refused(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    store.record(ev("know", 0, "page-1234"))
    ids = [f"page-{i}" for i in range(1500)]  # over SQLite's bound-variable batch
    assert set(store.mastery(ids, NOW)) == {"page-1234"}
    assert store.mastery([], NOW) == {}
    with pytest.raises(ValueError):
        store.record(LearnerEvent("a", "praise", NOW))  # type: ignore[arg-type]


def test_everything_can_be_deleted(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    for page in "abc":
        store.record(ev("know", 0, page))
    assert store.delete_all() == 3 and store.mastery(["a", "b", "c"], NOW) == {}


# ── the blocks carry mastery, checked against the snapshot they were built from ──────────────────────────────────────


@pytest.fixture
def built(tmp_path: Path):
    graph, docs = world(tmp_path)
    return compile_vault(graph, docs), docs


def test_a_page_and_its_graph_carry_the_snapshots_mastery_and_null_where_there_is_none(built):
    vault, docs = built
    snapshot = {"rag": MasteryScore(0.6667, 3)}
    page = derive_concept_page(vault, docs, "rag", snapshot)
    assert page is not None and page["mastery"] == {"score": 0.6667, "events": 3}
    other = derive_concept_page(vault, docs, "self_rag", snapshot)
    assert other is not None and other["mastery"] is None
    graph = derive_notes_graph(vault, docs, None, "", snapshot)
    assert graph is not None
    assert {n["id"]: n["mastery"] for n in graph["nodes"]}["rag"] == 0.6667
    assert {n["id"]: n["mastery"] for n in graph["nodes"]}["self_rag"] is None


def test_a_block_is_checked_against_the_snapshot_and_a_claim_the_snapshot_does_not_hold_is_refused(
    built,
):
    vault, docs = built
    snapshot = {"rag": MasteryScore(0.6667, 3)}
    raw = concept_page("page:rag", "ready", data=derive_concept_page(vault, docs, "rag", snapshot))
    assert validate_block(raw, docs, vault=vault, mastery=snapshot).type == "ConceptPage"
    with pytest.raises(ValidationFailed):  # a mastery when no snapshot is given
        validate_block(raw, docs, vault=vault)
    with pytest.raises(ValidationFailed):  # a different score
        validate_block(raw, docs, vault=vault, mastery={"rag": MasteryScore(0.9, 3)})
    with pytest.raises(ValidationFailed):  # a different count
        validate_block(raw, docs, vault=vault, mastery={"rag": MasteryScore(0.6667, 4)})
    graph = notes_graph("g", "ready", data=derive_notes_graph(vault, docs, None, "", snapshot))
    assert validate_block(graph, docs, vault=vault, mastery=snapshot).type == "NotesGraph"
    forged = notes_graph("g", "ready", data=derive_notes_graph(vault, docs, None, "", snapshot))
    forged["data"]["nodes"][1]["mastery"] = 0.99  # a page the learner has not rated
    with pytest.raises(ValidationFailed):
        validate_block(forged, docs, vault=vault, mastery=snapshot)


def test_a_mastery_outside_zero_to_one_cannot_be_derived_from_events():
    for signals in (["know"] * 50, ["dont_know"] * 50, ["unsure"] * 7):
        got = mastery_of([ev(s) for s in signals], NOW)
        assert got is not None and 0 < got.score < 1


# ── over HTTP ─────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def with_vault(client, pdf_bytes):
    assert (
        client.post(
            "/ingest", files={"file": ("hybrid_retrieval.pdf", pdf_bytes, "application/pdf")}
        ).status_code
        == 200
    )
    assert client.post("/vault/rebuild").status_code == 200
    graph = client.get("/vault/notes").json()["blocks"][0]
    return client, graph["data"]["nodes"][0]["id"]


def test_a_rating_is_recorded_and_the_pages_and_the_graph_show_it(with_vault):
    client, page_id = with_vault
    first = client.get("/vault/notes", params={"page": page_id}).json()["blocks"]
    assert first[0]["data"]["mastery"] is None and all(
        n["mastery"] is None for n in first[1]["data"]["nodes"]
    )
    rated = client.post("/learner/events", json={"pageId": page_id, "signal": "know"})
    assert rated.status_code == 200 and rated.json() == {
        "pageId": page_id,
        "mastery": {"score": 0.6667, "events": 1},
    }
    client.post("/learner/events", json={"pageId": page_id, "signal": "dont_know"})
    after = client.get("/vault/notes", params={"page": page_id}).json()["blocks"]
    assert after[0]["data"]["mastery"] == {"score": 0.5, "events": 2}  # A=1, B=1: 2/4
    assert {n["id"]: n["mastery"] for n in after[1]["data"]["nodes"]}[page_id] == 0.5


def test_the_route_refuses_an_unknown_page_a_quiz_signal_and_a_missing_vault(client, with_vault):
    c, page_id = with_vault
    assert (
        c.post("/learner/events", json={"pageId": "no_such_page", "signal": "know"}).status_code
        == 404
    )
    refused = c.post("/learner/events", json={"pageId": page_id, "signal": "quiz_correct"})
    assert (
        refused.status_code == 422 and refused.json()["code"] == "validation_failed"
    )  # until the Studio generators exist
    assert c.post("/learner/events", json={"pageId": page_id}).status_code == 422
    assert (
        c.get("/vault/notes", params={"page": page_id}).json()["blocks"][0]["data"]["mastery"]
        is None
    )  # nothing was recorded


def test_the_learner_can_forget_everything(with_vault):
    client, page_id = with_vault
    client.post("/learner/events", json={"pageId": page_id, "signal": "know"})
    assert client.delete("/learner").status_code == 204
    assert (
        client.get("/vault/notes", params={"page": page_id}).json()["blocks"][0]["data"]["mastery"]
        is None
    )


def test_the_route_refuses_when_there_is_no_vault_yet(client):
    assert client.post("/learner/events", json={"pageId": "x", "signal": "know"}).status_code == 404
