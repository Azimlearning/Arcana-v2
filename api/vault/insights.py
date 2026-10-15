"""Learning insights (D-43, V5): the VERA "Analytics" function as a learning tool. Where VERA forecast stakeholder engagement, this shows the
learner their own position: how much of the vault they have rated, how well, what is weakest, how active the last two weeks were, and how
many pages will be due for review each day of the coming week.

`derive_insights` returns the exact `data` of a `LearningInsights` block, and the validator runs it again to check one. No model, no
spend, nothing fitted that the data cannot support:

    coverage     rated pages of the vault's pages; three bands by the mastery words' thresholds (needs work, getting there, comfortable)
    weakest      the five lowest-mastery rated pages
    activity     ratings per day over the last `WINDOW_DAYS` days, zeros included
    trend        a least-squares line through those days and a 3-day trailing average, ONLY when at least `MIN_ACTIVE_DAYS` of the days
                 have activity; below that no line is drawn and the block says why (a slope through three points is not a trend)
    workload     for each of the next `HORIZON_DAYS` days, how many rated pages the review schedule's own fixed rule would have due
                 then, if nothing changes (the rule applied forward; further decay of mastery is not modelled)

The weekly seasonal adjustment VERA used is not built: a 14-day window holds two cycles at best, which cannot separate a weekly pattern
from noise. The limit is stated on the screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from api.learner.mastery import COMFORTABLE, GETTING_THERE, MasteryScore
from api.vault.review import _due
from api.vault.types import Vault
from api.vault.view import CAPS, _label

WINDOW_DAYS = 14
HORIZON_DAYS = 7
MAX_WEAKEST = 5
MIN_ACTIVE_DAYS = 7
MOVING_AVERAGE_DAYS = 3


def _trend(counts: list[int]) -> dict[str, Any]:
    n = len(counts)
    mean_x = (n - 1) / 2
    mean_y = sum(counts) / n
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    slope = sum((i - mean_x) * (c - mean_y) for i, c in enumerate(counts)) / denominator
    average = []
    for i in range(n):
        window = counts[max(0, i - MOVING_AVERAGE_DAYS + 1) : i + 1]
        average.append(round(sum(window) / len(window), 2))
    return {"slopePerDay": round(slope, 3), "movingAverage": average}


def derive_insights(
    vault: Vault,
    mastery: Mapping[str, MasteryScore] | None,
    last_rated: Mapping[str, datetime] | None,
    activity: Mapping[str, int] | None,
    as_of: datetime,
) -> dict[str, Any]:
    """The data of a `LearningInsights` as of the date of `as_of`."""
    today = as_of.date()
    rated = {p: m for p, m in sorted((mastery or {}).items()) if p in vault.pages}
    bands = {"needsWork": 0, "gettingThere": 0, "comfortable": 0}
    for held in rated.values():
        if held.score >= COMFORTABLE:
            bands["comfortable"] += 1
        elif held.score >= GETTING_THERE:
            bands["gettingThere"] += 1
        else:
            bands["needsWork"] += 1
    weakest = sorted(rated.items(), key=lambda kv: (kv[1].score, -kv[1].events, kv[0]))[:MAX_WEAKEST]

    days = [today - timedelta(days=WINDOW_DAYS - 1 - i) for i in range(WINDOW_DAYS)]
    series = [{"date": d.isoformat(), "count": int((activity or {}).get(d.isoformat(), 0))} for d in days]
    counts = [s["count"] for s in series]
    active = sum(1 for c in counts if c > 0)

    workload = []
    for k in range(1, HORIZON_DAYS + 1):
        day = today + timedelta(days=k)
        due = 0
        for page_id, held in rated.items():
            when = (last_rated or {}).get(page_id)
            since = max(0, (day - when.date()).days) if when is not None else 0
            if _due(held.score, since) in ("now", "soon"):
                due += 1
        workload.append({"date": day.isoformat(), "due": due})

    return {
        "asOf": today.isoformat(),
        "pages": len(vault.pages),
        "ratedPages": len(rated),
        "bands": bands,
        "weakest": [
            {"pageId": p, "pageLabel": _label(vault.pages[p].label), "score": m.score, "events": m.events} for p, m in weakest
        ],
        "activity": series,
        "activeDays": active,
        "trend": _trend(counts) if active >= MIN_ACTIVE_DAYS else None,
        "workload": workload,
    }


def insights_caps() -> dict[str, int]:
    return {
        "weakest": MAX_WEAKEST,
        "window_days": WINDOW_DAYS,
        "horizon_days": HORIZON_DAYS,
        "min_active_days": MIN_ACTIVE_DAYS,
        "label_chars": CAPS["label_chars"],
    }


def activity_window_start(today: date) -> date:
    return today - timedelta(days=WINDOW_DAYS - 1)
