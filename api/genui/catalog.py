"""The component catalog: what each component needs from retrieval before the Composer may show it (D-28).

A `Spec` is a component's written structural precondition (catalog.md, "The bound") as a pure function of
`ComposerEvidence`. The evidence is plain data built once per turn from what the agents returned: no store
handles, no model, so a check is deterministic and the Composer needs no provider call to decide.

This module knows nothing about blocks' wire shapes beyond the type name and nothing about agents. Adding a
component is a new `Spec` here plus the steps in catalog.md, "How to add a component"; the Composer and the
layout do not change (D-27).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from api.genui.generated import UIBlock
from api.genui.text import MIN_LABEL_CHARS, MIN_QUOTE_CHARS, label_in_quote, normalise
from api.stores.doc_store import Document


@dataclass(frozen=True)
class ComposerEvidence:
    """Everything the catalog may look at for one turn."""

    answer: dict[str, Any] | None
    """The CitedSummary payload after the Fact Checker, or None when nothing could be grounded."""
    graph: dict[str, Any] | None
    """The Graph agent's payload (mode, entities, nodes, edges, chunk_ids), or None when it did not run."""
    documents: tuple[Document, ...]
    intent: str
    chunk_counts: Mapping[str, int] = field(default_factory=dict)
    """Stored passage count per document id, for the documents listed above."""


@dataclass(frozen=True)
class Placement:
    """A hint to the layout, not a position (D-27): the panel this component prefers and its priority in it."""

    panel: str
    priority: int


@dataclass(frozen=True)
class Result:
    satisfied: bool
    reasons: tuple[str, ...] = ()
    """Short codes saying why not (empty when satisfied)."""


@dataclass(frozen=True)
class Spec:
    name: str
    """The `type` tag of the block, exactly as in the schema's UIBlock union."""
    precondition: str
    """The structural precondition in words, as written in catalog.md."""
    supplied_by: tuple[str, ...]
    """The agents whose output the check reads."""
    caps: Mapping[str, int]
    placement: Placement
    check: Callable[[ComposerEvidence], Result]
    terminal: bool = False
    """The turn's answer component. When its precondition fails the Composer shows its empty state instead of
    omitting it, so every turn ends with a visible result (constraint 4)."""


RecordOutcome = Literal["admitted", "empty", "refused", "error"]


@dataclass(frozen=True)
class ComponentRecord:
    """What the Composer decided for one component this turn, kept for the trace."""

    component: str
    outcome: RecordOutcome
    reasons: tuple[str, ...] = ()
    block_id: str | None = None


@dataclass(frozen=True)
class Composition:
    """The Composer's whole output for a turn: the blocks to stream (the terminal one first) and one record
    per component the catalog considered."""

    blocks: tuple[UIBlock, ...]
    records: tuple[ComponentRecord, ...] = field(default=())

    @property
    def primary(self) -> UIBlock:
        return self.blocks[0]


# ── the components ────────────────────────────────────────────────────────────


def _check_cited_summary(evidence: ComposerEvidence) -> Result:
    segments = evidence.answer.get("segments") if evidence.answer else None
    return Result(True) if segments else Result(False, ("no_grounded_answer",))


CITED_SUMMARY = Spec(
    name="CitedSummary",
    precondition="The Research agent produced at least one segment, each citing a stored chunk.",
    supplied_by=("research", "fact_checker"),
    caps={"segments": 40, "citations": 40},
    placement=Placement(panel="chat", priority=10),
    check=_check_cited_summary,
    terminal=True,
)

MAX_SOURCES = 50
MAX_GRAPH_NODES = 30
MAX_GRAPH_EDGES = 40
MAX_LABEL_CHARS = 120
MAX_RELATION_CHARS = 80


def _check_source_list(evidence: ComposerEvidence) -> Result:
    return (
        Result(True) if any(d.status == "ready" for d in evidence.documents) else Result(False, ("no_ready_document",))
    )


def graph_edges(graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The Graph agent's edges that a GraphView may draw, in the agent's order: each has a verbatim quote holding
    both endpoint labels, two different endpoints, a label and a relation within the caps. Edges are taken while
    the drawing stays within the node and edge caps. A pure function of the payload, shared by the check and the
    Composer so the two cannot disagree."""
    if not graph:
        return []
    labels: dict[str, str] = graph.get("labels") or {}
    drawn: list[dict[str, Any]] = []
    nodes: set[str] = set()
    for edge in graph.get("edges") or []:
        src, dst = edge.get("src"), edge.get("dst")
        quote, page, title = edge.get("quote"), edge.get("page"), edge.get("doc_title")
        relation = str(edge.get("relation") or "").replace("_", " ").strip()
        if not (isinstance(quote, str) and quote and isinstance(title, str) and title and src != dst):
            continue
        if src not in labels or dst not in labels or not relation or len(relation) > MAX_RELATION_CHARS:
            continue
        if any(not MIN_LABEL_CHARS <= len(labels[n].strip()) <= MAX_LABEL_CHARS for n in (src, dst)):
            continue
        # The same tests the validator applies to the quote, so an edge admitted here cannot sink the whole block.
        if len(normalise(quote)) < MIN_QUOTE_CHARS or not all(label_in_quote(quote, labels[n]) for n in (src, dst)):
            continue
        if len(drawn) >= MAX_GRAPH_EDGES or len(nodes | {src, dst}) > MAX_GRAPH_NODES:
            continue
        nodes.update((src, dst))
        drawn.append({**edge, "relation": relation, "page": page if isinstance(page, int) else None})
    return drawn


def _check_graph_view(evidence: ComposerEvidence) -> Result:
    if evidence.graph is None:
        return Result(False, ("no_graph_result",))
    return Result(True) if graph_edges(evidence.graph) else Result(False, ("no_grounded_edge",))


GRAPH_VIEW = Spec(
    name="GraphView",
    precondition="The Graph agent returned at least one edge whose chunk holds a verbatim quote naming both endpoints.",
    supplied_by=("graph",),
    caps={"nodes": MAX_GRAPH_NODES, "edges": MAX_GRAPH_EDGES},
    placement=Placement(panel="studio", priority=20),
    check=_check_graph_view,
)

SOURCE_LIST = Spec(
    name="SourceList",
    precondition="At least one document in the store has status ready.",
    supplied_by=("document_store",),
    caps={"documents": MAX_SOURCES},
    placement=Placement(panel="sources", priority=10),
    check=_check_source_list,
)

CATALOG: dict[str, Spec] = {spec.name: spec for spec in (CITED_SUMMARY, SOURCE_LIST, GRAPH_VIEW)}
"""Every component the Composer may admit, in the order it considers them (the terminal one first)."""
