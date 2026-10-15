"""The document brief (D-43, V3): the VERA "Meetings" function as a learning tool. Instead of a transcript, a stored document; instead of
an executive brief with action items, its key points, its key terms and what the learner could do next.

`derive_doc_brief` returns the exact `data` of a `DocBrief` block, and the validator runs it again to check one (as for the study set and
the quiz). No model, no spend: every sentence shown is a verbatim, cited span of a stored passage of THIS document (a claim or a
definition the vault holds), so a brief is only as good as the vault and says so.

    key points   the document's claims, the ones that name the most concepts first, then by passage; at most `MAX_POINTS`
    key terms    concept pages the document defines: each page's first stored definition from this document; at most `MAX_TERMS`
    next steps   from the learner's mastery of the pages above: a page rated under `REVIEW_BELOW` is "review", one never rated is
                 "learn"; and one "quiz" on the first of them; at most `MAX_ACTIONS`, each with the fixed reason it is there
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.genui.text import normalise
from api.learner.mastery import MasteryScore
from api.stores.doc_store import DocStore
from api.vault.types import Vault
from api.vault.view import CAPS, derive_concept_page

MAX_POINTS = 6
MAX_TERMS = 6
MAX_ACTIONS = 4
SCAN_PAGES = 40
"""At most this many of the document's pages are opened, the most mentioned first."""
REVIEW_BELOW = 0.5
"""A rated page under this is one to review; the schedule's "due now" threshold, so the two tools agree."""


class _Cites:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self._by_key: dict[tuple[str, str], str] = {}

    def take(self, citation: Mapping[str, Any]) -> str:
        key = (citation["chunkId"], citation["quote"])
        if key not in self._by_key:
            self._by_key[key] = f"c{len(self.items) + 1}"
            self.items.append({**citation, "id": self._by_key[key]})
        return self._by_key[key]


def default_doc_id(vault: Vault) -> str | None:
    """The document with the most claims in the vault (ties by id): what a brief covers when the request names none."""
    counts: dict[str, int] = {}
    for claim in vault.claims:
        counts[claim.doc_id] = counts.get(claim.doc_id, 0) + 1
    if not counts:
        return None
    return sorted(counts, key=lambda d: (-counts[d], d))[0]


def _cited(page_data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in page_data["citations"]}


def derive_doc_brief(
    vault: Vault, docs: DocStore, doc_id: str, mastery: Mapping[str, MasteryScore] | None = None
) -> dict[str, Any] | None:
    """The data of a `DocBrief` for this document, or None if the store holds no such document."""
    document = docs.get_document(doc_id)
    if document is None:
        return None
    # the document's pages: those it names in a claim, those it defines, and those the vault lists it under
    named = {p for c in vault.claims if c.doc_id == doc_id for p in c.page_ids}
    named |= {p.id for p in vault.pages.values() if any(d.doc_id == doc_id for d in p.definitions) or doc_id in p.doc_ids}
    pages = sorted((vault.pages[p] for p in named if p in vault.pages), key=lambda p: (-len(p.mention_chunk_ids), p.id))[:SCAN_PAGES]
    points: dict[str, tuple[int, dict[str, Any], list[str]]] = {}  # normalised quote -> (concepts named, citation, labels)
    terms: list[tuple[str, str, dict[str, Any]]] = []
    seen_terms: set[str] = set()
    for page in pages:
        data = derive_concept_page(vault, docs, page.id, mastery)
        if data is None:
            continue
        by_id = _cited(data)
        for entry in data["claims"]:
            citation = by_id[entry["citationId"]]
            if citation["docId"] != doc_id:
                continue
            key = normalise(citation["quote"]).lower()
            labels = [p["label"] for p in entry["pages"]]
            if key not in points or len(labels) > points[key][0]:
                points[key] = (len(labels), citation, labels)
        for entry in data["definitions"]:
            citation = by_id[entry["citationId"]]
            key = normalise(citation["quote"]).lower()
            if citation["docId"] == doc_id and key not in seen_terms:
                seen_terms.add(key)
                terms.append((page.id, data["page"]["label"], citation))
                break
    ordered_points = sorted(points.values(), key=lambda p: (-p[0], p[1]["chunkId"], p[1]["quote"]))
    cites = _Cites()
    key_points = [
        {"citationId": cites.take(citation), "pageLabels": labels}
        for _, citation, labels in ordered_points[:MAX_POINTS]
    ]
    key_terms = [
        {"pageId": page_id, "pageLabel": label, "citationId": cites.take(citation)}
        for page_id, label, citation in terms[:MAX_TERMS]
    ]
    return {
        "docId": doc_id,
        "docTitle": document.title,
        "keyPoints": key_points,
        "terms": key_terms,
        "actions": _actions(vault, mastery, [t[0] for t in terms[:MAX_TERMS]]),
        "citations": cites.items,
        "claimsInDocument": sum(1 for c in vault.claims if c.doc_id == doc_id),
        "leftOut": max(0, len(ordered_points) - MAX_POINTS),
    }


def _actions(vault: Vault, mastery: Mapping[str, MasteryScore] | None, page_ids: list[str]) -> list[dict[str, Any]]:
    """The next steps over the pages the brief names: weakest rated first, then the unrated, each with its fixed reason."""
    rated = [(mastery[p].score, p) for p in page_ids if mastery is not None and p in mastery]
    unrated = [p for p in page_ids if mastery is None or p not in mastery]
    actions: list[dict[str, Any]] = []
    for score, page_id in sorted(rated):
        if score < REVIEW_BELOW:
            actions.append(
                {
                    "kind": "review",
                    "pageId": page_id,
                    "pageLabel": _label(vault, page_id),
                    "reason": f"Your mastery is {round(score * 100)} percent: revisit it.",
                }
            )
    for page_id in unrated:
        actions.append(
            {
                "kind": "learn",
                "pageId": page_id,
                "pageLabel": _label(vault, page_id),
                "reason": "You have not rated it yet: start with its definition.",
            }
        )
    actions = actions[: MAX_ACTIONS - 1]
    if page_ids:
        actions.append(
            {
                "kind": "quiz",
                "pageId": page_ids[0],
                "pageLabel": _label(vault, page_ids[0]),
                "reason": "Test yourself: ask for a quiz on it.",
            }
        )
    return actions


def _label(vault: Vault, page_id: str) -> str:
    label = vault.pages[page_id].label
    cap = CAPS["label_chars"]
    return label if len(label) <= cap else (label[:cap].rsplit(" ", 1)[0] or label[:cap])


def brief_caps() -> dict[str, int]:
    return {
        "key_points": MAX_POINTS,
        "terms": MAX_TERMS,
        "actions": MAX_ACTIONS,
        "citations": MAX_POINTS + MAX_TERMS,
        "label_chars": CAPS["label_chars"],
    }
