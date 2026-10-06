"""The component catalog: what each component needs from retrieval before the Composer may show it (D-28).

A `Spec` is a component's written structural precondition (catalog.md, "The bound") as a pure function of
`ComposerEvidence`. The evidence is plain data built once per turn from what the agents returned: no store
handles, no model, so a check is deterministic and the Composer needs no provider call to decide.

This module knows nothing about blocks' wire shapes beyond the type name and nothing about agents. Adding a
component is a new `Spec` here plus the steps in catalog.md, "How to add a component"; the Composer and the
layout do not change (D-27).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast, get_args

from api.genui.alignment import settle
from api.genui.generated import ComponentDecision, DecisionReason, LayoutSpec, PanelId, UIBlock
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
class PlacementHint:
    """A hint to the layout, not a position (D-27): the panel this component prefers and its priority in it."""

    panel: PanelId
    priority: int


@dataclass(frozen=True)
class Result:
    satisfied: bool
    reasons: tuple[str, ...] = ()
    """Short codes saying why not (empty when satisfied)."""


@dataclass(frozen=True)
class Slot:
    """A typed parameter a saved pattern may carry for a template. Strings only: an `entity` is a label the graph
    resolves, a `document_id` names a stored document. A pattern carries no evidence, only these."""

    name: str
    kind: Literal["entity", "document_id"]
    min_count: int = 1
    max_count: int = 1


@dataclass(frozen=True)
class A11yRequirement:
    """A role and label the component must expose (checked statically against its source, see test_templates)."""

    role: str
    label: str


@dataclass(frozen=True)
class Fences:
    """The declared limits a template stays inside (D-31). The validator, the Composer and the Graph agent all read
    their caps from here, so there is one source of truth; catalog.md states the same numbers and a test parses them."""

    caps: dict[str, int]
    grounding: str
    """The id of the grounding rule the template's block must satisfy (see catalog.md, "Conventions")."""
    a11y: tuple[A11yRequirement, ...] = ()


@dataclass(frozen=True)
class Spec:
    """A template: the reviewed, versioned recipe for one component (D-31). Generation starts from it."""

    name: str
    """The `type` tag of the block, exactly as in the schema's UIBlock union."""
    precondition: str
    """The structural precondition in words, as written in catalog.md."""
    supplied_by: tuple[str, ...]
    """The agents whose output the check reads."""
    fences: Fences
    placement: PlacementHint
    check: Callable[[ComposerEvidence], Result]
    version: int = 1
    """Bumped when the template's preconditions, fences or block shape change; a saved pattern records the version it
    was made with and is stale (until re-verified) when it differs."""
    slots: tuple[Slot, ...] = ()
    """The parameters a saved pattern of this template may carry."""
    reusable: bool = False
    """True if a saved pattern can be applied without Research: its evidence is re-bound by the Graph agent's tools."""
    terminal: bool = False
    """The turn's answer component. When its precondition fails the Composer shows its empty state instead of
    omitting it, so every turn ends with a visible result (constraint 4)."""

    @property
    def caps(self) -> dict[str, int]:
        return self.fences.caps


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
    layout: LayoutSpec | None = None
    """The validated adaptive layout, or None when it could not be composed or failed validation."""
    layout_failure: tuple[str, ...] = ()
    """Field paths (or a short code) saying why there is no layout. Empty when there is one."""

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
    fences=Fences(
        caps={"segments": 40, "citations": 40},
        grounding="citation_verbatim_quote",
        a11y=(A11yRequirement("region", "Sources"),),
    ),
    placement=PlacementHint(panel="chat", priority=10),
    check=_check_cited_summary,
    terminal=True,
)


def cap(component: str, key: str) -> int:
    """One cap of one template's fences (read at call time, so a change in the fences is a change everywhere)."""
    return CATALOG[component].fences.caps[key]


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
    caps = CATALOG["GraphView"].fences.caps
    labels: dict[str, str] = graph.get("labels") or {}
    drawn: list[dict[str, Any]] = []
    nodes: set[str] = set()
    for edge in graph.get("edges") or []:
        src, dst = edge.get("src"), edge.get("dst")
        quote, page, title = edge.get("quote"), edge.get("page"), edge.get("doc_title")
        relation = str(edge.get("relation") or "").replace("_", " ").strip()
        if not (isinstance(quote, str) and quote and isinstance(title, str) and title and src != dst):
            continue
        if src not in labels or dst not in labels or not relation or len(relation) > caps["relation_chars"]:
            continue
        if any(not MIN_LABEL_CHARS <= len(labels[n].strip()) <= caps["label_chars"] for n in (src, dst)):
            continue
        # The same tests the validator applies to the quote, so an edge admitted here cannot sink the whole block.
        if len(normalise(quote)) < MIN_QUOTE_CHARS or not all(label_in_quote(quote, labels[n]) for n in (src, dst)):
            continue
        if len(drawn) >= caps["edges"] or len(nodes | {src, dst}) > caps["nodes"]:
            continue
        nodes.update((src, dst))
        drawn.append({**edge, "relation": relation, "page": page if isinstance(page, int) else None})
    return drawn


