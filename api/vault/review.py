"""The review schedule (P5 S3, D-42): which pages the learner should revisit and how soon, as a pure function of the vault, the learner's
mastery and when each page was last rated.

`derive_study_plan` returns the exact `data` of a `StudyPlan` block, and the validator runs it again to check one (as for the quiz and the
study set). No model, no trained scheduler (D-37 found no data worth one): a fixed rule over the mastery arithmetic the notes view already
shows (D-35 A6), which is the "fixed review interval" fallback the Mastery engine would have had.

    score under 0.5            due now (the learner said they do not know it, or it has decayed)
    score 0.5 to under 0.75    due soon once 2 days have passed since the last rating, else later
    score 0.75 or more         due soon once 7 days have passed since the last rating, else later

A page with no rating has no mastery and is not in the plan (it is for the study set to introduce, not to review). The plan is capped at
`MAX_ITEMS`, soonest first, and says how many rated pages it left out.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from api.learner.mastery import MasteryScore
from api.vault.types import Vault
from api.vault.view import _label

MAX_ITEMS = 10
DUE_NOW_BELOW = 0.5
SOON_AFTER_DAYS_MID = 2
SOON_AFTER_DAYS_HIGH = 7
HIGH = 0.75
_RANK = {"now": 0, "soon": 1, "later": 2}


def _due(score: float, days: int) -> str:
    if score < DUE_NOW_BELOW:
        return "now"
    after = SOON_AFTER_DAYS_HIGH if score >= HIGH else SOON_AFTER_DAYS_MID
    return "soon" if days >= after else "later"


def derive_study_plan(
    vault: Vault,
    mastery: Mapping[str, MasteryScore] | None,
    last_rated: Mapping[str, datetime] | None,
    as_of: datetime,
) -> dict[str, Any]:
    """The data of a `StudyPlan` as of the date of `as_of`: the rated pages, soonest first, with how many days it is since each was last
    rated (whole days, never negative)."""
    today = as_of.date()
    rows: list[tuple[int, float, int, str, dict[str, Any]]] = []
    for page_id, held in sorted((mastery or {}).items()):
        if page_id not in vault.pages:
            continue  # an event about a page the vault no longer holds is not in the plan
        when = (last_rated or {}).get(page_id)
        days = max(0, (today - when.date()).days) if when is not None else 0
        due = _due(held.score, days)
        item = {
            "pageId": page_id,
            "pageLabel": _label(vault.pages[page_id].label),
            "score": held.score,
            "events": held.events,
            "due": due,
            "daysSince": days,
        }
        rows.append((_RANK[due], held.score, -days, page_id, item))
    rows.sort(key=lambda r: r[:4])
    return {
        "asOf": today.isoformat(),
        "items": [r[4] for r in rows[:MAX_ITEMS]],
        "ratedPages": len(rows),
        "leftOut": max(0, len(rows) - MAX_ITEMS),
    }
