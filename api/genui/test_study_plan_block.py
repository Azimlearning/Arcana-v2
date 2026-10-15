"""The `StudyPlan` block (P5 S3, D-42): the validator by planted defects, the learner store's rating dates, and the Composer's schedule in a
turn. The vault is the handmade one of `api/vault/test_quiz.py`; no model call anywhere."""

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.agents.test_agents import GRAPH
from api.core.budget import TokenBudget
from api.core.errors import ValidationFailed
from api.fakes import fake_llm_responder
from api.genui.builders import BUILDERS, study_plan
from api.genui.generated import StudyPlan
from api.genui.notes_catalog import NOTES_CATALOG, STUDY_PLAN
from api.genui.validate import validate_block
from api.learner.mastery import LearnerEvent, MasteryScore
from api.learner.store import SqliteLearnerStore
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult, RetrievedChunk
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.review import MAX_ITEMS, derive_study_plan
from api.vault.test_quiz import DOC_OF, PAGE_OF, TEXT, fill

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
MASTERY = {"bm25": MasteryScore(0.2, 3), "dense_retrieval": MasteryScore(0.9, 6), "rrf": MasteryScore(0.6, 2)}
LAST = {"bm25": NOW - timedelta(days=1), "dense_retrieval": NOW - timedelta(days=9), "rrf": NOW - timedelta(days=3)}


@pytest.fixture
def world(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "plan.db"))
    return fill(docs), docs


def raw_block(vault, status="ready"):
    return study_plan("plan", status, data=derive_study_plan(vault, MASTERY, LAST, NOW))


def check(raw, vault, docs, mastery=MASTERY, last=LAST):
    return validate_block(raw, docs, vault=vault, mastery=mastery, last_rated=last)


def test_a_derived_schedule_passes_and_orders_soonest_first(world):
    vault, docs = world
    block = check(raw_block(vault), vault, docs)
    assert isinstance(block, StudyPlan)
    assert [(i.pageId, i.due) for i in block.data.items] == [("bm25", "now"), ("rrf", "soon"), ("dense_retrieval", "soon")]
    assert block.data.asOf == "2026-10-15" and block.data.ratedPages == 3


def test_a_schedule_is_refused_without_the_vault_and_a_bad_date_is_refused(world):
    vault, docs = world
    with pytest.raises(ValidationFailed):
        validate_block(raw_block(vault), docs, mastery=MASTERY, last_rated=LAST)
    raw = raw_block(vault)
    raw["data"]["asOf"] = "last tuesday"
    with pytest.raises(ValidationFailed):
        check(raw, vault, docs)


def _defects():
    def due(d):
        d["items"][0]["due"] = "later"

    def days(d):
        d["items"][1]["daysSince"] = 0

    def score(d):
        d["items"][0]["score"] = 0.99

    def events(d):
        d["items"][0]["events"] = 40

    def label(d):
        d["items"][0]["pageLabel"] = "Something else"

    def page(d):
        d["items"][0]["pageId"] = "ghost"

    def order(d):
        d["items"].reverse()

    def dropped(d):
        d["items"].pop()

    def added(d):
        d["items"].append(copy.deepcopy(d["items"][0]))

    def rated(d):
        d["ratedPages"] = 9

    def left_out(d):
        d["leftOut"] = 3

    def as_of(d):
        d["asOf"] = "2026-10-20"  # a different day gives different day counts

    def unknown(d):
        d["note"] = "review everything"

    return [
        ("due_changed", due),
        ("days_changed", days),
        ("score_changed", score),
        ("events_changed", events),
        ("label_changed", label),
        ("page_forged", page),
        ("order_changed", order),
        ("item_dropped", dropped),
        ("item_added", added),
        ("rated_pages_changed", rated),
        ("left_out_changed", left_out),
        ("day_changed", as_of),
        ("unknown_field", unknown),
    ]


@pytest.mark.parametrize("name,apply", _defects(), ids=[n for n, _ in _defects()])
def test_every_planted_defect_is_refused(world, name, apply):
    vault, docs = world
    raw = raw_block(vault)
    check(copy.deepcopy(raw), vault, docs)  # the undamaged block is accepted
    apply(raw["data"])
    with pytest.raises(ValidationFailed):
        check(raw, vault, docs)


def test_the_status_rules(world):
    vault, docs = world
    nothing = study_plan("plan", "ready", data={"asOf": "2026-10-15", "items": [], "ratedPages": 0, "leftOut": 0})
    with pytest.raises(ValidationFailed):  # ready with nothing in it
        check(nothing, vault, docs, mastery={}, last={})
    assert check(study_plan("plan", "empty", as_of="2026-10-15"), vault, docs, mastery={}, last={}).meta.status == "empty"
    rated_but_empty = raw_block(vault, "empty")
    with pytest.raises(ValidationFailed):  # pages are rated: it must not claim there are none
        check(rated_but_empty, vault, docs)
    loading = raw_block(vault, "loading")
    with pytest.raises(ValidationFailed):  # a placeholder carries nothing
        check(loading, vault, docs)


def test_the_catalog_builder_and_caps_agree():
    assert "StudyPlan" in NOTES_CATALOG and BUILDERS["StudyPlan"] is study_plan
    assert STUDY_PLAN.caps == {"items": MAX_ITEMS, "label_chars": 120}
    assert STUDY_PLAN.fences.grounding == "vault_rederived" and STUDY_PLAN.supplied_by == ("vault",)


def test_the_store_gives_the_date_of_the_last_rating_of_each_page(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    store.record(LearnerEvent("bm25", "know", NOW - timedelta(days=5)))
    store.record(LearnerEvent("bm25", "unsure", NOW - timedelta(days=2)))
    store.record(LearnerEvent("rrf", "dont_know", NOW - timedelta(days=7)))
    last = store.last_rated(["bm25", "rrf", "never"])
    assert last == {"bm25": NOW - timedelta(days=2), "rrf": NOW - timedelta(days=7)}
    assert store.last_rated([]) == {}


async def test_a_review_turn_shows_the_schedule_from_the_learners_real_ratings(world, tmp_path: Path):
    vault, docs = world
    learner = SqliteLearnerStore(tmp_path / "learner.db")
    now = datetime.now(UTC)
    learner.record(LearnerEvent("bm25", "dont_know", now - timedelta(days=1)))
    learner.record(LearnerEvent("rrf", "know", now - timedelta(days=1)))

    async def retrieve(q: str) -> RetrievalResult:
        chunks = [RetrievedChunk(c, DOC_OF[c], TEXT[c], PAGE_OF[c], 1.0, ("dense",)) for c in ("c1", "c2")]
        return RetrievalResult(chunks=chunks, per_signal={})

    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'turn.db'}"), None)
    ctx = TurnContext(
        docs,
        retrieve,
        LLMService(FakeProvider(fake_llm_responder), None, ledger),
        TokenBudget(),
        "blk",
        roster=default_roster(),
        vault=vault,
        learner=learner,
    )
    state = await GRAPH.ainvoke({"question": "What should I review today? Give me a review schedule"}, context=ctx)
    composition = state["composition"]
    assert ctx.intent == "study"
    plan = next(b for b in composition.blocks if b.type == "StudyPlan")
    ids = [i.pageId for i in plan.data.items]  # type: ignore[union-attr]
    assert ids[0] == "bm25" and set(ids) == {"bm25", "rrf"}
    assert plan.data.items[0].due == "now"  # type: ignore[union-attr]
    assert composition.blocks[0].type == "CitedSummary"
