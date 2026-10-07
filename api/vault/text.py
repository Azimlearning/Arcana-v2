"""Text helpers for the vault (M2, D-35): hyphen-blind folding, whole-word phrase tests and sentence splitting.

The folding is the same as the atomic builder's `label_in_text` (PDF text breaks "retrieval-augmented" across a line and a model
repairs it), so a label found here is a label the builder would have found. A test pins the two together.
"""

from __future__ import annotations

import re
from functools import lru_cache

_HYPHEN_BREAK = re.compile(r"-\s*")
_TOKEN = re.compile(r"[a-z0-9]+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_BIBLIOGRAPHY = re.compile(
    r"arxiv|preprint|proceedings|\bdoi\b|\bpp\.|journal of|conference on|association for computational",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    """Whitespace collapsed, every hyphen (and the space a PDF leaves after one) removed, lowercase."""
    return _HYPHEN_BREAK.sub("", " ".join(text.split())).lower()


def tokens(folded: str) -> list[str]:
    """The alphanumeric runs of folded text."""
    return _TOKEN.findall(folded)


@lru_cache(maxsize=65536)
def _pattern(folded_label: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(folded_label)}(?![a-z0-9])")


def occurs(folded_text: str, folded_label: str) -> bool:
    """True if `folded_label` occurs in `folded_text` as a whole word or phrase. An empty label never matches."""
    return bool(folded_label) and _pattern(folded_label).search(folded_text) is not None


def split_sentences(text: str) -> list[str]:
    """The whitespace-normalised text cut after a full stop, question mark or exclamation mark followed by a space. Each piece
    is a verbatim span of the normalised text."""
    return [p for p in _SENTENCE_BREAK.split(" ".join(text.split())) if p]


def looks_bibliographic(sentence: str) -> bool:
    """True for a sentence that reads like a reference-list entry: it holds a strong marker of one (arXiv, preprint,
    proceedings, doi, pp., journal of, conference on, association for computational). "et al" is not a marker: prose cites
    "Lewis et al." too. Such a sentence makes no co-mention links (D-35 amendment A1): a reference entry names the
    concepts of a cited title, not a relation between them."""
    return _BIBLIOGRAPHY.search(sentence) is not None
