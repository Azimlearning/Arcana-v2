"""The five ablation arms (D-15). Each is just a set of enabled signals; nothing else differs.

    dense   : dense only            sparse : BM25 only          graph : graph only
    flat    : dense + sparse        hybrid : dense + sparse + graph

`flat` vs `hybrid` is the comparison that measures what the knowledge graph adds.
"""

from __future__ import annotations

from api.retrieval.types import Signal

ARMS: dict[str, frozenset[Signal]] = {
    "dense": frozenset({"dense"}),
    "sparse": frozenset({"sparse"}),
    "graph": frozenset({"graph"}),
    "flat": frozenset({"dense", "sparse"}),
    "hybrid": frozenset({"dense", "sparse", "graph"}),
}
