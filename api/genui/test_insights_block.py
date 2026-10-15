"""The `LearningInsights` block (D-43, V5): the validator by planted defects, the status rules, and the catalog and builder entries."""

import copy
from datetime import UTC, datetime, timedelta

import pytest

from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS, learning_insights
from api.genui.notes_catalog import LEARNING_INSIGHTS, NOTES_CATALOG
from api.genui.validate import validate_block
from api.learner.mastery import MasteryScore
from api.vault.insights import derive_insights, insights_caps
from api.vault.test_quiz import small  # noqa: F401  (a fixture the world fixture builds on)
from api.vault.test_study import world  # noqa: F401  (a fixture)

AS_OF = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
MASTERY = {"bm25": MasteryScore(0.1, 3), "dense_retrieval": MasteryScore(0.9, 5)}
LAST = {"bm25": AS_OF - timedelta(days=1), "dense_retrieval": AS_OF}
ACTIVITY = {(AS_OF.date() - timedelta(days=i)).isoformat(): 1 + (i % 3) for i in range(9)}  # nine active days: a trend is present


def block_of(vault, status="ready", activity=ACTIVITY):
    return learning_insights("insights", status, data=derive_insights(vault, MASTERY, LAST, activity, AS_OF))


def check(raw, vault, activity=ACTIVITY):
    return validate_block(raw, None, vault=vault, mastery=MASTERY, last_rated=LAST, activity=activity)  # type: ignore[arg-type]


def test_derived_insights_pass_the_validator(world):  # noqa: F811
    vault, _ = world
    block = check(block_of(vault), vault)
    assert block.type == "LearningInsights" and block.data.trend is not None  # type: ignore[union-attr]


def test_insights_are_refused_without_the_vault_they_are_checked_against(world):  # noqa: F811
    vault, _ = world
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault), None, mastery=MASTERY, last_rated=LAST, activity=ACTIVITY)  # type: ignore[arg-type]


def test_the_activity_the_block_was_made_from_is_part_of_what_is_checked(world):  # noqa: F811
    vault, _ = world
    raw = block_of(vault)
    with pytest.raises(ValidationFailed):  # a day that was never recorded as active
        check(raw, vault, activity={})


def _defects():
    def pages(d):
        d["pages"] = 99

    def rated(d):
        d["ratedPages"] = 7

    def bands(d):
        d["bands"]["comfortable"] = 2

    def weakest_order(d):
        d["weakest"].reverse()

    def weakest_score(d):
        d["weakest"][0]["score"] = 0.99

    def weakest_dropped(d):
        d["weakest"].pop()

    def activity_count(d):
        d["activity"][-1]["count"] = 50

    def activity_dropped(d):
        d["activity"].pop(0)

    def active_days(d):
        d["activeDays"] = 14

    def trend_slope(d):
        d["trend"]["slopePerDay"] = 5.0

    def trend_average(d):
        d["trend"]["movingAverage"][0] = 40.0

    def trend_removed(d):
        d["trend"] = None

    def workload_due(d):
        d["workload"][0]["due"] = 40

    def workload_dropped(d):
        d["workload"].pop()

    def as_of(d):
        d["asOf"] = "2026-10-14"

    def unknown_field(d):
        d["prediction"] = "You will master this by Friday."

    return [
        ("pages_changed", pages),
        ("rated_pages_changed", rated),
        ("band_changed", bands),
        ("weakest_order_changed", weakest_order),
        ("weakest_score_changed", weakest_score),
        ("weakest_dropped", weakest_dropped),
        ("daily_count_changed", activity_count),
        ("day_dropped", activity_dropped),
        ("active_days_changed", active_days),
        ("trend_slope_invented", trend_slope),
        ("trend_average_changed", trend_average),
        ("trend_removed_though_present", trend_removed),
        ("workload_changed", workload_due),
        ("workload_day_dropped", workload_dropped),
        ("day_changed", as_of),
        ("unknown_field", unknown_field),
    ]


@pytest.mark.parametrize("name,apply", _defects(), ids=[n for n, _ in _defects()])
def test_every_planted_defect_is_refused(world, name, apply):  # noqa: F811
    vault, _ = world
    raw = block_of(vault)
    check(copy.deepcopy(raw), vault)  # the undamaged block is accepted
    apply(raw["data"])
    with pytest.raises(ValidationFailed):
        check(raw, vault)


def test_a_trend_is_refused_where_the_data_cannot_support_one(world):  # noqa: F811
    vault, _ = world
    sparse = {AS_OF.date().isoformat(): 3}
    raw = block_of(vault, activity=sparse)
    assert raw["data"]["trend"] is None and check(copy.deepcopy(raw), vault, activity=sparse)
    raw["data"]["trend"] = {"slopePerDay": 0.1, "movingAverage": [0.0] * 14}  # a line through one active day
    with pytest.raises(ValidationFailed):
        check(raw, vault, activity=sparse)


def test_the_status_rules(world):  # noqa: F811
    vault, _ = world
    ready = block_of(vault)
    nothing = copy.deepcopy(ready)
    nothing["data"].update(ratedPages=0, weakest=[], bands={"needsWork": 0, "gettingThere": 0, "comfortable": 0})
    with pytest.raises(ValidationFailed):
        check(nothing, vault)
    as_empty = copy.deepcopy(ready)
    as_empty["meta"]["status"] = "empty"  # pages are rated: it must not claim otherwise
    with pytest.raises(ValidationFailed):
        check(as_empty, vault)
    loading = copy.deepcopy(ready)
    loading["meta"]["status"] = "loading"
    with pytest.raises(ValidationFailed):
        check(loading, vault)
    assert validate_block(learning_insights("insights", "loading"), None, vault=None).meta.status == "loading"  # type: ignore[arg-type]


def test_the_catalog_builder_and_caps_agree():
    assert "LearningInsights" in NOTES_CATALOG and BUILDERS["LearningInsights"] is learning_insights
    assert LEARNING_INSIGHTS.caps == insights_caps() == {
        "weakest": 5,
        "window_days": 14,
        "horizon_days": 7,
        "min_active_days": 7,
        "label_chars": 120,
    }
    assert LEARNING_INSIGHTS.fences.grounding == "vault_rederived" and LEARNING_INSIGHTS.precondition.strip()
