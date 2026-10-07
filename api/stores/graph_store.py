"""GraphStore: the knowledge graph behind an abstraction (constraint 6, D-09).

Code calls this interface, never NetworkX or Neo4j directly. Every edge records the chunk it was
extracted from, which is what lets a graph hit be traced back to evidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    id: str
    """Canonical key (normalised entity name). Identical across documents, so nodes merge."""
    label: str
    """Display name as first seen."""
    type: str | None = None
    doc_ids: tuple[str, ...] = ()
    """Every document that mentions this entity."""
    chunk_ids: tuple[str, ...] = ()
    """Every chunk that mentions it, including chunks where it appears with no relation. Graph
    retrieval needs these: edges alone only reach chunks that contain a relation."""
    kind: str | None = None
    """What the note is about (concept, method, person, ...). Only the atomic builder (G1) sets it."""
    note: str | None = None
    """One verbatim sentence of a chunk that names the concept: the first one seen. Only the atomic builder sets it."""


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    relation: str
    chunk_id: str
    """The stored chunk this edge was extracted from. Never empty."""
    doc_id: str
    evidence: str | None = None
    """One verbatim sentence of the source chunk that states the relation and names both ends. Only the atomic builder
    sets it; the free-form extractor leaves it empty."""


@dataclass(frozen=True)
class Subgraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


class GraphStore(ABC):
    @abstractmethod
    def upsert_node(self, node: Node) -> None:
        """Insert, or merge into an existing node (doc_ids are unioned, first label kept)."""

    @abstractmethod
    def upsert_edge(self, edge: Edge) -> None:
        """Insert an edge. The same (src, relation, dst, chunk_id) twice is a no-op."""

    @abstractmethod
    def get_node(self, node_id: str) -> Node | None: ...

    @abstractmethod
    def nodes(self) -> list[Node]: ...

    @abstractmethod
    def edges(self) -> list[Edge]: ...

    @abstractmethod
    def expand(self, node_ids: Iterable[str], hops: int = 1) -> Subgraph:
        """Edges within `hops` of the seeds (either direction), with the nodes they touch."""

    @abstractmethod
    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """Node ids from src to dst ignoring edge direction, or None if unconnected."""

    @abstractmethod
    def communities(self) -> list[set[str]]:
        """Node-id groups from community detection (Louvain in the local implementation)."""

    @abstractmethod
    def delete_document(self, doc_id: str, chunk_ids: Collection[str] = ()) -> None:
        """Remove a document's edges, drop it (and its `chunk_ids`) from every node, and drop nodes
        no document mentions any more."""

    @abstractmethod
    def save(self) -> None:
        """Persist to the backing store. A reopened store reads back the same graph."""
