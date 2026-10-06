"""Settling an entity-by-document grid: which documents and entities may be shown together.

A comparison needs every shown entity evidenced in at least two shown documents, and every shown document to carry
at least one shown entity. Dropping a document can strand an entity and the reverse, so the two rules are applied
until nothing changes. Pure and order-preserving: used by the Graph agent when it aligns documents and again by the
catalog when it admits the grid, so both apply one definition.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

MAX_GRID_DOCS = 6
MAX_GRID_DIMS = 8


def settle(
    doc_order: Sequence[str],
    dim_order: Sequence[str],
    present: Collection[tuple[str, str]],
    *,
    max_docs: int,
    max_dims: int,
) -> tuple[list[str], list[str]]:
    """The documents and dimensions that survive, each in the order given. `present` holds (doc, dimension) pairs
    that have evidence. Documents are capped before dimensions, so a cap never reorders what is kept."""
    docs = list(dict.fromkeys(doc_order))[:max_docs]
    dims = list(dict.fromkeys(dim_order))[:max_dims]
    while True:
        kept_dims = [d for d in dims if sum((doc, d) in present for doc in docs) >= 2]
        kept_docs = [doc for doc in docs if any((doc, d) in present for d in kept_dims)]
        if kept_dims == dims and kept_docs == docs:
            return docs, dims
        docs, dims = kept_docs, kept_dims
