"""A quiz from the vault's claims (Q1, D-35 amendment A8): pure functions of the vault, the stored passages and the learner's mastery.

A claim is a sentence of a stored passage that names concepts. An item blanks one concept name in it and offers four pages to
choose from. `derive_quiz` returns the exact `data` of a `QuizCard` block; the Composer builds the block from it and the
validator runs it again to check a block. `derive_item` and `check_answer` read one item back from its id alone, so the block
need not carry the answer and an answer cannot be forged: the right page is derived, never sent. Nothing here calls a model.

The sentence shown is the claim's quote (clipped as every quote is), the blank replaces the first whole-word, case-insensitive,
literal occurrence of the longest name of the target page that occurs in it. A name that a PDF broke with a hyphen makes no
item. The options (the target and three distractors) and their order depend on the item id and the vault only, not on the
learner, so an item reads the same whenever it is asked for.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from api.genui.text import MIN_QUOTE_CHARS, normalise
from api.learner.mastery import MasteryScore
from api.stores.doc_store import Chunk, DocStore
from api.vault.text import fold, occurs
from api.vault.types import MIN_SCAN_LABEL_CHARS, ClaimNote, ConceptPage, Vault
from api.vault.view import _clip, _ref

BLANK = "_____"
MAX_ITEMS = 5
"""Items in one quiz (A8)."""
OPTION_COUNT = 4
MIN_BLANK_WORDS = 4
"""The blanked sentence has at least this many words (the blank counts as one)."""
UNRATED = 0.5
"""What a page the learner has not rated counts as when claims are ordered: between "needs work" and "comfortable"."""
MIN_DISTRACTOR_PASSAGES = 2
"""A page offered as a wrong answer is mentioned in at least this many passages: a name that occurs once is a one-off (an example
in a paper), which makes an item trivial."""
MAX_DISTRACTOR_WORDS = 6
"""...and its name has at most this many words and no ":" or "?": a longer name is a paper's title (a reference-list entry made a
page), not a concept."""
MIN_NAME_CHARS = 2
"""A name of the blanked page that is blanked, and that must not be left standing, is at least this long: "QA" beside "question
answering" would give the answer away, though the vault does not search a whole corpus for a name this short."""
SEPARATOR = "~"


@dataclass(frozen=True)
class Item:
    """One question as the server holds it: the shown parts and the answer."""

    id: str
    text: str
    options: tuple[str, ...]
    """Page ids in the order shown."""
    target: str
    chunk: Chunk
    quote: str
    """The sentence, unblanked."""


@dataclass(frozen=True)
class Checked:
    item: Item
    correct: bool


def _names(page: ConceptPage) -> list[str]:
    """The names a blank may use, longest first (so "large language models" is blanked rather than "language models")."""
    names = {n for n in [page.label, *page.aliases] if len(n.strip()) >= MIN_NAME_CHARS}
    return sorted(names, key=lambda n: (-len(n), n))


def _blank(quote: str, page: ConceptPage) -> str | None:
    """`quote` with every whole-word, case-insensitive, literal occurrence of every name of `page` replaced by the blank (the
    longest name first, so "large language models" is blanked as one), or None when no blank can be made fairly: no name occurs
    literally, the sentence already holds a blank, a name still occurs after blanking (one a PDF broke with a hyphen, say: the
    answer would show), or fewer than `MIN_BLANK_WORDS` words are left."""
    names = _names(page)
    if not names or BLANK in quote:
        return None
    pattern = "|".join(re.escape(n) for n in names)
    text, count = re.subn(
        rf"(?<![A-Za-z0-9])(?:{pattern})(?![A-Za-z0-9])", BLANK, quote, flags=re.IGNORECASE
    )
    if count == 0:
        return None
    folded = fold(text)
    if any(occurs(folded, k) for k in (fold(n) for n in names) if k):
        return None
    return text if len(text.split()) >= MIN_BLANK_WORDS else None


def _quote(claim: ClaimNote) -> str:
    return _clip(normalise(claim.sentence))


