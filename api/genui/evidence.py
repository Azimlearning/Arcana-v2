"""Helpers for turning a stored chunk into a quote a block may cite (constraint 1).

Shared by the Research agent (a citation's quote) and the Composer (the quote behind an edge, a path step or a
grid cell). They live here, in a neutral module, so neither has to import the other. Every function returns a
**verbatim span of the whitespace-normalised chunk** (or None), which is exactly what `validate_block` demands of a
quote, so a quote chosen here cannot fail the validator's verbatim rule.

`excerpt_containing` and `label_in_quote` serve the relational grounding rule (catalog.md, "Conventions"): a quote that
backs a relation must contain the label of every entity the relation names.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from api.genui.text import MIN_QUOTE_CHARS, label_in_quote, normalise

QUOTE_CHARS = 240
__all__ = ["QUOTE_CHARS", "best_excerpt", "excerpt_containing", "label_in_quote", "normalise", "verified_quote"]
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]{3,}")


def _trim(span: str) -> str:
    """At most QUOTE_CHARS, cut on a word boundary (a prefix of a verbatim span is still a verbatim span)."""
    return span if len(span) <= QUOTE_CHARS else span[:QUOTE_CHARS].rsplit(" ", 1)[0]


def best_excerpt(chunk_text: str, segment_text: str) -> str:
    """The sentence of the chunk sharing the most words with the segment, at most QUOTE_CHARS long.
    A prefix of a sentence of the whitespace-normalised chunk, so always a verbatim span of it."""
    normal = normalise(chunk_text)
    wanted = set(_WORD.findall(segment_text.lower()))
    sentences = [s for s in _SENTENCE_BREAK.split(normal) if s] or [normal]
    best = max(sentences, key=lambda s: len(wanted & set(_WORD.findall(s.lower()))))
    return _trim(best)


def verified_quote(chunk_text: str, proposed: object) -> str | None:
    """The model's proposed quote if it is a verbatim, non-trivial span of the chunk, else None."""
    if not isinstance(proposed, str):
        return None
    quote, chunk = normalise(proposed), normalise(chunk_text)
    if not quote or quote not in chunk or len(quote) < min(MIN_QUOTE_CHARS, len(chunk)):
        return None
    return _trim(quote)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if b > a]


def _window(text: str, lowered: str, labels: list[str]) -> str | None:
    """The smallest stretch of the text holding every label, widened to word boundaries, if it fits QUOTE_CHARS."""
    best: tuple[int, int] | None = None
    for first in re.finditer(re.escape(labels[0]), lowered):
        a, b = first.start(), first.end()
        for label in labels[1:]:
            # The occurrence of this label nearest to the first one.
            near = min(
                (m for m in re.finditer(re.escape(label), lowered)),
                key=lambda m, a=a: abs(m.start() - a),
                default=None,
            )
            if near is None:
                a = b = -1
                break
            a, b = min(a, near.start()), max(b, near.end())
        if a < 0:
            return None
        if best is None or (b - a) < (best[1] - best[0]):
            best = (a, b)
    if best is None:
        return None
    a, b = best
    while a > 0 and text[a - 1] != " ":
        a -= 1
    while b < len(text) and text[b] != " ":
        b += 1
    return text[a:b] if b - a <= QUOTE_CHARS else None


def excerpt_containing(chunk_text: str, labels: Sequence[str]) -> str | None:
    """A verbatim span of the chunk, at most QUOTE_CHARS long, that contains **every** label (ignoring case and
    whitespace runs), or None. Prefers the shortest sentence, then two adjacent sentences, then the tightest window
    around the labels. A span shorter than the validator's minimum quote length is never returned (it would not be
    evidence), unless the whole chunk is shorter than that."""
    wanted = [normalise(label).lower() for label in labels]
    if not wanted or any(not w for w in wanted):
        return None
    text = normalise(chunk_text)
    lowered = text.lower()
    if any(w not in lowered for w in wanted):
        return None
    minimum = min(MIN_QUOTE_CHARS, len(text))
    sentences = _sentence_spans(text)
    candidates = [(a, b) for a, b in sentences]
    candidates += [(sentences[i][0], sentences[i + 1][1]) for i in range(len(sentences) - 1)]
    for a, b in sorted(candidates, key=lambda span: span[1] - span[0]):
        span = text[a:b]
        if len(span) < minimum or len(span) > QUOTE_CHARS:
            continue
        if all(label_in_quote(span, w) for w in wanted):
            return span
    window = _window(text, lowered, wanted)
    if window is not None and len(window) >= minimum and all(label_in_quote(window, w) for w in wanted):
        return window
    return None
