"""The review schedule (P5 S3, D-42): every expected value worked out by hand from the rule in `api/vault/review.py`."""

from datetime import UTC, datetime, timedelta

from api.learner.mastery import MasteryScore
from api.vault.review import MAX_ITEMS, derive_study_plan
from api.vault.types import ConceptPage, Vault

NOW = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)


def vault_of(*ids: str) -> Vault:
    pages = {i: ConceptPage(i, f"page {i}", (), (i,), None, ("d1",), ("c1",), ()) for i in ids}
    return Vault("vault-1", 1, pages, [], [])


def ago(days: int) -> datetime:
    return NOW - timedelta(days=days, hours=3)


def test_the_rule_by_hand():
    vault = vault_of("a", "b", "c", "d", "e", "f")
    mastery = {
        "a": MasteryScore(0.2, 3),  # low: due now, whatever the age
        "b": MasteryScore(0.6, 2),  # mid, 3 days: soon
        "c": MasteryScore(0.6, 2),  # mid, 1 day: later
        "d": MasteryScore(0.9, 5),  # high, 8 days: soon
        "e": MasteryScore(0.9, 5),  # high, 3 days: later
        "f": MasteryScore(0.49, 1),  # just under the line: now
    }
    last = {"a": ago(0), "b": ago(3), "c": ago(1), "d": ago(8), "e": ago(3), "f": ago(40)}
    plan = derive_study_plan(vault, mastery, last, NOW)
    assert plan["asOf"] == "2026-10-15" and plan["ratedPages"] == 6 and plan["leftOut"] == 0
    due = {i["pageId"]: i["due"] for i in plan["items"]}
    assert due == {"a": "now", "f": "now", "b": "soon", "d": "soon", "c": "later", "e": "later"}
    # soonest first, then the lowest score, then the longest unseen, then id
    assert [i["pageId"] for i in plan["items"]] == ["a", "f", "b", "d", "c", "e"]
    assert {i["pageId"]: i["daysSince"] for i in plan["items"]} == {"a": 0, "b": 3, "c": 1, "d": 8, "e": 3, "f": 40}


def test_a_page_with_no_rating_or_not_in_the_vault_is_not_in_the_plan():
    vault = vault_of("a", "b")
    plan = derive_study_plan(vault, {"a": MasteryScore(0.3, 1), "ghost": MasteryScore(0.1, 1)}, {"a": ago(1)}, NOW)
    assert [i["pageId"] for i in plan["items"]] == ["a"] and plan["ratedPages"] == 1  # b has none; ghost is not a page
    assert derive_study_plan(vault, None, None, NOW)["items"] == []


def test_the_plan_is_capped_and_says_how_many_it_left_out():
    ids = [f"p{i:02d}" for i in range(14)]
    vault = vault_of(*ids)
    mastery = {i: MasteryScore(0.1, 1) for i in ids}
    plan = derive_study_plan(vault, mastery, {}, NOW)
    assert len(plan["items"]) == MAX_ITEMS and plan["leftOut"] == 4 and plan["ratedPages"] == 14


def test_it_is_deterministic_and_never_negative_in_days():
    vault = vault_of("a")
    future = NOW + timedelta(days=3)  # a clock that moved back must not give a negative age
    first = derive_study_plan(vault, {"a": MasteryScore(0.7, 1)}, {"a": future}, NOW)
    assert first == derive_study_plan(vault, {"a": MasteryScore(0.7, 1)}, {"a": future}, NOW)
    assert first["items"][0]["daysSince"] == 0 and first["items"][0]["due"] == "later"
