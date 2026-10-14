"""Retrieval types shared by the three retrievers, fusion and the hybrid entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Signal = Literal["dense", "sparse", "graph"]
ALL_SIGNALS: frozenset[Signal] = frozenset({"dense", "sparse", "graph"})

# Benchmark protocol: top 10 per signal and after fusion; RRF constant 60.
TOP_K = 10
RRF_K = 60

# The product path draws this many candidates from each signal before fusing and keeps the fused top TOP_K. D-38 set it to 30; the declared
# extension questions did not confirm it (D-40: Recall@10 -0.007 on 19 new questions), so by the rule fixed in advance it is back at TOP_K,
# the frozen protocol (D-20). The `depth` parameter of `hybrid_retrieve` stays for the experiments.
CANDIDATE_DEPTH = TOP_K


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    doc_id: str
    text: str
    page: int | None
    score: float
    """The signal's own score before fusion; the fused RRF score after it. Ranks are what fusion uses."""
    sources: tuple[Signal, ...]
    """Which signals ranked this chunk. After fusion it is every signal that contributed."""


@dataclass(frozen=True)
class ResolvedEntity:
    node_id: str
    match: Literal["exact", "approximate"]
    weight: float
    """1.0 for an exact match, lower for an approximate one. This is the weight of ONE entity: chunk
    scores add across entities, so two approximate entities (2 x 0.6) can outscore one exact one."""
    query_tokens: tuple[str, ...]
    """The query words this match accounts for."""


@dataclass(frozen=True)
class ResolutionReport:
    """How much of the query the graph recognised. Logged for every query: a silent failure to match
    query entities to graph nodes looks exactly like "the graph adds nothing" (the pilot's failure)."""

    content_tokens: int
    """Query words that are not stopwords."""
    covered_tokens: int
    """Content words that an exact or approximate match accounts for."""
    entities: tuple[ResolvedEntity, ...] = ()
    exact_covered_tokens: int = 0
    """Content words covered by EXACT matches only. Report this beside hit_rate: approximate matches
    flatter the overall number."""

    @property
    def hit_rate(self) -> float:
        return self.covered_tokens / self.content_tokens if self.content_tokens else 0.0

    @property
    def exact_hit_rate(self) -> float:
        return self.exact_covered_tokens / self.content_tokens if self.content_tokens else 0.0

    @property
    def n_exact(self) -> int:
        return sum(1 for e in self.entities if e.match == "exact")

    @property
    def n_approx(self) -> int:
        return sum(1 for e in self.entities if e.match == "approximate")

    @property
    def any_resolved(self) -> bool:
        return bool(self.entities)


@dataclass(frozen=True)
class RetrieverResult:
    chunks: list[RetrievedChunk]
    resolution: ResolutionReport | None = None
    """Only the graph retriever sets this."""


class Retriever(Protocol):
    async def retrieve(self, query: str, top_k: int = TOP_K) -> RetrieverResult: ...


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    """Fused, best first, at most TOP_K."""
    per_signal: dict[Signal, list[RetrievedChunk]] = field(default_factory=dict)
    signals: frozenset[Signal] = ALL_SIGNALS
    failed: tuple[Signal, ...] = ()
    """Enabled signals whose retriever raised; each contributed an empty ranking."""
    resolution: ResolutionReport | None = None
    latency_ms: float = 0.0
