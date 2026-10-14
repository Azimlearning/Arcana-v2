# Adapted from Azimlearning/Arcana (v1), api/retrieval/hybrid.py @ 9a3d67f.
# Read in full. Kept: concurrent fan-out, per-retriever failure isolation, RRF. Dropped for v2: v1's
# local/global/auto modes (not in P0). Added: signals toggled by a parameter (the five ablation
# arms), and a result object that carries what the eval harness records.
"""hybrid_retrieve: the evidence path every grounded answer starts from (constraint 1).

Enabled retrievers run concurrently. A retriever that raises contributes an empty ranking (the
turn degrades, it does not fail) and is listed in `failed`. Rankings are fused with RRF (k = 60) and
cut to the top 10. Signals are switched with the `signals` argument, never by editing code.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection

from api.core.logging import get_logger
from api.retrieval.fusion import reciprocal_rank_fusion
from api.retrieval.types import (
    RRF_K,
    TOP_K,
    RetrievalResult,
    Retriever,
    RetrieverResult,
    Signal,
)

log = get_logger(__name__)

# A fixed order keeps logs and the per-signal map identical across runs.
_ORDER: tuple[Signal, ...] = ("dense", "sparse", "graph")


async def hybrid_retrieve(
    query: str,
    *,
    dense: Retriever,
    sparse: Retriever,
    graph: Retriever,
    signals: Collection[Signal] = _ORDER,
    top_k: int = TOP_K,
    rrf_k: int = RRF_K,
    depth: int | None = None,
) -> RetrievalResult:
    """`depth` is how many candidates each signal contributes before fusion (default: `top_k`, the frozen benchmark protocol); the fused list is
    always cut to `top_k`. A deeper per-signal list lets a passage ranked 11 to `depth` by one signal reach the fused top ten (D-38)."""
    per_signal_depth = top_k if depth is None else depth
    if per_signal_depth < top_k:
        raise ValueError("depth cannot be below top_k")
    wanted: frozenset[Signal] = frozenset(signals)
    unknown = wanted - set(_ORDER)
    if unknown:
        raise ValueError(f"unknown retrieval signal(s): {sorted(unknown)}")
    enabled: list[Signal] = [s for s in _ORDER if s in wanted]
    if not enabled:
        raise ValueError("at least one retrieval signal must be enabled")
    retrievers: dict[Signal, Retriever] = {"dense": dense, "sparse": sparse, "graph": graph}

    started = time.perf_counter()
    outcomes = await asyncio.gather(*(_safe(s, retrievers[s], query, per_signal_depth) for s in enabled))

    per_signal: dict[Signal, list] = {}
    failed: list[Signal] = []
    resolution = None
    for signal, outcome in zip(enabled, outcomes, strict=True):
        if outcome is None:
            failed.append(signal)
            per_signal[signal] = []
            continue
        per_signal[signal] = outcome.chunks[:per_signal_depth]  # top `depth` per signal (top k in the frozen protocol), whatever a retriever returns
        if outcome.resolution is not None:
            resolution = outcome.resolution

    fused = reciprocal_rank_fusion([per_signal[s] for s in enabled], k=rrf_k)[:top_k]
    latency_ms = (time.perf_counter() - started) * 1000
    log.info(
        "retrieval",
        signals=enabled,
        hits={s: len(per_signal[s]) for s in enabled},
        fused=len(fused),
        failed=failed,
        resolution_hit_rate=None if resolution is None else round(resolution.hit_rate, 3),
        resolved_entities=None if resolution is None else len(resolution.entities),
        latency_ms=round(latency_ms, 1),
    )
    return RetrievalResult(
        chunks=fused,
        per_signal=per_signal,
        signals=frozenset(enabled),
        failed=tuple(failed),
        resolution=resolution,
        latency_ms=latency_ms,
    )


async def _safe(
    signal: Signal, retriever: Retriever, query: str, top_k: int
) -> RetrieverResult | None:
    """Run one retriever; on any exception log it and return None (an empty ranking).

    `except Exception` deliberately does not catch asyncio.CancelledError, so a caller's timeout
    still cancels the retrieval instead of being turned into a degraded result.
    """
    try:
        return await retriever.retrieve(query, top_k)
    except Exception as exc:
        log.warning("retriever_failed", signal=signal, error=type(exc).__name__)
        return None
