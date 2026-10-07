"""What the notes view shows, as pure functions of the vault and the stored passages (M2.6, D-35).

`derive_concept_page` and `derive_notes_graph` return the exact `data` of a `ConceptPage` and a `NotesGraph` block. The
Composer builds the blocks from them and the validator runs them again to check a block: a page is a function of its id, a
graph a function of its focus and query, so a block that says anything else is refused. Nothing here calls a model.

Every sentence shown is a verbatim span of a stored passage and is cited: definitions (the builder's notes), the evidence of an
asserted link, the first sentence where two pages co-occur, claims, and one sentence of each mentioning passage (the
backlinks). A link or mention with no usable sentence (under the quote minimum, or not found in its passage) is not shown and
is counted in `linksLeftOut` / `mentionsLeftOut`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.genui.evidence import QUOTE_CHARS
from api.genui.text import MIN_QUOTE_CHARS, normalise
from api.learner.mastery import MasteryScore
from api.stores.doc_store import Chunk, DocStore
from api.vault.text import fold, occurs, split_sentences
from api.vault.types import ConceptPage, PageLink, Vault

CAPS = {
    "definitions": 8,
    "links": 40,
    "claims": 10,
    "mentions": 10,
    "aliases": 20,
    "nodes": 40,
    "edges": 120,
    "label_chars": 120,
}
"""The notes components' fences. The validator and the Composer read them from here; catalog.md states the same numbers and a
test parses them (D-31)."""


def _clip(sentence: str) -> str:
    return sentence if len(sentence) <= QUOTE_CHARS else sentence[:QUOTE_CHARS].rsplit(" ", 1)[0]


def _usable(sentence: str) -> bool:
    return len(sentence) >= MIN_QUOTE_CHARS


class _Cites:
    """Citations in the order they are first needed, one per (passage, quote)."""

    def __init__(self, docs: DocStore):
        self._docs = docs
        self._by_key: dict[tuple[str, str], str] = {}
        self.items: list[dict[str, Any]] = []
        self._titles: dict[str, str] = {}

    def cite(self, chunk: Chunk, quote: str) -> str:
        key = (chunk.id, quote)
        if key not in self._by_key:
            if chunk.doc_id not in self._titles:
                document = self._docs.get_document(chunk.doc_id)
                self._titles[chunk.doc_id] = document.title if document else ""
            cid = f"c{len(self.items) + 1}"
            self._by_key[key] = cid
            self.items.append(
                {
                    "id": cid,
                    "chunkId": chunk.id,
                    "docId": chunk.doc_id,
                    "docTitle": self._titles[chunk.doc_id],
                    "page": chunk.page,
                    "quote": quote,
                }
            )
        return self._by_key[key]


def _label(label: str) -> str:
    """A name at most `label_chars` long (cut on a word boundary where there is one), so a page with a very long name cannot
    widen a block."""
    cap = CAPS["label_chars"]
    return label if len(label) <= cap else (label[:cap].rsplit(" ", 1)[0] or label[:cap])


def _ref(vault: Vault, page_id: str) -> dict[str, str]:
    return {"id": page_id, "label": _label(vault.pages[page_id].label)}


def _names(page: ConceptPage) -> list[str]:
    return [page.label, *page.aliases]


def _holding(sentences: list[str], keys: list[str]) -> str | None:
    """The first usable sentence that holds any of the folded names."""
    for sentence in sentences:
        if _usable(sentence) and any(occurs(fold(sentence), k) for k in keys):
            return _clip(sentence)
    return None


def _evidence_chunk(link: PageLink, chunks: dict[str, Chunk]) -> tuple[Chunk, str] | None:
    """The passage and quote that evidence a link: the first of its passages whose text holds the stored sentence."""
    if not link.evidence:
        return None
    quote = _clip(normalise(link.evidence))
    if len(quote) < MIN_QUOTE_CHARS:
        return None
    for chunk_id in link.chunk_ids:
        chunk = chunks.get(chunk_id)
        if chunk is not None and quote in normalise(chunk.text):
            return chunk, quote
    return None


def _round_robin(chunks: list[Chunk]) -> list[Chunk]:
    """Passages in turn from each document (documents in id order, passages in reading order), so a page that occurs in several
    papers shows several."""
    by_doc: dict[str, list[Chunk]] = {}
    for chunk in sorted(chunks, key=lambda c: (c.doc_id, c.ordinal)):
        by_doc.setdefault(chunk.doc_id, []).append(chunk)
    ordered: list[Chunk] = []
    queues = [by_doc[d] for d in sorted(by_doc)]
    depth = max((len(q) for q in queues), default=0)
    for i in range(depth):
        ordered += [q[i] for q in queues if i < len(q)]
    return ordered


def derive_concept_page(
    vault: Vault, docs: DocStore, page_id: str, mastery: Mapping[str, MasteryScore] | None = None
) -> dict[str, Any] | None:
    """The data of a `ready` ConceptPage for `page_id`, or None if the vault has no such page. `mastery` is the learner's snapshot
    (D-35 A6): a page it does not hold has none."""
    page = vault.pages.get(page_id)
    if page is None:
        return None
    wanted = set(page.mention_chunk_ids)
    links = vault.links_of(page_id)
    for link in links:
        wanted.update(link.chunk_ids)
    wanted.update(d.chunk_id for d in page.definitions)
    claims = sorted(vault.claims_of(page_id), key=lambda c: (c.doc_id, c.chunk_id, c.sentence))
    wanted.update(c.chunk_id for c in claims)
    stored = docs.get_chunks(sorted(wanted))
    cites = _Cites(docs)

    definitions: list[dict[str, str]] = []
    for definition in page.definitions[: CAPS["definitions"]]:
        chunk = stored.get(definition.chunk_id)
        quote = _clip(normalise(definition.text))
        if chunk is not None and _usable(quote) and quote in normalise(chunk.text):
            definitions.append({"citationId": cites.cite(chunk, quote)})

    ordered_links = sorted(
        links,
        key=lambda x: (
            x.kind != "asserted",
            -x.strength,
            x.relation or "",
            vault.pages[x.dst if x.src == page_id else x.src].label.lower(),
            x.src,
            x.dst,
        ),
    )
    shown_links: list[dict[str, Any]] = []
    for link in ordered_links:
        if len(shown_links) == CAPS["links"]:
            break
        other = link.dst if link.src == page_id else link.src
        if link.kind == "asserted":
            found = _evidence_chunk(link, stored)
        else:
            sentence = _clip(normalise(link.evidence or ""))
            chunk = stored.get(link.chunk_ids[0]) if link.chunk_ids else None
            found = (
                (chunk, sentence)
                if chunk is not None and _usable(sentence) and sentence in normalise(chunk.text)
                else None
            )
        if found is None:
            continue
        chunk, quote = found
        shown_links.append(
            {
                "other": _ref(vault, other),
                "kind": link.kind,
                "relation": link.relation if link.kind == "asserted" else None,
                "direction": ("out" if link.src == page_id else "in")
                if link.kind == "asserted"
                else None,
                "citationId": cites.cite(chunk, quote),
                "passages": link.strength,
            }
        )

    shown_claims: list[dict[str, Any]] = []
    for claim in claims:
        if len(shown_claims) == CAPS["claims"]:
            break
        chunk = stored.get(claim.chunk_id)
        quote = _clip(normalise(claim.sentence))
        if chunk is not None and _usable(quote) and quote in normalise(chunk.text):
            shown_claims.append(
                {
                    "citationId": cites.cite(chunk, quote),
                    "pages": [_ref(vault, p) for p in claim.page_ids],
                }
            )

    mention_stored = [stored[cid] for cid in page.mention_chunk_ids if cid in stored]
    mention_chunks = _round_robin(mention_stored)
    keys = [k for k in (fold(n) for n in _names(page)) if k]
    shown_mentions: list[dict[str, str]] = []
    for chunk in mention_chunks:
        if len(shown_mentions) == CAPS["mentions"]:
            break
        sentence = _holding(split_sentences(chunk.text), keys)
        if sentence is not None:
            shown_mentions.append({"citationId": cites.cite(chunk, sentence)})

    return {
        "page": _ref(vault, page_id),
        "kind": page.kind,
        "aliases": [_label(a) for a in page.aliases[: CAPS["aliases"]]],
        "passages": len(page.mention_chunk_ids),
        "documents": len({c.doc_id for c in mention_stored}),
        "definitions": definitions,
        "links": shown_links,
        "linksLeftOut": len(links) - len(shown_links),
        "claims": shown_claims,
        "mentions": shown_mentions,
        "mentionsLeftOut": len(page.mention_chunk_ids) - len(shown_mentions),
        "citations": cites.items,
        "mastery": _mastery(mastery, page_id),
    }


def _mastery(snapshot: Mapping[str, MasteryScore] | None, page_id: str) -> dict[str, Any] | None:
    held = None if snapshot is None else snapshot.get(page_id)
    return None if held is None else {"score": held.score, "events": held.events}


def _node(
    vault: Vault, docs: DocStore, page_id: str, documents: dict[str, int], mastery: Mapping[str, MasteryScore] | None
) -> dict[str, Any]:
    page = vault.pages[page_id]
    if page_id not in documents:
        documents[page_id] = len(
            {c.doc_id for c in docs.get_chunks(list(page.mention_chunk_ids)).values()}
        )
    return {
        "id": page_id,
        "label": _label(page.label),
        "kind": page.kind,
        "passages": len(page.mention_chunk_ids),
        "documents": documents[page_id],
        "degree": len({x.dst if x.src == page_id else x.src for x in vault.links_of(page_id)}),
        "mastery": None if mastery is None or page_id not in mastery else mastery[page_id].score,
    }


def _matches(page: ConceptPage, key: str) -> bool:
    return not key or any(key in fold(name) for name in _names(page))


def derive_notes_graph(
    vault: Vault,
    docs: DocStore,
    focus_id: str | None,
    query: str,
    mastery: Mapping[str, MasteryScore] | None = None,
) -> dict[str, Any] | None:
    """The data of a NotesGraph: local to `focus_id` (None if the vault has no such page) or the overview narrowed by `query`."""
    key = fold(query.strip())
    if focus_id is not None:
        if focus_id not in vault.pages:
            return None
        neighbours: dict[str, tuple[bool, int]] = {}
        for link in vault.links_of(focus_id):
            other = link.dst if link.src == focus_id else link.src
            asserted, strength = neighbours.get(other, (False, 0))
            neighbours[other] = (asserted or link.kind == "asserted", max(strength, link.strength))
        ranked = sorted(
            neighbours,
            key=lambda p: (
                not neighbours[p][0],
                -neighbours[p][1],
                -len(vault.pages[p].mention_chunk_ids),
                p,
            ),
        )
        chosen = [focus_id, *ranked[: CAPS["nodes"] - 1]]
        left_out = len(ranked) - (len(chosen) - 1)
    else:
        candidates = [p for p in sorted(vault.pages) if _matches(vault.pages[p], key)]
        degree = {
            p: len({x.dst if x.src == p else x.src for x in vault.links_of(p)}) for p in candidates
        }
        ranked = sorted(
            candidates, key=lambda p: (-degree[p], -len(vault.pages[p].mention_chunk_ids), p)
        )
        chosen = ranked[: CAPS["nodes"]]
        left_out = len(candidates) - len(chosen)
    inside = set(chosen)
    documents: dict[str, int] = {}
    edges = [
        {
            "source": link.src,
            "target": link.dst,
            "kind": link.kind,
            "relation": link.relation if link.kind == "asserted" else None,
            "passages": link.strength,
        }
        for link in sorted(
            vault.links,
            key=lambda x: (x.kind != "asserted", -x.strength, x.src, x.dst, x.relation or ""),
        )
        if link.src in inside and link.dst in inside
    ][: CAPS["edges"]]
    return {
        "focusId": focus_id,
        "query": query.strip(),
        "nodes": [_node(vault, docs, p, documents, mastery) for p in chosen],
        "edges": edges,
        "nodesLeftOut": left_out,
    }
