"""Vault retrieval, `vault-1` (M2, D-35): resolve the question to concept pages, then rank the passages that evidence them.

An ADDITIVE arm. The frozen graph retriever (`graph.py`, D-20) and its constants are not touched; the frozen resolver is reused
as it is, over the member node ids of every page, so an alias that the vault groups into one page resolves to that page.

For each resolved page (weight 1.0 exact, 0.6 approximate, 0.5 semantic) with `spread = idf(page)` (1.0 when the spread
discount is off):
  - passages that mention the page, or that hold evidence for an ASSERTED link touching it:   w * spread
  - passages that mention an asserted neighbour page (and are not already scored here):       0.5  * w * spread(neighbour)
  - passages that mention a co-mention neighbour page (and are in neither set above):         0.25 * w * spread(neighbour)
  - passages that hold a CLAIM naming the page (A2, below), added on top of the above:        0.25 * w * spread
Scores add across pages. A passage reached through several neighbours takes the best (largest spread) neighbour's value once.
Ties are broken by asserted-link support, then document id, then position, as in the frozen retriever; scores are rounded
to 12 places first. Neither dense nor sparse scores are used.

Semantic resolution (the `vault_sem` arms): when the lexical step recognised fewer than half of the question's content words,
the 2 pages whose label embedding is nearest (cosine) to the question embedding are added at weight 0.5. Rank-based, with no
similarity threshold, so there is no number to tune on the questions.

D-35 amendment A2 (a clarification made before any retrieval run, no constant changed): (a) a passage reached through several
neighbours takes the best neighbour's value once, as above; (b) claims add `0.25 * w * spread` per resolved page whose claim
the passage holds, and are used only when the vault has claims and the claims toggle is on.

FROZEN with the protocol: the weights above and VAULT_SCORING_VERSION. Changing any is a declared amendment and a new version.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Literal

from api.core.logging import get_logger
from api.ingestion.embed import Embedder
from api.retrieval.entities import resolve_query_entities
from api.retrieval.types import (
    TOP_K,
    ResolutionReport,
    ResolvedEntity,
    RetrievedChunk,
    RetrieverResult,
)
from api.stores.doc_store import DocStore
from api.stores.graph_store import Node
from api.vault.types import Vault

log = get_logger(__name__)

VAULT_SCORING_VERSION = "vault-1"
DIRECT_WEIGHT = 1.0
ASSERTED_NEIGHBOUR_WEIGHT = 0.5
CO_MENTION_NEIGHBOUR_WEIGHT = 0.25
CLAIM_WEIGHT = 0.25
SEMANTIC_WEIGHT = 0.5
SEMANTIC_PAGES = 2
SEMANTIC_BELOW_HIT_RATE = 0.5

Match = Literal["exact", "approximate"]
Resolved = dict[str, tuple[Match, float, tuple[str, ...]]]


class VaultRetriever:
    def __init__(
        self,
        *,
        vault: Vault,
        docs: DocStore,
        embedder: Embedder | None = None,
        label_vectors: dict[str, list[float]] | None = None,
        semantic: bool = False,
        co_mentions: bool = True,
        spread: bool = True,
        claims: bool = True,
    ):
        if semantic and (embedder is None or not label_vectors):
            raise ValueError("semantic resolution needs an embedder and the page-label vectors")
        self._vault = vault
        self._docs = docs
        self._embedder = embedder
        self._label_vectors = label_vectors or {}
        self._semantic = semantic
        self._co_mentions = co_mentions
        self._spread = spread
        self._claims = claims
        self._mentions = {pid: frozenset(p.mention_chunk_ids) for pid, p in vault.pages.items()}
        # One pseudo node per member node id: the frozen resolver reads ids, so any member's id resolves to its page.
        self._pseudo = [
            Node(id=node_id, label=page.label, doc_ids=page.doc_ids)
            for page in vault.pages.values()
            for node_id in page.node_ids
        ]
        self._claim_chunks: dict[str, frozenset[str]] = {}
        for claim in vault.claims:
            for pid in claim.page_ids:
                self._claim_chunks[pid] = self._claim_chunks.get(pid, frozenset()) | {
                    claim.chunk_id
                }

    def _weight(self, page_id: str) -> float:
        return self._vault.idf(page_id) if self._spread else 1.0

    async def retrieve(self, query: str, top_k: int = TOP_K) -> RetrieverResult:
        report = resolve_query_entities(query, self._pseudo)
        resolved = self._to_pages(report)
        if self._semantic and report.hit_rate < SEMANTIC_BELOW_HIT_RATE and query.strip():
            resolved = await self._add_semantic(query, resolved)
        entities = tuple(
            ResolvedEntity(pid, match, w, tokens) for pid, (match, w, tokens) in resolved.items()
        )
        shown = ResolutionReport(
            report.content_tokens, report.covered_tokens, entities, report.exact_covered_tokens
        )
        if not resolved:
            log.warning(
                "vault_resolved_nothing",
                content_tokens=report.content_tokens,
                pages=len(self._vault.pages),
            )
            return RetrieverResult([], shown)

        scores: dict[str, float] = {}
        support: dict[str, int] = {}
        for pid, (_, w, _) in resolved.items():
            spread = self._weight(pid)
            asserted = [link for link in self._vault.links_of(pid) if link.kind == "asserted"]
            for link in asserted:
                for chunk_id in link.chunk_ids:
                    support[chunk_id] = support.get(chunk_id, 0) + 1
            direct = set(self._mentions[pid]) | {c for link in asserted for c in link.chunk_ids}
            for chunk_id in direct:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + w * DIRECT_WEIGHT * spread

            reached: dict[str, float] = {}
            for link in asserted:
                other = link.dst if link.src == pid else link.src
                value = ASSERTED_NEIGHBOUR_WEIGHT * w * self._weight(other)
                for chunk_id in self._mentions[other] - direct:
                    reached[chunk_id] = max(reached.get(chunk_id, 0.0), value)
            if self._co_mentions:
                via_co: dict[str, float] = {}
                for link in self._vault.links_of(pid):
                    if link.kind != "co_mention":
                        continue
                    other = link.dst if link.src == pid else link.src
                    value = CO_MENTION_NEIGHBOUR_WEIGHT * w * self._weight(other)
                    for chunk_id in self._mentions[other] - direct:
                        if chunk_id not in reached:
                            via_co[chunk_id] = max(via_co.get(chunk_id, 0.0), value)
                reached.update(via_co)
            for chunk_id, value in reached.items():
                scores[chunk_id] = scores.get(chunk_id, 0.0) + value
            if self._claims:
                for chunk_id in self._claim_chunks.get(pid, ()):
                    scores[chunk_id] = scores.get(chunk_id, 0.0) + CLAIM_WEIGHT * w * spread

        stored = self._docs.get_chunks(list(scores))
        for chunk_id in scores.keys() - stored.keys():
            log.warning("vault_hit_without_chunk", chunk_id=chunk_id)
        ranked = sorted(
            stored,
            key=lambda cid: (
                -round(scores[cid], 12),
                -support.get(cid, 0),
                stored[cid].doc_id,
                stored[cid].ordinal,
            ),
        )
        chunks = [
            RetrievedChunk(
                stored[c].id,
                stored[c].doc_id,
                stored[c].text,
                stored[c].page,
                scores[c],
                ("graph",),
            )
            for c in ranked[:top_k]
        ]
        return RetrieverResult(chunks, shown)

    def _to_pages(self, report: ResolutionReport) -> Resolved:
        """Resolved node ids to pages: one entry per page, keeping the strongest match and every word it accounts for."""
        out: Resolved = {}
        for entity in report.entities:
            pid = self._vault.page_of_node(entity.node_id)
            if pid is None:
                continue
            previous = out.get(pid)
            if previous is None:
                out[pid] = (entity.match, entity.weight, entity.query_tokens)
            else:
                best = (
                    previous
                    if previous[1] >= entity.weight
                    else (entity.match, entity.weight, previous[2])
                )
                out[pid] = (
                    best[0],
                    best[1],
                    tuple(dict.fromkeys(previous[2] + entity.query_tokens)),
                )
        return out

    async def _add_semantic(self, query: str, resolved: Resolved) -> Resolved:
        assert self._embedder is not None
        (q,) = await self._embedder.embed([query])
        scored = sorted(
            (
                (_cosine(q, v), pid)
                for pid, v in self._label_vectors.items()
                if pid not in resolved and pid in self._vault.pages
            ),
            key=lambda t: (-round(t[0], 12), t[1]),
        )
        out = dict(resolved)
        for _, pid in scored[:SEMANTIC_PAGES]:
            out[pid] = ("approximate", SEMANTIC_WEIGHT, ())
        return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"vectors of different lengths ({len(a)} and {len(b)}): the page labels were embedded by another model"
        )
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def embed_page_labels(vault: Vault, embedder: Embedder) -> dict[str, list[float]]:
    """One embedding per page, of its display label, in page-id order (the cost is the labels' tokens, a few thousand)."""
    ids = sorted(vault.pages)
    vectors = await embedder.embed([vault.pages[i].label for i in ids])
    return dict(zip(ids, vectors, strict=True))


def labels_sha256(vault: Vault) -> str:
    """A hash of the page ids and display labels, so label vectors can be tied to the vault they were made for."""
    body = json.dumps(sorted((pid, p.label) for pid, p in vault.pages.items()), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
