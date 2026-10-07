"""Lint the vault (M2.8, D-35): what a person should look at, reported and never fixed.

Deterministic, no model. Nothing here changes the vault, merges pages or judges whether two definitions disagree.

    orphans      pages that no link of either kind reaches (and that at least one passage mentions)
    duplicates   pairs of pages whose names suggest one concept, awaiting a person's review:
                   same_name        the same words after folding plurals and hyphens
                   one_more_word    one name is the other plus exactly one word ("language models", "large language models")
                   initials         one name is the initials of the other ("LLM", "large language models")
    tensions     a concept that two or more papers define: the definitions are listed with their papers, not compared
    hubs         pages that a quarter or more of all passages mention (the spread discount's reason for being)

Each list is capped for display; the totals are exact.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.stores.doc_store import DocStore
from api.vault.text import fold, tokens
from api.vault.types import ConceptPage, Vault

DISPLAY_CAP = 50
HUB_SHARE = 0.25
MAX_TENSION_DEFINITIONS = 4
MIN_INITIALS = 2
MAX_INITIALS = 8
MAX_POSTING = 300
"""A word held by more pages than this is too common to pair pages by."""


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _words(label: str) -> tuple[str, ...]:
    return tuple(_singular(t) for t in tokens(fold(label)))


def _ref(page: ConceptPage) -> dict[str, Any]:
    return {"id": page.id, "label": page.label, "passages": len(page.mention_chunk_ids)}


def _initials(words: tuple[str, ...]) -> str:
    return "".join(w[0] for w in words)


def orphans(vault: Vault) -> list[ConceptPage]:
    return sorted(
        (p for p in vault.pages.values() if p.mention_chunk_ids and not vault.links_of(p.id)),
        key=lambda p: (-len(p.mention_chunk_ids), p.id),
    )


def hubs(vault: Vault) -> list[ConceptPage]:
    if not vault.n_chunks:
        return []
    return sorted(
        (p for p in vault.pages.values() if len(p.mention_chunk_ids) / vault.n_chunks >= HUB_SHARE),
        key=lambda p: (-len(p.mention_chunk_ids), p.id),
    )


def duplicates(vault: Vault) -> list[tuple[ConceptPage, ConceptPage, str]]:
    """Pairs of distinct pages whose names suggest one concept. Each pair once (the smaller id first), its first matching reason."""
    words = {pid: _words(p.label) for pid, p in vault.pages.items()}
    by_word: dict[str, list[str]] = defaultdict(list)
    by_initials: dict[str, list[str]] = defaultdict(list)
    for pid, w in sorted(words.items()):
        for token in set(w):
            by_word[token].append(pid)
        if len(w) >= MIN_INITIALS:
            by_initials[_initials(w)].append(pid)
    found: dict[tuple[str, str], str] = {}

    def add(a: str, b: str, reason: str) -> None:
        pair = (a, b) if a < b else (b, a)
        found.setdefault(pair, reason)

    for pid, w in sorted(words.items()):
        if not w:
            continue
        rarest = min(set(w), key=lambda t: (len(by_word[t]), t))
        if len(by_word[rarest]) <= MAX_POSTING:
            for other in by_word[rarest]:
                if other == pid or not words[other]:
                    continue
                a, b = w, words[other]
                if a == b:
                    add(pid, other, "same_name")
                elif len(a) >= MIN_INITIALS and set(a) < set(b) and len(b) == len(a) + 1:
                    add(pid, other, "one_more_word")
        label = vault.pages[pid].label.strip()
        if (
            MIN_INITIALS <= len(label) <= MAX_INITIALS
            and label.replace("-", "").isalpha()
            and label.isupper()
        ):
            for other in by_initials.get(label.lower().replace("-", ""), []):
                if other != pid:
                    add(pid, other, "initials")
    return [(vault.pages[a], vault.pages[b], reason) for (a, b), reason in sorted(found.items())]


def tensions(vault: Vault, docs: DocStore) -> list[tuple[ConceptPage, list[dict[str, str]]]]:
    """Concepts that two or more papers define, with one definition per paper and the paper's title. Not compared or judged."""
    titles: dict[str, str] = {}
    out: list[tuple[ConceptPage, list[dict[str, str]]]] = []
    for page in vault.pages.values():
        per_doc: dict[str, str] = {}
        for definition in page.definitions:
            per_doc.setdefault(definition.doc_id, definition.text)
        if len(per_doc) < 2:
            continue
        shown = []
        for doc_id in sorted(per_doc)[:MAX_TENSION_DEFINITIONS]:
            if doc_id not in titles:
                document = docs.get_document(doc_id)
                titles[doc_id] = document.title if document else doc_id
            shown.append({"docTitle": titles[doc_id], "text": per_doc[doc_id]})
        out.append((page, shown))
    return sorted(out, key=lambda t: (-len(t[1]), -len(t[0].mention_chunk_ids), t[0].id))


def lint(vault: Vault, docs: DocStore) -> dict[str, Any]:
    """The whole report as plain data (the shape of `VaultLintResponse`)."""
    orphan = orphans(vault)
    duplicate = duplicates(vault)
    tension = tensions(vault, docs)
    hub = hubs(vault)
    duplicate.sort(
        key=lambda t: (
            -(len(t[0].mention_chunk_ids) + len(t[1].mention_chunk_ids)),
            t[0].id,
            t[1].id,
        )
    )
    return {
        "pages": len(vault.pages),
        "orphans": [_ref(p) for p in orphan[:DISPLAY_CAP]],
        "orphansTotal": len(orphan),
        "duplicates": [
            {"a": _ref(a), "b": _ref(b), "reason": reason}
            for a, b, reason in duplicate[:DISPLAY_CAP]
        ],
        "duplicatesTotal": len(duplicate),
        "tensions": [{"page": _ref(p), "definitions": d} for p, d in tension[:DISPLAY_CAP]],
        "tensionsTotal": len(tension),
        "hubs": [_ref(p) for p in hub[:DISPLAY_CAP]],
    }
