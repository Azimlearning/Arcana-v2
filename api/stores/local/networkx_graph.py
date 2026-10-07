"""NetworkX GraphStore persisted to disk as JSON (D-09).

A MultiDiGraph: several relations, and the same relation from different chunks, can link two nodes.
Persistence is node-link JSON written atomically (temp file then replace), so a crash mid-save
cannot leave a truncated graph.
"""

from __future__ import annotations

import json
import os
from collections.abc import Collection, Iterable
from pathlib import Path

import networkx as nx

from api.stores.graph_store import Edge, GraphStore, Node, Subgraph


def _edge_key(relation: str, chunk_id: str) -> str:
    return f"{relation}|{chunk_id}"


class NetworkXGraphStore(GraphStore):
    def __init__(self, path: Path):
        self._path = path
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._g = nx.node_link_graph(data, edges="edges", multigraph=True, directed=True)

    def upsert_node(self, node: Node) -> None:
        if node.id in self._g:
            existing = self._g.nodes[node.id]
            existing["doc_ids"] = sorted(set(existing.get("doc_ids", [])) | set(node.doc_ids))
            existing["chunk_ids"] = sorted(set(existing.get("chunk_ids", [])) | set(node.chunk_ids))
            if existing.get("type") is None and node.type is not None:
                existing["type"] = node.type
            # The first note and kind seen are kept; nothing is written for a store that never has them.
            for name in ("kind", "note"):
                if existing.get(name) is None and getattr(node, name) is not None:
                    existing[name] = getattr(node, name)
        else:
            extra = {name: getattr(node, name) for name in ("kind", "note") if getattr(node, name) is not None}
            self._g.add_node(
                node.id,
                label=node.label,
                type=node.type,
                doc_ids=sorted(set(node.doc_ids)),
                chunk_ids=sorted(set(node.chunk_ids)),
                **extra,
            )

    def upsert_edge(self, edge: Edge) -> None:
        if not edge.chunk_id:
            raise ValueError("an edge must record the chunk it came from")
        for endpoint in (edge.src, edge.dst):
            if endpoint not in self._g:
                raise KeyError(f"edge endpoint {endpoint!r} is not a node; upsert nodes first")
        extra = {"evidence": edge.evidence} if edge.evidence is not None else {}
        self._g.add_edge(
            edge.src,
            edge.dst,
            key=_edge_key(edge.relation, edge.chunk_id),
            relation=edge.relation,
            chunk_id=edge.chunk_id,
            doc_id=edge.doc_id,
            **extra,
        )

    def _node(self, node_id: str) -> Node:
        d = self._g.nodes[node_id]
        return Node(
            id=node_id,
            label=d["label"],
            type=d.get("type"),
            doc_ids=tuple(d.get("doc_ids", [])),
            chunk_ids=tuple(d.get("chunk_ids", [])),
            kind=d.get("kind"),
            note=d.get("note"),
        )

    def get_node(self, node_id: str) -> Node | None:
        return self._node(node_id) if node_id in self._g else None

    def nodes(self) -> list[Node]:
        return [self._node(n) for n in self._g.nodes]

    def edges(self) -> list[Edge]:
        return [
            Edge(
                src=u,
                dst=v,
                relation=d["relation"],
                chunk_id=d["chunk_id"],
                doc_id=d["doc_id"],
                evidence=d.get("evidence"),
            )
            for u, v, d in self._g.edges(data=True)
        ]

    def expand(self, node_ids: Iterable[str], hops: int = 1) -> Subgraph:
        seeds = {n for n in node_ids if n in self._g}
        reached = set(seeds)
        frontier = set(seeds)
        edges: dict[tuple[str, str, str], Edge] = {}
        for _ in range(max(hops, 0)):
            next_frontier: set[str] = set()
            for n in frontier:
                incident = list(self._g.out_edges(n, keys=True, data=True)) + list(
                    self._g.in_edges(n, keys=True, data=True)
                )
                for u, v, key, d in incident:
                    edges[(u, v, key)] = Edge(
                        src=u,
                        dst=v,
                        relation=d["relation"],
                        chunk_id=d["chunk_id"],
                        doc_id=d["doc_id"],
                        evidence=d.get("evidence"),
                    )
                    for other in (u, v):
                        if other not in reached:
                            next_frontier.add(other)
            reached |= next_frontier
            frontier = next_frontier
        touched = {e.src for e in edges.values()} | {e.dst for e in edges.values()} | seeds
        return Subgraph(nodes=[self._node(n) for n in sorted(touched)], edges=list(edges.values()))

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        if src not in self._g or dst not in self._g:
            return None
        try:
            return list(nx.shortest_path(self._g.to_undirected(as_view=True), src, dst))
        except nx.NetworkXNoPath:
            return None

    def communities(self) -> list[set[str]]:
        if self._g.number_of_nodes() == 0:
            return []
        simple = nx.Graph(self._g.to_undirected())
        return [set(c) for c in nx.community.louvain_communities(simple, seed=0)]

    def delete_document(self, doc_id: str, chunk_ids: Collection[str] = ()) -> None:
        doomed = [(u, v, k) for u, v, k, d in self._g.edges(keys=True, data=True) if d["doc_id"] == doc_id]
        self._g.remove_edges_from(doomed)
        gone = set(chunk_ids)
        for n in list(self._g.nodes):
            ids = [d for d in self._g.nodes[n].get("doc_ids", []) if d != doc_id]
            self._g.nodes[n]["doc_ids"] = ids
            self._g.nodes[n]["chunk_ids"] = [c for c in self._g.nodes[n].get("chunk_ids", []) if c not in gone]
            if not ids:
                self._g.remove_node(n)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._g, edges="edges")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)
