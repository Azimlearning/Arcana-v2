"""Approximate query entity resolution: map a question onto graph nodes without an LLM call.

Two stages, both deterministic:

1. Exact: the longest word n-gram (up to 4, leftmost first) whose canonical slug is a node id. Also
   exact: the same n-gram with its separators removed, so a lowercase "graphrag" finds the node
   `graph_rag`. Matching is greedy and spans do not overlap, so "dense retrieval" does not also fire
   a separate "retrieval" node.
2. Approximate: for the content words exact matching left uncovered, nodes sharing at least half of
   their own tokens with those words, best first, at most three. Each uncovered word is claimed by at
   most one approximate node, so one word cannot be counted three times.

An approximate entity weighs 0.6 against 1.0 for an exact one. That is a per-entity weight: chunk
scores add across entities, so two approximate entities can outscore one exact one.

The report says how many of the query's content words the graph recognised, and how many of those
by exact match alone. It is logged for every query because the pilot's graph arm silently matched
nothing, which is indistinguishable from "the graph adds nothing" unless the match rate is recorded.

FROZEN constants (see D-20): changing any of these, or STOPWORDS, changes retrieval behaviour and
requires a declared amendment and a GRAPH_SCORING_VERSION bump in api/retrieval/graph.py.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from api.ingestion.extract import slug
from api.retrieval.types import ResolutionReport, ResolvedEntity
from api.stores.graph_store import Node

EXACT_WEIGHT = 1.0
APPROX_WEIGHT = 0.6
MAX_APPROX = 3
MIN_CONTAINMENT = 0.5
MAX_NGRAM = 4

_WORD_RE = re.compile(r"[A-Za-z0-9]+")

STOPWORDS = frozenset(
    """a an the of in on at to for from by with about as into over between across and or but not no
    is are was were be been being do does did doing has have had how what which who whom whose when
    where why that this these those it its their there than then can could should would may might
    will shall vs versus me us you i we they he she them his her our your
    compare describe explain tell discuss summarise summarize list give show find mention mentions
    say says work works use used using paper papers document documents""".split()
)


def _fold(token: str) -> str:
    """Lowercase singular form of one word, matching how node ids were canonicalised."""
    return slug(token)


def _compact(node_id: str) -> str:
    return node_id.replace("_", "")


def resolve_query_entities(query: str, nodes: Sequence[Node]) -> ResolutionReport:
    words = _WORD_RE.findall(query)
    low = [w.lower() for w in words]
    content = [i for i, w in enumerate(low) if w not in STOPWORDS]
    node_ids = {n.id for n in nodes}
    # "graphrag" -> graph_rag. On a collision the smallest id wins, so the choice is deterministic.
    compact_to_id: dict[str, str] = {}
    for node_id in sorted(node_ids):
        compact_to_id.setdefault(_compact(node_id), node_id)

    covered: set[int] = set()
    entities: list[ResolvedEntity] = []
    matched: set[str] = set()

    # Stage 1: longest exact n-gram first, then leftmost; never overlap an earlier match.
    for n in range(min(MAX_NGRAM, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            span = range(i, i + n)
            if any(j in covered for j in span):
                continue
            if low[i] in STOPWORDS or low[i + n - 1] in STOPWORDS:
                continue  # a phrase must start and end on a content word
            candidate = slug(" ".join(words[i : i + n]))
            node_id = candidate if candidate in node_ids else compact_to_id.get(_compact(candidate))
            if node_id is not None and node_id not in matched:
                matched.add(node_id)
                covered.update(span)
                entities.append(
                    ResolvedEntity(node_id, "exact", EXACT_WEIGHT, tuple(low[i : i + n]))
                )
    exact_covered = sum(1 for i in content if i in covered)

    # Stage 2: approximate, on the content words still uncovered.
    uncovered = {_fold(low[i]): i for i in content if i not in covered}
    if uncovered:
        candidates: list[tuple[float, int, int, str, frozenset[str]]] = []
        for node in nodes:
            if node.id in matched:
                continue
            tokens = {_fold(t) for t in node.id.split("_") if t and t not in STOPWORDS}
            if not tokens:
                continue
            overlap = frozenset(tokens & uncovered.keys())
            if not overlap:
                continue
            containment = len(overlap) / len(tokens)
            if containment >= MIN_CONTAINMENT:
                candidates.append((containment, len(overlap), len(node.doc_ids), node.id, overlap))
        candidates.sort(key=lambda c: (-c[0], -c[1], -c[2], c[3]))

        claimed: set[str] = set()
        accepted = 0
        for _, _, _, node_id, overlap in candidates:
            if accepted == MAX_APPROX:
                break
            if overlap <= claimed:
                continue  # every word it matches is already accounted for by a better node
            claimed |= overlap
            accepted += 1
            positions = sorted(uncovered[t] for t in overlap)
            covered.update(positions)
            entities.append(
                ResolvedEntity(node_id, "approximate", APPROX_WEIGHT, tuple(low[p] for p in positions))
            )

    covered_content = sum(1 for i in content if i in covered)
    return ResolutionReport(len(content), covered_content, tuple(entities), exact_covered)