def _score(mastery: Mapping[str, MasteryScore] | None, page_id: str) -> float:
    held = None if mastery is None else mastery.get(page_id)
    return UNRATED if held is None else held.score


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


_WORD = re.compile(r"[a-z0-9]+")


def _words(name: str) -> set[str]:
    """The words of a name, a hyphen being a space: "Retrieval-Augmented Generation" and "retrieval augmented generation" are the
    same words (unlike `fold`, which joins a hyphenated word, as a PDF breaks one)."""
    return set(_WORD.findall(name.lower()))


def _title_like(label: str) -> bool:
    return len(label.split()) > MAX_DISTRACTOR_WORDS or ":" in label or "?" in label


def _distractors(vault: Vault, target: ConceptPage, quote: str, item_id: str) -> list[str]:
    """Three pages that are fair wrong answers: not the target, of its kind when it has one, mentioned in at least two passages, with a
    name that is not a paper's title, neither in the sentence nor made of the same words as the target's (so "language models" is
    never offered for "large language models"), chosen in the order of a hash of the item and the page."""
    folded = fold(quote)
    target_words = [_words(n) for n in [target.label, *target.aliases]]
    pool = [
        p
        for p in vault.pages.values()
        if p.id != target.id
        and len(p.mention_chunk_ids) >= MIN_DISTRACTOR_PASSAGES
        and len(p.label.strip()) >= MIN_SCAN_LABEL_CHARS
        and not _title_like(p.label)
        and (target.kind is None or p.kind == target.kind)
    ]
    chosen: list[str] = []
    labels = {fold(target.label)}
    for page in sorted(pool, key=lambda p: _hash(item_id, p.id)):
        words = _words(page.label)
        key = fold(page.label)
        if not words or key in labels:
            continue
        if any(words <= other or other <= words for other in target_words if other):
            continue
        if any(occurs(folded, k) for k in (fold(n) for n in [page.label, *page.aliases]) if k):
            continue
        labels.add(key)
        chosen.append(page.id)
        if len(chosen) == OPTION_COUNT - 1:
            break
    return chosen


def _build(vault: Vault, claim: ClaimNote, target_id: str, chunk: Chunk | None) -> Item | None:
    """The item for `claim` blanking `target_id`, or None when one cannot be made fairly."""
    target = vault.pages.get(target_id)
    if (
        target is None
        or target_id not in claim.page_ids
        or chunk is None
        or chunk.id != claim.chunk_id
    ):
        return None
    quote = _quote(claim)
    if len(quote) < MIN_QUOTE_CHARS or quote not in normalise(chunk.text):
        return None
    text = _blank(quote, target)
    if text is None:
        return None
    item_id = f"{claim.id}{SEPARATOR}{target_id}"
    others = _distractors(vault, target, quote, item_id)
    if len(others) < OPTION_COUNT - 1:
        return None
    options = sorted([target_id, *others], key=lambda p: _hash(item_id, "order", p))
    return Item(item_id, text, tuple(options), target_id, chunk, quote)


def derive_item(vault: Vault, docs: DocStore, item_id: str) -> Item | None:
    """The item an id names, or None if its claim or page is gone or the item can no longer be made."""
    claim_id, separator, target_id = item_id.partition(SEPARATOR)
    if not separator or not claim_id or not target_id:
        return None
    claim = next((c for c in vault.claims if c.id == claim_id), None)
    if claim is None:
        return None
    return _build(vault, claim, target_id, docs.get_chunks([claim.chunk_id]).get(claim.chunk_id))


def check_answer(vault: Vault, docs: DocStore, item_id: str, chosen_id: str) -> Checked | None:
    """Whether `chosen_id` is the blanked page of the item, or None for an item that cannot be derived or a page that is not one
    of its four options (a forged request)."""
    item = derive_item(vault, docs, item_id)
    if item is None or chosen_id not in item.options:
        return None
    return Checked(item, chosen_id == item.target)


