"""VectorStore: dense vectors behind an abstraction (constraint 6, D-09, D-14).

Vectors are 3,072-dim (text-embedding-3-large). Similarity is cosine and scores are higher-is-better,
so callers can rank without knowing the backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class VectorHit:
    id: str
    score: float
    """Cosine similarity, higher is closer."""


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        """Insert or replace vectors by id."""

    @abstractmethod
    def query(self, vector: Sequence[float], k: int = 10) -> list[VectorHit]:
        """The k nearest ids by cosine similarity, best first. Empty store gives an empty list."""

    @abstractmethod
    def delete(self, ids: Sequence[str]) -> None:
        """Remove vectors by id. Unknown ids are ignored."""

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def ids(self) -> list[str]:
        """Every stored id, for corpus parity checks."""

    @abstractmethod
    def save(self) -> None:
        """Persist to the backing store. A reopened store reads back the same vectors."""
