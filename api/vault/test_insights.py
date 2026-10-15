"""Learning insights (D-43, V5): the derivation worked out by hand over the handmade vault of `api/vault/test_study.py`, and the store's
per-day count. The learner has rated bm25 (0.1, 3 events) and dense_retrieval (0.9, 5 events). No model call.

As of 2026-10-15: bm25 is under 0.5 so it is due now on every coming day; dense_retrieval (0.9, rated today) becomes due soon once 7 days
have passed, so it first counts on the 7th coming day (2026-10-22).
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from api.learner.mastery import LearnerEvent, MasteryScore
from api.learner.store import SqliteLearnerStore
from api.vault.insights import HORIZON_DAYS, MIN_ACTIVE_DAYS, WINDOW_DAYS, derive_insights
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)

AS_OF = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
MASTERY = {"bm25": MasteryScore(0.1, 3), "dense_retrieval": MasteryScore(0.9, 5)}
LAST = {"bm25": AS_OF - timedelta(days=1), "dense_retrieval": AS_OF}


def _activity(active_days: int, *, rising: bool = False) -> dict[str, int]:
    today = AS_OF.date()
    return {
        (today - timedelta(days=i)).isoformat(): (WINDOW_DAYS - i if rising else 1) for i in range(active_days)
    }


def test_coverage_and_the_three_bands(world):  # noqa: F811
    vault, _ = world
    data = derive_insights(vault, MASTERY, LAST, {}, AS_OF)
    assert data["asOf"] == "2026-10-15" and data["pages"] == len(vault.pages) and data["ratedPages"] == 2
    assert data["bands"] == {"needsWork": 1, "gettingThere": 0, "comfortable": 1}


def test_the_weakest_pages_come_lowest_first(world):  # noqa: F811
    vault, _ = world
    data = derive_insights(vault, MASTERY, LAST, {}, AS_OF)
    assert [w["pageId"] for w in data["weakest"]] == ["bm25", "dense_retrieval"]
    assert data["weakest"][0] == {"pageId": "bm25", "pageLabel": "BM25", "score": 0.1, "events": 3}


def test_an_event_about_a_page_the_vault_no_longer_holds_is_not_counted(world):  # noqa: F811
    vault, _ = world
    data = derive_insights(vault, {**MASTERY, "gone": MasteryScore(0.2, 1)}, LAST, {}, AS_OF)
    assert data["ratedPages"] == 2 and "gone" not in [w["pageId"] for w in data["weakest"]]


def test_the_window_has_every_day_oldest_first_with_zeros_included(world):  # noqa: F811
    vault, _ = world
    data = derive_insights(vault, MASTERY, LAST, {"2026-10-15": 4, "2026-10-13": 1, "2026-09-01": 9}, AS_OF)
    days = data["activity"]
    assert len(days) == WINDOW_DAYS and days[-1] == {"date": "2026-10-15", "count": 4}
    assert days[0]["date"] == "2026-10-02" and [d["count"] for d in days[-3:]] == [1, 0, 4]
    assert data["activeDays"] == 2  # the day outside the window is not counted


def test_no_trend_is_drawn_below_the_threshold_and_one_is_fitted_at_it(world):  # noqa: F811
    vault, _ = world
    below = derive_insights(vault, MASTERY, LAST, _activity(MIN_ACTIVE_DAYS - 1), AS_OF)
    assert below["activeDays"] == MIN_ACTIVE_DAYS - 1 and below["trend"] is None
    at = derive_insights(vault, MASTERY, LAST, _activity(MIN_ACTIVE_DAYS), AS_OF)
    assert at["trend"] is not None and len(at["trend"]["movingAverage"]) == WINDOW_DAYS


def test_a_rising_series_has_a_positive_slope_and_a_flat_one_has_none(world):  # noqa: F811
    vault, _ = world
    rising = derive_insights(vault, MASTERY, LAST, _activity(WINDOW_DAYS, rising=False) | {"2026-10-15": 9}, AS_OF)
    assert rising["trend"] is not None and rising["trend"]["slopePerDay"] > 0
    flat = derive_insights(vault, MASTERY, LAST, _activity(WINDOW_DAYS), AS_OF)
    assert flat["trend"] is not None and flat["trend"]["slopePerDay"] == 0
    assert set(flat["trend"]["movingAverage"]) == {1.0}


def test_the_workload_applies_the_schedules_rule_forward(world):  # noqa: F811
    vault, _ = world
    data = derive_insights(vault, MASTERY, LAST, {}, AS_OF)
    assert [w["date"] for w in data["workload"]] == [f"2026-10-{d}" for d in range(16, 23)]
    assert len(data["workload"]) == HORIZON_DAYS
    # bm25 is under 0.5: due on every coming day; dense_retrieval (0.9) is due soon only once 7 days have passed since it was rated
    assert [w["due"] for w in data["workload"]] == [1, 1, 1, 1, 1, 1, 2]


def test_the_same_inputs_give_the_same_insights(world):  # noqa: F811
    vault, _ = world
    assert derive_insights(vault, MASTERY, LAST, _activity(9), AS_OF) == derive_insights(vault, MASTERY, LAST, _activity(9), AS_OF)


def test_the_store_counts_events_per_utc_day_inside_the_window(tmp_path: Path):
    store = SqliteLearnerStore(tmp_path / "learner.db")
    for page, signal, when in [
        ("bm25", "know", datetime(2026, 10, 15, 1, 0, tzinfo=UTC)),
        ("bm25", "unsure", datetime(2026, 10, 15, 23, 0, tzinfo=UTC)),
        ("rrf", "dont_know", datetime(2026, 10, 13, 12, 0, tzinfo=UTC)),
        ("rrf", "know", datetime(2026, 9, 1, 12, 0, tzinfo=UTC)),
    ]:
        store.record(LearnerEvent(page, signal, when))  # type: ignore[arg-type]
    got = store.daily_activity(date(2026, 10, 2), date(2026, 10, 15))
    assert dict(got) == {"2026-10-15": 2, "2026-10-13": 1}
