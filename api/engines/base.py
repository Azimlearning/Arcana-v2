"""Engines: trained tools behind one interface, additive to a heuristic (P3, D-12, D-37, hard constraint 6).

An `Engine` is a narrow trained model with `predict()` and `is_available()`. It is **additive, never substitutive**: it sits downstream of an
existing heuristic and, absent, failing or returning something it must not, the heuristic's output stands. `apply_rerank` is that rule for the one
engine kind built so far: a re-ranker may only **re-order** the candidates it is given (never add, drop or duplicate one), and any other outcome
returns the heuristic's order unchanged with the reason recorded. Nothing here calls a paid service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from api.core.logging import get_logger
from api.retrieval.types import RetrievedChunk

log = get_logger(__name__)


class Engine(ABC):
    """A trained, narrow model behind `predict()` and `is_available()`."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """True if the engine can run now (its runtime and weights are present). Must not raise."""

    @abstractmethod
    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The engine's output for `payload`. May raise: the caller falls back to the heuristic."""


class RerankEngine(Engine):
    """Scores candidate passages against a query. `predict({"query": str, "texts": list[str]})` returns `{"scores": list[float]}`, one per text."""


@dataclass(frozen=True)
class RerankOutcome:
    chunks: list[RetrievedChunk]
    used: bool
    """True only if the engine's order was applied."""
    reason: str | None
    """Why the heuristic order stood (None when the engine's order was used)."""
    scores: tuple[float, ...] = ()


def apply_rerank(
    engine: RerankEngine | None, query: str, candidates: Sequence[RetrievedChunk]
) -> RerankOutcome:
    """Re-order `candidates` by the engine's scores (higher first, ties kept in their original order), or return them unchanged with the reason.

    Falls back when: there is no engine, it is not available, it raises, it returns the wrong number of scores, or a score is not a finite number.
    The output is always a permutation of the input."""
    original = list(candidates)
    if engine is None:
        return RerankOutcome(original, False, "no engine")
    if len(original) < 2:
        return RerankOutcome(original, False, "fewer than two candidates")
    try:
        if not engine.is_available():
            return RerankOutcome(original, False, "engine unavailable")
        out = engine.predict({"query": query, "texts": [c.text for c in original]})
        scores = [float(s) for s in out["scores"]]
    except Exception as exc:  # an engine failing must never fail the turn: the heuristic stands
        log.warning("engine_failed", engine=getattr(engine, "name", "?"), error=type(exc).__name__)
        return RerankOutcome(original, False, f"engine failed: {type(exc).__name__}")
    if len(scores) != len(original):
        return RerankOutcome(original, False, "engine returned the wrong number of scores")
    if any(s != s or s in (float("inf"), float("-inf")) for s in scores):
        return RerankOutcome(original, False, "engine returned a score that is not a finite number")
    order = sorted(
        range(len(original)), key=lambda i: (-scores[i], i)
    )  # stable: ties keep the heuristic's order
    return RerankOutcome([original[i] for i in order], True, None, tuple(scores[i] for i in order))
