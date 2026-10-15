"""The cheat sheet (D-43, V4): the VERA "Visual" function as a learning tool. A one-page picture of a concept and the concepts around it:
each with the one stored sentence that defines (or, failing that, states) it, and the links between them.

`derive_cheat_sheet` returns the exact `data` of a `CheatSheet` block, and the validator runs it again to check one. No model, no spend,
no image generation: the "visual" is a small diagram the web draws from the same entries and edges, with the entries listed beside it as
the text alternative. Every sentence is a verbatim, cited span of a stored passage.

    focus      the page the request names, else the best connected page that has a citable sentence
    entries    the focus first, then the pages linked to it, strongest link first, each with its first definition or claim;
               a neighbour with no citable sentence is passed over (and counted); at most `MAX_ENTRIES`
    edges      the links between the entries (an asserted relation is preferred over a co-mention), at most `MAX_EDGES`
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.learner.mastery import MasteryScore
from api.stores.doc_store import DocStore
from api.vault.types import Vault
from api.vault.view import CAPS, derive_concept_page

MAX_ENTRIES = 8
MAX_EDGES = 16
SCAN_PAGES = 40


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


def _sentence(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """A page's first stored definition, else its first claim, as a citation; None when it has neither."""
    by_id = {c["id"]: c for c in data["citations"]}
    for source in ("definitions", "claims"):
        for entry in data[source]:
            return by_id[entry["citationId"]]
    return None


def default_focus(vault: Vault) -> str | None:
    """The best connected page (most links, then id) that holds a definition or a claim: what a sheet covers when none is named."""
    ranked = sorted(vault.pages, key=lambda p: (-len(vault.links_of(p)), p))
    for page_id in ranked[:SCAN_PAGES]:
        if vault.pages[page_id].definitions or vault.claims_of(page_id):
            return page_id
    return None


def derive_cheat_sheet(
    vault: Vault, docs: DocStore, focus_id: str | None, mastery: Mapping[str, MasteryScore] | None = None
) -> dict[str, Any] | None:
    """The data of a `CheatSheet` for this page, or None if `focus_id` names no page of the vault."""
    if focus_id is None or focus_id not in vault.pages:
        return None
    cites = _Cites()
    entries: list[dict[str, Any]] = []
    skipped = 0
    head = derive_concept_page(vault, docs, focus_id, mastery)
    assert head is not None
    candidates = [focus_id]
    for link in head["links"]:
        other = link["other"]["id"]
        if other not in candidates:
            candidates.append(other)
    for page_id in candidates:
        if len(entries) >= MAX_ENTRIES:
            break
        data = head if page_id == focus_id else derive_concept_page(vault, docs, page_id, mastery)
        citation = _sentence(data) if data is not None else None
        if data is None or citation is None:
            skipped += 1
            continue
        entries.append(
            {
                "pageId": page_id,
                "pageLabel": data["page"]["label"],
                "kind": data["kind"],
                "citationId": cites.take(citation),
            }
        )
    shown = {e["pageId"] for e in entries}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for link in vault.links:
        if link.src not in shown or link.dst not in shown or link.src == link.dst:
            continue
        pair = (min(link.src, link.dst), max(link.src, link.dst))
        edge = {"src": pair[0], "dst": pair[1], "relation": link.relation if link.kind == "asserted" else None}
        if pair not in edges or (edges[pair]["relation"] is None and edge["relation"] is not None):
            edges[pair] = edge
    ordered = [edges[k] for k in sorted(edges)][:MAX_EDGES]
    return {
        "focusId": focus_id,
        "entries": entries,
        "edges": ordered,
        "citations": cites.items,
        "skipped": skipped,
    }


def sheet_caps() -> dict[str, int]:
    return {"entries": MAX_ENTRIES, "edges": MAX_EDGES, "citations": MAX_ENTRIES, "label_chars": CAPS["label_chars"]}
