"""Vault data (M2, D-35): concept pages above graph nodes, asserted and co-mentioned links, and claim notes.

Plain dataclasses, no backend. A page is a list of node ids (nodes are never merged by judgement, so the frozen query resolver,
which reads node ids, is unaffected); every link and definition points at a stored passage.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal

VAULT_VERSION = "vault-1"
"""The construction rules in D-35. Changing any constant or rule is a declared amendment with a new version."""

LinkKind = Literal["asserted", "co_mention"]
MAX_SENTENCE_PAGES = 6
"""A sentence naming more distinct pages than this makes no co-mention links (lists, author lines)."""
MIN_SCAN_LABEL_CHARS = 3
"""A label shorter than this is not searched for across the corpus ("AI" would be found everywhere); the chunks the builder
already named for the node always count."""
NO_CO_MENTION_KINDS = frozenset({"person", "organisation"})
MAX_DEFINITIONS = 8


@dataclass(frozen=True)
class Definition:
    text: str
    """A verbatim sentence of the passage, as the builder stored it."""
    chunk_id: str
    doc_id: str


@dataclass(frozen=True)
class ConceptPage:
    id: str
    """The smallest member node id (stable across rebuilds)."""
    label: str
    aliases: tuple[str, ...]
    node_ids: tuple[str, ...]
    kind: str | None
    doc_ids: tuple[str, ...]
    mention_chunk_ids: tuple[str, ...]
    """Every passage that mentions the page: a member's own chunk list, or a member label found in it by the server."""
    definitions: tuple[Definition, ...]


@dataclass(frozen=True)
class PageLink:
    src: str
    dst: str
    kind: LinkKind
    relation: str | None
    """The relation a model stated (asserted links); None for co-mentions."""
    chunk_ids: tuple[str, ...]
    """Asserted: the passages the relation was extracted from. Co-mention: the passages in which both pages occur in one sentence."""
    evidence: str | None
    """One verbatim sentence: the relation's evidence, or the first sentence where the two pages co-occur."""

    @property
    def strength(self) -> int:
        return len(self.chunk_ids)


@dataclass(frozen=True)
class ClaimDraft:
    """What a builder hands the vault: a claim-worthy sentence of a stored passage and the concept ids it names (node ids)."""

    chunk_id: str
    doc_id: str
    sentence: str
    concept_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClaimNote:
    id: str
    chunk_id: str
    doc_id: str
    sentence: str
    page_ids: tuple[str, ...]


@dataclass
class Vault:
    version: str
    n_chunks: int
    pages: dict[str, ConceptPage]
    links: list[PageLink]
    claims: list[ClaimNote] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    _page_of_node: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _links_of: dict[str, list[PageLink]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        for page in self.pages.values():
            for node_id in page.node_ids:
                self._page_of_node[node_id] = page.id
        for link in self.links:
            self._links_of.setdefault(link.src, []).append(link)
            if link.dst != link.src:
                self._links_of.setdefault(link.dst, []).append(link)

    def page_of_node(self, node_id: str) -> str | None:
        return self._page_of_node.get(node_id)

    def links_of(self, page_id: str) -> list[PageLink]:
        return self._links_of.get(page_id, [])

    def claims_of(self, page_id: str) -> list[ClaimNote]:
        return [c for c in self.claims if page_id in c.page_ids]

    def df(self, page_id: str) -> int:
        return len(self.pages[page_id].mention_chunk_ids)

    def idf(self, page_id: str) -> float:
        """How specific a page is: ln(1 + N / df) / ln(1 + N), 1.0 for a page found in one passage, near 0 for one found
        in every passage. 0.0 for a page no passage mentions."""
        df = self.df(page_id)
        if df == 0 or self.n_chunks == 0:
            return 0.0
        return math.log(1 + self.n_chunks / df) / math.log(1 + self.n_chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "n_chunks": self.n_chunks,
            "pages": [_page_dict(p) for _, p in sorted(self.pages.items())],
            "links": [_link_dict(link) for link in self.links],
            "claims": [_claim_dict(c) for c in self.claims],
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Vault:
        pages = {
            p["id"]: ConceptPage(
                id=p["id"],
                label=p["label"],
                aliases=tuple(p["aliases"]),
                node_ids=tuple(p["node_ids"]),
                kind=p["kind"],
                doc_ids=tuple(p["doc_ids"]),
                mention_chunk_ids=tuple(p["mention_chunk_ids"]),
                definitions=tuple(Definition(**d) for d in p["definitions"]),
            )
            for p in raw["pages"]
        }
        links = [
            PageLink(
                src=link["src"],
                dst=link["dst"],
                kind=link["kind"],
                relation=link["relation"],
                chunk_ids=tuple(link["chunk_ids"]),
                evidence=link["evidence"],
            )
            for link in raw["links"]
        ]
        claims = [
            ClaimNote(c["id"], c["chunk_id"], c["doc_id"], c["sentence"], tuple(c["page_ids"]))
            for c in raw["claims"]
        ]
        return cls(raw["version"], raw["n_chunks"], pages, links, claims, raw.get("stats", {}))

    def sha256(self) -> str:
        body = json.dumps({k: v for k, v in self.to_dict().items() if k != "stats"}, sort_keys=True)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _page_dict(p: ConceptPage) -> dict[str, Any]:
    return {
        "id": p.id,
        "label": p.label,
        "aliases": list(p.aliases),
        "node_ids": list(p.node_ids),
        "kind": p.kind,
        "doc_ids": list(p.doc_ids),
        "mention_chunk_ids": list(p.mention_chunk_ids),
        "definitions": [
            {"text": d.text, "chunk_id": d.chunk_id, "doc_id": d.doc_id} for d in p.definitions
        ],
    }


def _link_dict(link: PageLink) -> dict[str, Any]:
    return {
        "src": link.src,
        "dst": link.dst,
        "kind": link.kind,
        "relation": link.relation,
        "chunk_ids": list(link.chunk_ids),
        "evidence": link.evidence,
    }


def _claim_dict(c: ClaimNote) -> dict[str, Any]:
    return {
        "id": c.id,
        "chunk_id": c.chunk_id,
        "doc_id": c.doc_id,
        "sentence": c.sentence,
        "page_ids": list(c.page_ids),
    }
