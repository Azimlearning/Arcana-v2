"""LearnerStore: the learner's events behind an abstraction (constraint 6, D-35 A6), and a local SQLite implementation.

Personal data, kept apart from the documents and the vault: its own file (`learner.db`), events only (a page id, a signal and a
time: no document text, no identity), and deletable as a whole. The vault is derived and rebuilt; this is not.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from api.learner.mastery import SIGNALS, LearnerEvent, MasteryScore, Signal, mastery_of

MAX_EVENTS_PER_PAGE = 200
"""The oldest events of a page are dropped past this: a page's mastery never depends on more than its latest 200 events."""


class LearnerStore(ABC):
    @abstractmethod
    def record(self, event: LearnerEvent) -> None: ...

    @abstractmethod
    def events(self, page_id: str) -> list[LearnerEvent]:
        """A page's events, oldest first."""

    @abstractmethod
    def mastery(
        self, page_ids: Collection[str], now: datetime | None = None
    ) -> Mapping[str, MasteryScore]:
        """The mastery of each of these pages that has events, at `now`. A page with none is absent."""

    @abstractmethod
    def delete_all(self) -> int:
        """Remove every event. Returns how many were removed."""


class SqliteLearnerStore(LearnerStore):
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS learner_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL, signal TEXT NOT NULL, at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS learner_events_page ON learner_events (page_id, id)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def record(self, event: LearnerEvent) -> None:
        if event.signal not in SIGNALS:
            raise ValueError(f"unknown signal {event.signal!r}")
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO learner_events (page_id, signal, at) VALUES (?, ?, ?)",
                (event.page_id, event.signal, event.at.astimezone(UTC).isoformat()),
            )
            db.execute(
                "DELETE FROM learner_events WHERE page_id = ? AND id NOT IN "
                "(SELECT id FROM learner_events WHERE page_id = ? ORDER BY id DESC LIMIT ?)",
                (event.page_id, event.page_id, MAX_EVENTS_PER_PAGE),
            )

    def events(self, page_id: str) -> list[LearnerEvent]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT signal, at FROM learner_events WHERE page_id = ? ORDER BY id", (page_id,)
            ).fetchall()
        return [LearnerEvent(page_id, signal, datetime.fromisoformat(at)) for signal, at in rows]

    def mastery(
        self, page_ids: Collection[str], now: datetime | None = None
    ) -> Mapping[str, MasteryScore]:
        wanted = sorted(set(page_ids))
        out: dict[str, MasteryScore] = {}
        if not wanted:
            return out
        grouped: dict[str, list[LearnerEvent]] = {}
        with closing(self._connect()) as db:
            for start in range(0, len(wanted), 500):  # SQLite's limit on bound variables
                batch = wanted[start : start + 500]
                marks = ",".join("?" * len(batch))
                for page_id, signal, at in db.execute(
                    f"SELECT page_id, signal, at FROM learner_events WHERE page_id IN ({marks}) ORDER BY id",
                    batch,
                ):
                    grouped.setdefault(page_id, []).append(
                        LearnerEvent(page_id, signal, datetime.fromisoformat(at))
                    )
        for page_id, events in grouped.items():
            score = mastery_of(events, now)
            if score is not None:
                out[page_id] = score
        return out

    def delete_all(self) -> int:
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM learner_events").rowcount


__all__ = ["MAX_EVENTS_PER_PAGE", "LearnerStore", "Signal", "SqliteLearnerStore"]
