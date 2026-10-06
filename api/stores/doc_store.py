"""DocStore: documents, chunks and turns behind an abstraction (constraint 6, D-09).

Returns plain dataclasses, never ORM objects, so callers do not depend on the backend. The spend
ledger is not here: it lives in api/llm/ledger.py and shares the SQLite file.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

DocStatus = Literal["pending", "parsing", "embedding", "ready", "failed"]


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    source_path: str
    status: DocStatus
    size_bytes: int
    error: str | None
    created_at: str


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    ordinal: int
    """Position within the document, from 0."""
    page: int | None
    """1-based page the chunk starts on."""
    text: str


@dataclass(frozen=True)
class Turn:
    id: str
    created_at: str
    query: str
    outcome: Literal["ok", "error"]
    latency_ms: int
    error_code: str | None


@dataclass(frozen=True)
class StoredPattern:
    """A saved UI pattern as the store keeps it (D-31). `params_json` is a serialised list of parameters: strings only,
    never evidence, block data or document text. The caller validates it on the way in and out."""

    id: str
    name: str
    template_id: str
    template_version: int
    params_json: str
    layout_mode: str
    state: str
    use_count: int
    created_at: str
    last_used_at: str | None


class DocStore(ABC):
    @abstractmethod
    def put_document(self, doc: Document) -> None:
        """Insert or replace a document row."""

    @abstractmethod
    def set_status(self, doc_id: str, status: DocStatus, error: str | None = None) -> None: ...

    @abstractmethod
    def get_document(self, doc_id: str) -> Document | None: ...

    @abstractmethod
    def list_documents(self) -> list[Document]: ...

    @abstractmethod
    def put_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Insert or replace chunks."""

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Chunk | None: ...

    @abstractmethod
    def get_chunks(self, chunk_ids: Sequence[str]) -> dict[str, Chunk]:
        """The stored chunks among `chunk_ids`, keyed by id. Missing ids are absent."""

    @abstractmethod
    def chunks_for_document(self, doc_id: str) -> list[Chunk]:
        """In ordinal order."""

    @abstractmethod
    def all_chunks(self) -> list[Chunk]:
        """Every chunk, for building the BM25 index."""

    @abstractmethod
    def delete_document(self, doc_id: str) -> list[str]:
        """Delete the document and its chunks. Returns the deleted chunk ids."""

    @abstractmethod
    def record_turn(self, turn: Turn) -> None: ...

    @abstractmethod
    def turns(self) -> list[Turn]: ...

    @abstractmethod
    def record_trace(self, turn_id: str, trace_json: str) -> None:
        """Keep the turn's trace (serialised TurnTrace) under the turn id. Replaces an earlier one."""

    @abstractmethod
    def get_trace(self, turn_id: str) -> str | None:
        """The serialised trace recorded for the turn, or None. The caller validates it."""

    @abstractmethod
    def record_view(self, turn_id: str, view_json: str) -> None:
        """Keep the turn's view record (which reusable components it showed, with their parameters). Replaces one."""

    @abstractmethod
    def get_view(self, turn_id: str) -> str | None:
        """The serialised view record for the turn, or None. The caller validates it."""

    @abstractmethod
    def put_pattern(self, pattern: StoredPattern) -> StoredPattern:
        """Keep a pattern. If one with the same id exists it is kept as it is and returned: saving the same view
        twice is one pattern."""

    @abstractmethod
    def get_pattern(self, pattern_id: str) -> StoredPattern | None: ...

    @abstractmethod
    def list_patterns(self) -> list[StoredPattern]:
        """Every saved pattern, oldest first."""

    @abstractmethod
    def delete_pattern(self, pattern_id: str) -> bool:
        """Delete a pattern. True if there was one."""

    @abstractmethod
    def mark_pattern_used(self, pattern_id: str, when: str) -> None:
        """Count one use and stamp the time. A no-op for an unknown id."""

    @abstractmethod
    def update_pattern(self, pattern_id: str, *, state: str, template_version: int) -> None:
        """Set a pattern's state and the template version it is current with (re-verification)."""
