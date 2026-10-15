"""Study sets from the vault (P5 S2, D-42): flashcards, blurting, Cornell notes and a Socratic turn, as pure functions of the vault, the
stored passages and the learner's mastery.

`derive_study_set` returns the exact `data` of a `StudySet` block. The Composer builds the block from it and the validator runs it again
to check one, as for the quiz and the concept page, so a block that says anything else is refused. Nothing here calls a model: every
sentence shown is a verbatim span of a stored passage (a definition, a claim, or the evidence of an asserted link) and is cited.

What each kind asks (the prompts are fixed templates over a page's name; the learner is never shown the sentence first):

  flashcard   the page's name; the reveal is its definition (or, failing that, a claim).
  blurt       "write down what you remember about X"; the reveal is up to four sentences the documents state about it.
  cornell     a cue question per page and up to three notes; the set's `summary` is the first page's definition.
  socratic    "how do A and B relate?" for an asserted link (with a focus page, one per link of that page; without, one per page),
              with a hint that points at the source and does not state the relation; the reveal is the sentence that evidences it.

No `prompt` or `hint` contains a note's sentence (checked while deriving and again by a test over every kind): what is withheld is
withheld. Pages are taken the learner knows least first, an unrated page counting as `UNRATED`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Literal

from api.genui.text import normalise
from api.learner.mastery import MasteryScore
from api.stores.doc_store import DocStore
from api.vault.types import ConceptPage, Vault
from api.vault.view import CAPS, derive_concept_page

StudyKind = Literal["flashcard", "blurt", "cornell", "socratic"]
STUDY_KINDS: tuple[StudyKind, ...] = ("flashcard", "blurt", "cornell", "socratic")
MAX_ITEMS = 5
"""Items in one set."""
MAX_NOTES = 4
"""Notes under one item (blurting; Cornell shows three)."""
CORNELL_NOTES = 3
UNRATED = 0.5
"""What a page the learner has not rated counts as when pages are ordered (the quiz uses the same)."""
SCAN_PAGES = 40
"""At most this many candidate pages are opened to fill a set: the first in need order that have something citable."""


def _need(page: ConceptPage, mastery: Mapping[str, MasteryScore] | None) -> tuple[float, int, str]:
    held = None if mastery is None else mastery.get(page.id)
    return (held.score if held is not None else UNRATED, -len(page.mention_chunk_ids), page.id)


def _ordered_pages(vault: Vault, focus_id: str | None, mastery: Mapping[str, MasteryScore] | None) -> list[str]:
    if focus_id is not None:
        return [focus_id]
    pages = sorted(vault.pages.values(), key=lambda p: _need(p, mastery))
    return [p.id for p in pages if p.definitions or vault.claims_of(p.id)][:SCAN_PAGES]


def _item_id(kind: str, page_id: str, quote: str) -> str:
    return hashlib.sha1(f"{kind}|{page_id}|{quote}".encode()).hexdigest()[:12]


class _Cites:
    """The set's citations, taken from the pages' own (a page's citation is a verbatim, cited quote), renumbered in first-use order."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self._by_key: dict[tuple[str, str], str] = {}

    def take(self, citation: Mapping[str, Any]) -> str:
        key = (citation["chunkId"], citation["quote"])
        if key not in self._by_key:
            self._by_key[key] = f"c{len(self.items) + 1}"
            self.items.append({**citation, "id": self._by_key[key]})
        return self._by_key[key]


def _quote_of(page_data: Mapping[str, Any], citation_id: str) -> str:
    return next(c["quote"] for c in page_data["citations"] if c["id"] == citation_id)


def _citation_of(page_data: Mapping[str, Any], citation_id: str) -> dict[str, Any]:
    return next(c for c in page_data["citations"] if c["id"] == citation_id)


def _notes(page_data: Mapping[str, Any], order: tuple[str, ...], limit: int) -> list[str]:
    """Citation ids of the page's definitions and claims in the given order of sources, distinct sentences only, at most `limit`."""
    picked: list[str] = []
    seen: set[str] = set()
    for source in order:
        for entry in page_data[source]:
            cid = entry["citationId"]
            quote = normalise(_quote_of(page_data, cid))
            if quote not in seen and len(picked) < limit:
                seen.add(quote)
                picked.append(cid)
    return picked


def _leaks(text: str | None, quotes: list[str]) -> bool:
    """True if `text` holds any whole note sentence (a prompt or hint that states what it withholds)."""
    if not text:
        return False
    flat = normalise(text).lower()
    return any(normalise(q).lower() in flat for q in quotes)


def _socratic_items(data: Mapping[str, Any], label: str, limit: int) -> list[tuple[str, str | None, list[str]]]:
    """One question per asserted link that has a cited sentence, strongest first (the page's links are already in that order)."""
    made: list[tuple[str, str | None, list[str]]] = []
    for link in data["links"]:
        if len(made) >= limit:
            break
        if link["kind"] != "asserted" or not link["relation"]:
            continue
        citation = _citation_of(data, link["citationId"])
        where = f", page {citation['page']}" if citation["page"] is not None else ""
        made.append(
            (
                f"How do {label} and {link['other']['label']} relate? Say it in your own words, then check.",
                f"Look at {citation['docTitle']}{where}.",
                [link["citationId"]],
            )
        )
    return made


def derive_study_set(
    vault: Vault,
    docs: DocStore,
    kind: StudyKind,
    focus_id: str | None = None,
    mastery: Mapping[str, MasteryScore] | None = None,
) -> dict[str, Any] | None:
    """The data of a `StudySet` of this kind, or None if `focus_id` is given and the vault has no such page."""
    if focus_id is not None and focus_id not in vault.pages:
        return None
    cites = _Cites()
    items: list[dict[str, Any]] = []
    summary_citation: dict[str, Any] | None = None
    skipped = 0
    for page_id in _ordered_pages(vault, focus_id, mastery):
        if len(items) >= MAX_ITEMS:
            break
        data = derive_concept_page(vault, docs, page_id, mastery)
        if data is None:
            continue
        label = data["page"]["label"]
        made: list[tuple[str, str | None, list[str]]] = []  # (prompt, hint, the page's own citation ids)
        if kind == "flashcard":
            notes = _notes(data, ("definitions", "claims"), 1)
            if notes:
                made.append((label, None, notes))
        elif kind == "blurt":
            notes = _notes(data, ("definitions", "claims"), MAX_NOTES)
            if notes:
                made.append((f"Write down what you remember about {label}, then check it against your documents.", None, notes))
        elif kind == "cornell":
            notes = _notes(data, ("claims", "definitions"), CORNELL_NOTES)
            if notes:
                made.append((f"What do your documents state about {label}?", None, notes))
        else:  # socratic: with a focus, one item per link of that page; without, one per page
            made = _socratic_items(data, label, MAX_ITEMS if focus_id is not None else 1)
        if not made:
            skipped += 1
            continue
        for prompt, hint, cids in made:
            if len(items) >= MAX_ITEMS:
                break
            quotes = [_quote_of(data, c) for c in cids]
            if _leaks(prompt, quotes) or _leaks(hint, quotes):
                skipped += 1
                continue
            if kind == "cornell" and summary_citation is None:
                first = _notes(data, ("definitions",), 1)
                if first:
                    summary_citation = _citation_of(data, first[0])
            items.append(
                {
                    "id": _item_id(kind, page_id, quotes[0]),
                    "prompt": prompt,
                    "hint": hint,
                    "pageId": page_id,
                    "pageLabel": label,
                    "notes": [{"citationId": cites.take(_citation_of(data, c))} for c in cids],
                }
            )
    summary = {"citationId": cites.take(summary_citation)} if summary_citation is not None and items else None
    return {
        "kind": kind,
        "focusId": focus_id,
        "items": items,
        "summary": summary,
        "citations": cites.items,
        "skipped": skipped,
    }


def study_caps() -> dict[str, int]:
    return {"items": MAX_ITEMS, "notes": MAX_NOTES, "label_chars": CAPS["label_chars"]}
