"""Backend-only ingestion types."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class PageText:
    page: int
    """1-based."""
    text: str


@dataclass(frozen=True, slots=True)
class ParsedPdf:
    title: str | None
    """From the PDF's metadata, when it has one."""
    pages: list[PageText]


@dataclass(frozen=True, slots=True)
class IngestResult:
    doc_id: str
    title: str
    status: str
    """"ready" or "failed"."""
    chunk_count: int
    node_count: int
    edge_count: int
    extraction_failures: int
    """Chunks whose model output could not be parsed. They keep their text and vector, only
    their graph contribution is missing."""
    error: str | None


def doc_id_for(raw: bytes) -> str:
    """Content-addressed: the same file always gets the same id, so re-ingest replaces cleanly."""
    return sha256(raw).hexdigest()[:16]


def make_chunk_id(*, doc_id: str, page: int, char_offset: int, text: str) -> str:
    """Deterministic and position-sensitive: identical paragraphs in one document get distinct ids."""
    digest = sha256(f"{doc_id}|{page}|{char_offset}|{text}".encode()).hexdigest()[:16]
    return f"{doc_id}_c_{digest}"