def source_citation(docs: DocStore, item: Item) -> dict[str, Any]:
    """The sentence of an item, unblanked, as a citation (id `c1`)."""
    document = docs.get_document(item.chunk.doc_id)
    return {
        "id": "c1",
        "chunkId": item.chunk.id,
        "docId": item.chunk.doc_id,
        "docTitle": document.title if document else "",
        "page": item.chunk.page,
        "quote": item.quote,
    }


def _eligible(vault: Vault, claim: ClaimNote) -> list[str]:
    """The pages of `claim` a blank can be made for: those whose name occurs in the sentence, with a blanked text that is long
    enough."""
    quote = _quote(claim)
    if len(quote) < MIN_QUOTE_CHARS:
        return []
    return [
        p for p in claim.page_ids if p in vault.pages and _blank(quote, vault.pages[p]) is not None
    ]


def _target_of(
    vault: Vault, claim: ClaimNote, mastery: Mapping[str, MasteryScore] | None
) -> str | None:
    """The page of `claim` a blank is made for: of the eligible pages, the learner's weakest (an unrated page counts 0.5), then
    the more specific, then the smaller id."""
    eligible = _eligible(vault, claim)
    if not eligible:
        return None
    return min(eligible, key=lambda p: (_score(mastery, p), -vault.idf(p), p))


def _shown_title(vault: Vault, docs: DocStore, item: Item) -> str:
    """The document's title, or "" when it holds a name of the blanked page (a title that is a file name such as
    `2312.10997_Retrieval_Augmented_Generation_...` would give the answer away; the source after answering shows it)."""
    document = docs.get_document(item.chunk.doc_id)
    title = document.title if document else ""
    words = _words(title)
    if any(w and w <= words for w in (_words(n) for n in _names(vault.pages[item.target]))):
        return ""
    return title


def _data(item: Item, vault: Vault, docs: DocStore) -> dict[str, Any]:
    return {
        "id": item.id,
        "text": item.text,
        "options": [_ref(vault, p) for p in item.options],
        "docTitle": _shown_title(vault, docs, item),
        "page": item.chunk.page,
    }


def derive_quiz(
    vault: Vault,
    docs: DocStore,
    focus_id: str | None,
    mastery: Mapping[str, MasteryScore] | None = None,
) -> dict[str, Any] | None:
    """The data of a `QuizCard`, or None if `focus_id` names no page of the vault.

    With a focus, the claims that name that page, in claim id order, blanking that page (at most 5 items, so one page can fill
    the quiz). Without one, claims in the order of the learner's mastery of the page each would blank, weakest first, then claim
    id, at most one item per page. `skipped` counts the claims that were passed over: those with no sentence a name can be
    blanked in, and those looked at before the items were found whose item could not be made fairly (fewer than three distractors,
    or the passage no longer holds the sentence)."""
    if focus_id is not None and focus_id not in vault.pages:
        return None
    candidates: list[tuple[ClaimNote, str]] = []
    skipped = 0
    for claim in vault.claims:
        if focus_id is not None:
            if focus_id not in claim.page_ids:
                continue
            target = focus_id if focus_id in _eligible(vault, claim) else None
        else:
            target = _target_of(vault, claim, mastery)
        if target is None:
            skipped += 1
        else:
            candidates.append((claim, target))
    if focus_id is not None:
        candidates.sort(key=lambda c: c[0].id)
    else:
        candidates.sort(key=lambda c: (_score(mastery, c[1]), c[0].id))
    chunks = docs.get_chunks(sorted({c.chunk_id for c, _ in candidates}))
    items: list[Item] = []
    used: set[str] = set()
    for claim, target in candidates:
        if len(items) == MAX_ITEMS:
            break
        if focus_id is None and target in used:
            continue
        item = _build(vault, claim, target, chunks.get(claim.chunk_id))
        if item is None:
            skipped += 1
            continue
        used.add(target)
        items.append(item)
    return {
        "focusId": focus_id,
        "items": [_data(i, vault, docs) for i in items],
        "skipped": skipped,
    }