def alignment_grid(
    graph: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(documents, dimensions, cells) a ComparisonGrid may show, from the Graph agent's alignment, or three empty
    lists when there is no comparison. Each cell must carry a verbatim quote of at least the minimum length that
    names its dimension's label (the tests the validator applies), then the documents and dimensions are settled
    again (see `settle`): every dimension in two or more rows, every row with a cell, both within the caps. A pure
    function of the payload, shared by the check and the Composer."""
    caps = CATALOG["ComparisonGrid"].fences.caps
    alignment = (graph or {}).get("alignment") or {}
    labels: dict[str, str] = {}
    seen_labels: set[str] = set()
    for d in alignment.get("dimensions") or []:
        label = d.get("label")
        if isinstance(d.get("id"), str) and isinstance(label, str) and normalise(label).lower() not in seen_labels:
            seen_labels.add(normalise(label).lower())  # two columns with one label would say the same thing twice
            labels[d["id"]] = label
    titles = {
        d["doc_id"]: d["title"]
        for d in alignment.get("documents") or []
        if isinstance(d.get("doc_id"), str) and isinstance(d.get("title"), str)
    }
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for cell in alignment.get("cells") or []:
        doc_id, dim_id, quote = cell.get("doc_id"), cell.get("dimension_id"), cell.get("quote")
        if doc_id not in titles or dim_id not in labels or not isinstance(quote, str):
            continue
        if not MIN_LABEL_CHARS <= len(labels[dim_id].strip()) <= caps["label_chars"]:
            continue
        if len(normalise(quote)) < MIN_QUOTE_CHARS or not label_in_quote(quote, labels[dim_id]):
            continue
        if cell.get("doc_title") != titles[doc_id]:
            continue
        cells.setdefault((doc_id, dim_id), cell)
    docs, dims = settle(list(titles), list(labels), set(cells), max_docs=caps["documents"], max_dims=caps["entities"])
    if len(docs) < 2 or len(dims) < 2:
        return [], [], []
    return (
        [{"doc_id": d, "title": titles[d]} for d in docs],
        [{"id": n, "label": labels[n]} for n in dims],
        [cells[(d, n)] for d in docs for n in dims if (d, n) in cells],
    )


def _check_comparison_grid(evidence: ComposerEvidence) -> Result:
    if evidence.graph is None:
        return Result(False, ("no_graph_result",))
    documents, dimensions, _ = alignment_grid(evidence.graph)
    return Result(True) if documents and dimensions else Result(False, ("no_shared_entities",))


COMPARISON_GRID = Spec(
    name="ComparisonGrid",
    precondition=(
        "At least two documents and two entities remain after alignment, every entity evidenced in two or more of "
        "the documents by a verbatim quote naming it."
    ),
    supplied_by=("graph",),
    fences=Fences(
        caps={"documents": 6, "entities": 8, "label_chars": 120},
        grounding="quote_of_row_document_names_column_label",
        a11y=(
            A11yRequirement("table", "Comparison of"),
            A11yRequirement("region", "Comparison table"),
            A11yRequirement("region", "Sources"),
        ),
    ),
    slots=(Slot("entities", "entity", 2, 8), Slot("documents", "document_id", 0, 6)),
    reusable=True,
    placement=PlacementHint(panel="chat", priority=20),
    check=_check_comparison_grid,
)


def concept_path(graph: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str | None]:
    """(steps, reason): the Graph agent's path as ConceptMap steps in path order, or no steps and the reason it cannot
    be one. Every hop must carry a verbatim quote naming both of its concepts (a hop without one breaks the path:
    the map would otherwise skip a link), the hops must join up from the first entity, no concept may repeat, and
    there must be 2 to 6 hops (a single hop is a GraphView case). `reversed` marks a hop whose stored relation runs
    against the path, so the map never states a relation the wrong way round. Pure, shared by the check and the
    Composer."""
    if not graph:
        return [], "no_graph_result"
    caps = CATALOG["ConceptMap"].fences.caps
    edges = graph.get("edges") or []
    entities = graph.get("entities") or []
    if graph.get("mode") != "path" or not edges or not entities:
        return [], "not_a_path"
    if len(edges) < caps["min_steps"]:
        return [], "single_hop"
    if len(edges) > caps["steps"]:
        return [], "path_too_long"
    labels: dict[str, str] = graph.get("labels") or {}
    steps: list[dict[str, Any]] = []
    current = entities[0]
    seen = {normalise(labels.get(current, "")).lower()}
    for edge in edges:
        if edge.get("src") == current:
            following, backwards = edge.get("dst"), False
        elif edge.get("dst") == current:
            following, backwards = edge.get("src"), True
        else:
            return [], "broken_path"
        quote, title = edge.get("quote"), edge.get("doc_title")
        relation = str(edge.get("relation") or "").replace("_", " ").strip()
        if current not in labels or following not in labels:
            return [], "ungrounded_hop"
        names = (labels[current], labels[following])
        if not (
            isinstance(quote, str)
            and isinstance(title, str)
            and title
            and relation
            and len(relation) <= caps["relation_chars"]
            and all(MIN_LABEL_CHARS <= len(n.strip()) <= caps["label_chars"] for n in names)
            and len(normalise(quote)) >= MIN_QUOTE_CHARS
            and all(label_in_quote(quote, n) for n in names)
        ):
            return [], "ungrounded_hop"
        key = normalise(names[1]).lower()
        if key in seen:
            return [], "repeated_concept"
        seen.add(key)
        page = edge.get("page")
        steps.append(
            {
                "source": names[0],
                "target": names[1],
                "relation": relation,
                "reversed": backwards,
                "chunk_id": edge["chunk_id"],
                "doc_id": edge["doc_id"],
                "doc_title": title,
                "page": page if isinstance(page, int) else None,
                "quote": quote,
            }
        )
        current = following
    if current != entities[-1]:
        return [], "broken_path"  # the walk must end at the question's second entity
    return steps, None


def _check_concept_map(evidence: ComposerEvidence) -> Result:
    steps, reason = concept_path(evidence.graph)
    return Result(True) if steps else Result(False, (reason or "not_a_path",))


CONCEPT_MAP = Spec(
    name="ConceptMap",
    precondition=(
        "The Graph agent found a path of two to six hops between two entities, every hop backed by a verbatim quote "
        "naming both of its concepts, with no concept repeated."
    ),
    supplied_by=("graph",),
    fences=Fences(
        caps={"min_steps": 2, "steps": 6, "label_chars": 120, "relation_chars": 80},
        grounding="quote_names_both_ends_of_every_step",
        a11y=(A11yRequirement("list", "Steps"), A11yRequirement("region", "Sources")),
    ),
    slots=(Slot("entities", "entity", 2, 2),),
    reusable=True,
    placement=PlacementHint(panel="studio", priority=30),
    check=_check_concept_map,
)


def _check_graph_view(evidence: ComposerEvidence) -> Result:
    if evidence.graph is None:
        return Result(False, ("no_graph_result",))
    return Result(True) if graph_edges(evidence.graph) else Result(False, ("no_grounded_edge",))


GRAPH_VIEW = Spec(
    name="GraphView",
    precondition="The Graph agent returned at least one edge whose chunk holds a verbatim quote naming both endpoints.",
    supplied_by=("graph",),
    fences=Fences(
        caps={"nodes": 30, "edges": 40, "label_chars": 120, "relation_chars": 80},
        grounding="quote_names_both_ends_of_every_edge",
        a11y=(
            A11yRequirement("group", "Graph of"),
            A11yRequirement("region", "Relations"),
            A11yRequirement("region", "Details"),
            A11yRequirement("region", "Sources"),
        ),
    ),
    slots=(Slot("entities", "entity", 1, 2),),
    reusable=True,
    placement=PlacementHint(panel="studio", priority=20),
    check=_check_graph_view,
)

SOURCE_LIST = Spec(
    name="SourceList",
    precondition="At least one document in the store has status ready.",
    supplied_by=("document_store",),
    fences=Fences(
        caps={"documents": 50},
        grounding="stored_document_metadata",
        a11y=(A11yRequirement("region", "Documents"),),
    ),
    reusable=True,
    placement=PlacementHint(panel="sources", priority=10),
    check=_check_source_list,
)

CATALOG: dict[str, Spec] = {
    spec.name: spec for spec in (CITED_SUMMARY, SOURCE_LIST, GRAPH_VIEW, COMPARISON_GRID, CONCEPT_MAP)
}
"""Every component the Composer may admit, in the order it considers them (the terminal one first)."""

_KNOWN_REASONS: frozenset[str] = frozenset(get_args(DecisionReason))


def component_decisions(records: Iterable[ComponentRecord]) -> list[ComponentDecision]:
    """The Composer's records as the trace's decisions: one per catalog component, in catalog order. A component with
    no record (the turn ended before it was considered) is `not_considered`. Only codes in the schema's closed list
    are kept, anything else becomes `unspecified`, so a trace never carries free text (no exception message, no
    document text, no question text)."""
    by_name = {r.component: r for r in records}
    decisions: list[ComponentDecision] = []
    for name in CATALOG:
        record = by_name.get(name)
        if record is None:
            decisions.append(ComponentDecision(component=name, offered=False, reasons=["not_considered"]))
            continue
        reasons = [r if r in _KNOWN_REASONS else "unspecified" for r in record.reasons]
        decisions.append(
            ComponentDecision(
                component=name,
                offered=record.outcome in ("admitted", "empty"),
                reasons=cast("list[DecisionReason]", reasons),
            )
        )
    return decisions
