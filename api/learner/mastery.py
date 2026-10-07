"""The mastery rule (M2.7, D-35 A6): a learner's belief about a concept, from their own events. Deterministic, no model.

Each event adds to a pair (a, b): know (1, 0), unsure (0.5, 0.5), dont_know (0, 1), quiz_correct (1, 0), quiz_wrong (0, 1), each
multiplied by a decay of 0.5 ** (whole days since the event / HALF_LIFE_DAYS). With A and B the sums,

    score = (A + 1) / (A + B + 2)       rounded to 4 places, in [0, 1]

and a page with no events has no mastery. The score is a belief that decays towards ignorance, not a grade.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Signal = Literal["know", "unsure", "dont_know", "quiz_correct", "quiz_wrong"]
SIGNALS: tuple[Signal, ...] = ("know", "unsure", "dont_know", "quiz_correct", "quiz_wrong")
ACCEPTED_NOW: tuple[Signal, ...] = ("know", "unsure", "dont_know")
"""What the route accepts until the Studio generators exist (P5): the learner's own ratings."""
HALF_LIFE_DAYS = 14.0
CONTRIBUTION: dict[Signal, tuple[float, float]] = {
    "know": (1.0, 0.0),
    "unsure": (0.5, 0.5),
    "dont_know": (0.0, 1.0),
    "quiz_correct": (1.0, 0.0),
    "quiz_wrong": (0.0, 1.0),
}
COMFORTABLE = 0.67
GETTING_THERE = 0.4
"""Where the screen's words change (comfortable, getting there, needs work). The wire carries the score, not these words."""


@dataclass(frozen=True)
class LearnerEvent:
    page_id: str
    signal: Signal
    at: datetime
    """When it happened (UTC)."""


@dataclass(frozen=True)
class MasteryScore:
    score: float
    events: int


def decay(at: datetime, now: datetime) -> float:
    """0.5 ** (whole days since `at` / the half-life). An event from the future counts as today."""
    days = max((now - at).days, 0)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def mastery_of(events: Iterable[LearnerEvent], now: datetime | None = None) -> MasteryScore | None:
    """The mastery these events (all of one page) give at `now`, or None if there are none."""
    moment = now or datetime.now(UTC)
    a = b = 0.0
    count = 0
    for event in events:
        positive, negative = CONTRIBUTION[event.signal]
        weight = decay(event.at, moment)
        a += positive * weight
        b += negative * weight
        count += 1
    if count == 0:
        return None
    return MasteryScore(round((a + 1) / (a + b + 2), 4), count)
