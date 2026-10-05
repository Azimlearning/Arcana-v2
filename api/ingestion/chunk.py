# Adapted from Azimlearning/Arcana (v1), api/ingestion/chunker.py @ 9a3d67f.
# Read in full and adapted for v2 (D-01, D-16): emits v2's stores.doc_store.Chunk (with an ordinal)
# in place of v1's internal Chunk; window logic and boundary preference are unchanged.
"""Fixed-window chunker with paragraph and sentence preferring boundaries.

Pages are joined into one stream (blank-line separated) and a window of `target_chars` slides
across it, carrying `overlap_chars`. Each window ends at a paragraph boundary if one is near the
end, else a sentence boundary, else a hard cut. A chunk records the page it STARTS on: that is the
page a citation points at.

Settings come from the benchmark protocol (chunk 1,200 / overlap 200) and must not drift.
"""

from __future__ import annotations

from bisect import bisect_right

from api.ingestion.types import PageText, make_chunk_id
from api.stores.doc_store import Chunk

DEFAULT_TARGET_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 200
PAGE_SEPARATOR = "\n\n"
# Within this many characters of the window end, prefer a real boundary over a hard cut.
BOUNDARY_LOOKBACK = 200


def chunk(
    pages: list[PageText],
    *,
    doc_id: str,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    if target_chars < 1:
        raise ValueError(f"target_chars must be >= 1 (got {target_chars})")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError(
            f"overlap_chars must be in [0, target_chars) (got {overlap_chars} with target {target_chars})"
        )
    if not pages:
        return []

    full_text, page_starts = _flatten(pages)
    if not full_text.strip():
        return []

    chunks: list[Chunk] = []
    pos = 0
    while pos < len(full_text):
        while pos < len(full_text) and full_text[pos].isspace():
            pos += 1  # never start a chunk on whitespace
        if pos >= len(full_text):
            break

        end = min(pos + target_chars, len(full_text))
        if end < len(full_text):
            end = _prefer_clean_boundary(full_text, pos, end)

        text = full_text[pos:end].strip()
        if text:
            page = _page_for_offset(pos, page_starts)
            chunks.append(
                Chunk(
                    id=make_chunk_id(doc_id=doc_id, page=page, char_offset=pos, text=text),
                    doc_id=doc_id,
                    ordinal=len(chunks),
                    page=page,
                    text=text,
                )
            )

        if end >= len(full_text):
            break
        next_pos = end - overlap_chars
        pos = next_pos if next_pos > pos else end  # always make progress

    return chunks


def _flatten(pages: list[PageText]) -> tuple[str, list[tuple[int, int]]]:
    """Join page texts; return the text and [(start offset, page number)] for page attribution."""
    parts: list[str] = []
    starts: list[tuple[int, int]] = []
    cursor = 0
    for p in pages:
        starts.append((cursor, p.page))
        parts.append(p.text)
        cursor += len(p.text)
        parts.append(PAGE_SEPARATOR)
        cursor += len(PAGE_SEPARATOR)
    full = "".join(parts)
    if full.endswith(PAGE_SEPARATOR):
        full = full[: -len(PAGE_SEPARATOR)]
    return full, starts


def _prefer_clean_boundary(text: str, start: int, end: int) -> int:
    """Pull `end` back to a paragraph or sentence boundary, but only if the chunk stays at least
    half the target size: a boundary two characters in would leave a degenerate chunk."""
    target = end - start
    min_acceptable = start + max(1, target // 2)
    window_lo = max(min_acceptable, end - BOUNDARY_LOOKBACK)
    para = text.rfind("\n\n", window_lo, end)
    if para != -1:
        return para
    sentence = text.rfind(". ", window_lo, end)
    if sentence != -1:
        return sentence + 2  # keep the period, cut after the space
    return end


def _page_for_offset(offset: int, starts: list[tuple[int, int]]) -> int:
    idx = bisect_right([s[0] for s in starts], offset) - 1
    return starts[max(idx, 0)][1]
