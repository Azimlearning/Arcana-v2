"""Server-side block validation. Every block passes through here before it can be streamed, and a
violation fails closed: it becomes a ValidationFailed carrying field-path issues, never a partial or
best-effort block (constraint 2).

Two layers:
  1. Schema: the generated strict models (types, required fields, no unknown fields, valid enum).
  2. Content rules the schema cannot express, per block status:
       - meta.error is set if and only if status is "error";
       - "empty", "loading" and "error" blocks are placeholders: no segments, no citations;
       - "ready" and "partial" blocks: every segment cites at least one citation that exists in the
         block, citation ids are unique, each citation's chunk resolves in the DocStore under the
         document it names, and its quote is a verbatim span of that chunk;
       - "ready" additionally needs at least one segment (so at least one citation);
       - no orphan citations (every citation is cited by some segment), no id cited twice in one
         segment, docTitle and page equal the stored document's title and the chunk's page, and a
         quote is at least MIN_QUOTE_CHARS long (or the whole chunk, if it is shorter);
       - any block: a non-empty id (upsert-by-id keys on it);
       - "SourceList": placeholders carry no documents; otherwise at most the template's `documents` fence, unique ids, each id a
         stored document that is ready, with the stored title and passage count ("ready" needs one or more).
       - "ConceptMap": `min_steps` to `steps` steps (the template's fences), each starting where the previous one ended, no concept repeated,
         and each step's cited quote contains both of its labels. A step's `relation` and `reversed` flag come from
         the Composer, which read them from the graph: this validator holds the DocStore only, so it can prove
         co-mention in a stored quote but not the direction of a relation.
       - a block type with no rules here is refused, so a component cannot ship without written invariants.

Issue paths are dotted and relative to the block, e.g. "data.segments.0.citationIds.1". The
discriminator tag Pydantic puts at the front of a union member's path is stripped so the path still
points into the block.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from api.core.errors import ValidationFailed
from api.genui.bibliography import reference_for
from api.genui.catalog import CATALOG
from api.genui.generated import (
    Citation,
    CitedSummary,
    ComparisonGrid,
    ConceptMap,
    ConceptPage,
    FieldIssue,
    GraphView,
    LayoutSpec,
    NotesGraph,
    QuizCard,
    SourceList,
    StudyPlan,
    StudySet,
    TraversalView,
    UIBlock,
    VerifiedLab,
    WritingDraft,
)
from api.genui.text import MIN_LABEL_CHARS, MIN_QUOTE_CHARS, label_in_quote
from api.genui.text import normalise as _norm
from api.labs.checker import check_source
from api.labs.contract import CONTRACTS
from api.labs.evidence import BLANK_LAB_DATA, derive_lab_data, find_source
from api.labs.store import LabStore
from api.labs.verifier import TEMPLATE_VERSION, contract_sha256
from api.learner.mastery import MasteryScore
from api.retrieval.traversal import SeedNode, seed_weight, steps_for_display, traverse
from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore
from api.vault.quiz import derive_quiz
from api.vault.review import derive_study_plan
from api.vault.study import derive_study_set
from api.vault.types import Vault
from api.vault.view import derive_concept_page, derive_notes_graph

_UI_BLOCK = TypeAdapter(UIBlock)
PLACEHOLDER_STATUSES = {"empty", "loading", "error"}


def _path(loc: tuple[Any, ...], tag: str | None) -> str:
    parts = [str(p) for p in loc]
    if tag is not None and parts and parts[0] == tag:
        parts = parts[1:]  # drop the discriminator tag Pydantic prepends for a union member
    return ".".join(parts) or "(block)"


_TAG_ERRORS = {"union_tag_invalid", "union_tag_not_found"}


def _schema_issues(exc: ValidationError, tag: str | None) -> list[FieldIssue]:
    # With a discriminated union, a missing or unknown `type` is reported with an empty location: name it.
    return [
        FieldIssue(path="type" if e["type"] in _TAG_ERRORS else _path(e["loc"], tag), message=e["msg"])
        for e in exc.errors()
    ]


def validate_block(
    raw: Mapping[str, Any],
    docs: DocStore,
    graph: GraphStore | None = None,
    vault: Vault | None = None,
    mastery: Mapping[str, MasteryScore] | None = None,
    labs: LabStore | None = None,
    last_rated: Mapping[str, datetime] | None = None,
) -> UIBlock:
    """Return the validated block, or raise ValidationFailed naming every violated field. `graph` is the graph store
    the claims of a graph-derived block (a `TraversalView`) are re-derived from, and `vault` the vault those of a
    notes block (a `ConceptPage` or a `NotesGraph`) are re-derived from; a block of such a kind is refused when its
    source is not given, because its claims could not be checked. `mastery` is the learner's snapshot a notes block's mastery is
    checked against (D-35 A6); a block that claims a mastery the snapshot does not hold, or any when none is given, is refused."""
    tag = raw.get("type") if isinstance(raw.get("type"), str) else None
    try:
        block = _UI_BLOCK.validate_python(dict(raw))
    except ValidationError as exc:
        raise ValidationFailed("The block does not match the wire schema.", _schema_issues(exc, tag)) from exc

    issues = _content_issues(block, docs, graph, vault, mastery, labs, last_rated)
    if issues:
        raise ValidationFailed("The block failed content validation.", issues)
    return block


def _content_issues(
    block: UIBlock,
    docs: DocStore,
    graph: GraphStore | None,
    vault: Vault | None = None,
    mastery: Mapping[str, MasteryScore] | None = None,
    labs: LabStore | None = None,
    last_rated: Mapping[str, datetime] | None = None,
) -> list[FieldIssue]:
    """Rules common to every block, then the rules of its own type. A type with no rules here is refused:
    a component is not shown until its invariants are written down (constraint 7)."""
    issues = _common_issues(block)
    if isinstance(block, CitedSummary):
        issues += _cited_summary_issues(block, docs)
    elif isinstance(block, SourceList):
        issues += _source_list_issues(block, docs)
    elif isinstance(block, GraphView):
        issues += _graph_view_issues(block, docs)
    elif isinstance(block, ComparisonGrid):
        issues += _comparison_grid_issues(block, docs)
    elif isinstance(block, ConceptMap):
        issues += _concept_map_issues(block, docs)
    elif isinstance(block, TraversalView):
        issues += _traversal_view_issues(block, docs, graph)
    elif isinstance(block, ConceptPage):
        issues += _concept_page_issues(block, docs, vault, mastery)
    elif isinstance(block, NotesGraph):
        issues += _notes_graph_issues(block, docs, vault, mastery)
    elif isinstance(block, QuizCard):
        issues += _quiz_card_issues(block, docs, vault, mastery)
    elif isinstance(block, VerifiedLab):
        issues += _verified_lab_issues(block, docs, labs)
    elif isinstance(block, WritingDraft):
        issues += _writing_draft_issues(block, docs)
    elif isinstance(block, StudySet):
        issues += _study_set_issues(block, docs, vault, mastery)
    elif isinstance(block, StudyPlan):
        issues += _study_plan_issues(block, vault, mastery, last_rated)
    else:
        issues.append(FieldIssue(path="type", message="no content rules exist for this block type"))
    return issues


def _common_issues(block: UIBlock) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    status, error = block.meta.status, block.meta.error

    if not block.id.strip():
        issues.append(FieldIssue(path="id", message="must not be empty"))
    if (status == "error") != (error is not None):
        issues.append(
            FieldIssue(
                path="meta.error",
                message="must be set if and only if status is 'error'",
            )
        )
    return issues


def _source_list_issues(block: SourceList, docs: DocStore) -> list[FieldIssue]:
    caps = _caps("SourceList")
    documents = block.data.documents
    if block.meta.status in PLACEHOLDER_STATUSES:
        if documents:
            return [FieldIssue(path="data", message=f"a '{block.meta.status}' block must carry no documents")]
        return []

    issues: list[FieldIssue] = []
    if block.meta.status == "ready" and not documents:
        issues.append(FieldIssue(path="data.documents", message="a ready block needs at least one document"))
    if len(documents) > caps["documents"]:
        issues.append(FieldIssue(path="data.documents", message=f"at most {caps['documents']} documents may be listed"))
    seen: set[str] = set()
    for i, item in enumerate(documents):
        if item.docId in seen:
            issues.append(FieldIssue(path=f"data.documents.{i}.docId", message="listed twice"))
        seen.add(item.docId)
        stored = docs.get_document(item.docId)
        if stored is None:
            issues.append(FieldIssue(path=f"data.documents.{i}.docId", message="no stored document has this id"))
            continue
        if stored.status != "ready":
            issues.append(FieldIssue(path=f"data.documents.{i}.docId", message="the document is not ready to be cited"))
        if item.title != stored.title:
            issues.append(FieldIssue(path=f"data.documents.{i}.title", message="does not match the stored title"))
        if item.chunkCount != len(docs.chunks_for_document(item.docId)):
            issues.append(
                FieldIssue(path=f"data.documents.{i}.chunkCount", message="does not match the stored passage count")
            )
    return issues


def _caps(component: str) -> dict[str, int]:
    """The template's fences: the one source of the limits this validator enforces."""
    return CATALOG[component].fences.caps


LAYOUT_VERSION = 2
MIN_CHAT_WIDTH = 25
_LAYOUT = TypeAdapter(LayoutSpec)


def upgrade_layout(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Read a version 1 layout (no regions) as a version 2 one: every panel is one `main` region and every placement is
    in it. Anything else is returned as a plain copy, to be checked as it stands."""
    data = dict(raw)
    version = data.get("version")
    if type(version) is not int or version != 1:  # `True == 1` in Python: a boolean is not a version
        return data
    panels, placements = data.get("panels"), data.get("placements")
    if not isinstance(panels, list) or not isinstance(placements, list):
        return data  # not a shape that can be read: the schema check will say so
    data["version"] = LAYOUT_VERSION
    data["panels"] = [
        {**p, "direction": "rows", "regions": [{"id": "main", "size": 100}]} if isinstance(p, Mapping) else p
        for p in panels
    ]
    data["placements"] = [{**p, "region": "main"} if isinstance(p, Mapping) else p for p in placements]
    return data


def validate_layout(raw: LayoutSpec | Mapping[str, Any], known_block_ids: Collection[str]) -> LayoutSpec:
    """Return the validated layout, or raise ValidationFailed naming every violated field. Fail closed: a layout
    that fails is not sent, and the client keeps the layout it has. `known_block_ids` are the blocks the turn
    produced: a placement for any other block is a violation. A version 1 mapping is read as version 2."""
    data = upgrade_layout(raw.model_dump() if isinstance(raw, LayoutSpec) else raw)
    try:
        layout = _LAYOUT.validate_python(data)
    except ValidationError as exc:
        raise ValidationFailed("The layout does not match the wire schema.", _schema_issues(exc, None)) from exc

    issues: list[FieldIssue] = []
    if layout.version != LAYOUT_VERSION:
        issues.append(FieldIssue(path="version", message=f"only version {LAYOUT_VERSION} is supported"))
    if (layout.origin == "prebuilt") != (layout.mode == "basic"):
        issues.append(FieldIssue(path="mode", message="the prebuilt origin and the basic mode go together"))

    widths: dict[str, int] = {}
    regions: dict[str, dict[str, int]] = {}
    for i, panel in enumerate(layout.panels):
        if panel.id in widths:
            issues.append(FieldIssue(path=f"panels.{i}.id", message="panel ids must be unique"))
        widths[panel.id] = panel.width
        if not 0 <= panel.width <= 100:
            issues.append(FieldIssue(path=f"panels.{i}.width", message="a width is a whole number from 0 to 100"))
        sizes: dict[str, int] = {}
        for j, region in enumerate(panel.regions):
            where = f"panels.{i}.regions.{j}"
            if region.id in sizes:
                issues.append(FieldIssue(path=f"{where}.id", message="region ids must be unique within a panel"))
            sizes[region.id] = region.size
            if not 0 <= region.size <= 100:
                issues.append(FieldIssue(path=f"{where}.size", message="a size is a whole number from 0 to 100"))
        if not panel.regions:
            issues.append(FieldIssue(path=f"panels.{i}.regions", message="a panel has at least one region"))
        elif sum(r.size for r in panel.regions) != 100:
            issues.append(FieldIssue(path=f"panels.{i}.regions", message="region sizes must sum to 100"))
        regions.setdefault(panel.id, sizes)
    if sum(p.width for p in layout.panels) != 100:
        issues.append(FieldIssue(path="panels", message="widths must sum to 100"))
    if "chat" not in widths:
        issues.append(FieldIssue(path="panels", message="the chat panel is required"))
    elif widths["chat"] < MIN_CHAT_WIDTH:
        issues.append(FieldIssue(path="panels", message=f"the chat panel must be at least {MIN_CHAT_WIDTH} wide"))
    if "chat" in regions and "main" not in regions["chat"]:
        issues.append(FieldIssue(path="panels", message="the chat panel has a main region (the answer's own area)"))

    seen_blocks: set[str] = set()
    orders: set[tuple[str, str, int]] = set()
    for i, placement in enumerate(layout.placements):
        where = f"placements.{i}"
        if placement.blockId in seen_blocks:
            issues.append(FieldIssue(path=f"{where}.blockId", message="a block is placed once"))
        seen_blocks.add(placement.blockId)
        if placement.blockId not in known_block_ids:
            issues.append(FieldIssue(path=f"{where}.blockId", message="this turn produced no such block"))
        if placement.panel not in widths:
            issues.append(FieldIssue(path=f"{where}.panel", message="the panel is not in this layout"))
        elif widths[placement.panel] == 0:
            issues.append(FieldIssue(path=f"{where}.panel", message="a hidden panel (width 0) holds no blocks"))
        elif placement.region not in regions[placement.panel]:
            issues.append(FieldIssue(path=f"{where}.region", message="the panel has no such region"))
        elif regions[placement.panel][placement.region] == 0:
            issues.append(FieldIssue(path=f"{where}.region", message="a region of size 0 holds no blocks"))
        if placement.order < 0:
            issues.append(FieldIssue(path=f"{where}.order", message="must not be negative"))
        position = (placement.panel, placement.region, placement.order)
        if position in orders:
            issues.append(FieldIssue(path=f"{where}.order", message="orders are unique within a region"))
        orders.add(position)
    if issues:
        raise ValidationFailed("The layout failed validation.", issues)
    return layout


def _concept_map_issues(block: ConceptMap, docs: DocStore) -> list[FieldIssue]:
    caps = _caps("ConceptMap")
    data, status = block.data, block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data.steps or data.citations:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry no steps or citations")]
        return []

    issues: list[FieldIssue] = []
    if status == "ready" and len(data.steps) < caps["min_steps"]:
        issues.append(FieldIssue(path="data.steps", message=f"a path has at least {caps['min_steps']} steps"))
    if len(data.steps) > caps["steps"]:
        issues.append(FieldIssue(path="data.steps", message=f"a path has at most {caps['steps']} steps"))

    citations = {c.id: c for c in data.citations}
    if len(citations) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    referenced: set[str] = set()
    seen: set[str] = set()
    for i, step in enumerate(data.steps):
        where = f"data.steps.{i}"
        if i == 0:
            seen.add(_norm(step.source).lower())
        elif step.source != data.steps[i - 1].target:
            issues.append(FieldIssue(path=f"{where}.source", message="a step must start where the previous one ended"))
        if _norm(step.target).lower() in seen:
            issues.append(FieldIssue(path=f"{where}.target", message="a concept may not appear twice in a path"))
        seen.add(_norm(step.target).lower())
        for end, name in ((step.source, "source"), (step.target, "target")):
            if not MIN_LABEL_CHARS <= len(end.strip()) <= caps["label_chars"]:
                issues.append(
                    FieldIssue(
                        path=f"{where}.{name}",
                        message=f"a label is {MIN_LABEL_CHARS} to {caps['label_chars']} characters",
                    )
                )
        if not step.relation.strip() or len(step.relation) > caps["relation_chars"]:
            issues.append(
                FieldIssue(path=f"{where}.relation", message=f"a relation is 1 to {caps['relation_chars']} characters")
            )
        citation = citations.get(step.citationId)
        if citation is None:
            issues.append(FieldIssue(path=f"{where}.citationId", message=f"no citation with id {step.citationId!r}"))
            continue
        referenced.add(citation.id)
        for label in (step.source, step.target):
            if not label_in_quote(citation.quote, label):
                issues.append(
                    FieldIssue(
                        path=f"{where}.citationId", message=f"the cited quote does not contain the label {label!r}"
                    )
                )

    issues += _citation_issues(data.citations, referenced, docs)
    return issues


def _comparison_grid_issues(block: ComparisonGrid, docs: DocStore) -> list[FieldIssue]:
    caps = _caps("ComparisonGrid")
    data, status = block.data, block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data.dimensions or data.rows or data.citations:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry no rows, dimensions or citations")]
        return []

    issues: list[FieldIssue] = []
    if status == "ready" and (len(data.rows) < 2 or len(data.dimensions) < 2):
        issues.append(FieldIssue(path="data", message="a ready grid compares at least two documents on two entities"))
    if len(data.rows) > caps["documents"]:
        issues.append(FieldIssue(path="data.rows", message=f"at most {caps['documents']} documents may be compared"))
    if len(data.dimensions) > caps["entities"]:
        issues.append(
            FieldIssue(path="data.dimensions", message=f"at most {caps['entities']} entities may be compared")
        )

    labels: dict[str, str] = {}
    seen_labels: set[str] = set()
    for i, dimension in enumerate(data.dimensions):
        if dimension.id in labels:
            issues.append(FieldIssue(path=f"data.dimensions.{i}.id", message="dimension ids must be unique"))
        if _norm(dimension.label).lower() in seen_labels:
            issues.append(FieldIssue(path=f"data.dimensions.{i}.label", message="two columns may not share a label"))
        seen_labels.add(_norm(dimension.label).lower())
        labels[dimension.id] = dimension.label
        if not MIN_LABEL_CHARS <= len(dimension.label.strip()) <= caps["label_chars"]:
            issues.append(
                FieldIssue(
                    path=f"data.dimensions.{i}.label",
                    message=f"a label is {MIN_LABEL_CHARS} to {caps['label_chars']} characters",
                )
            )

    citations = {c.id: c for c in data.citations}
    if len(citations) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    rows_with: dict[str, int] = dict.fromkeys(labels, 0)
    referenced: set[str] = set()
    seen_docs: set[str] = set()
    for i, row in enumerate(data.rows):
        if row.docId in seen_docs:
            issues.append(FieldIssue(path=f"data.rows.{i}.docId", message="a document is listed twice"))
        seen_docs.add(row.docId)
        stored = docs.get_document(row.docId)
        if stored is None:
            issues.append(FieldIssue(path=f"data.rows.{i}.docId", message="no stored document has this id"))
        else:
            if stored.status != "ready":
                issues.append(FieldIssue(path=f"data.rows.{i}.docId", message="the document is not ready to be cited"))
            if row.docTitle != stored.title:
                issues.append(
                    FieldIssue(path=f"data.rows.{i}.docTitle", message="does not match the stored document's title")
                )
        if not row.cells:
            issues.append(FieldIssue(path=f"data.rows.{i}.cells", message="a row needs at least one cell"))
        in_row: set[str] = set()
        for j, cell in enumerate(row.cells):
            where = f"data.rows.{i}.cells.{j}"
            if cell.dimensionId not in labels:
                issues.append(
                    FieldIssue(path=f"{where}.dimensionId", message=f"no dimension with id {cell.dimensionId!r}")
                )
                continue
            if cell.dimensionId in in_row:
                issues.append(FieldIssue(path=f"{where}.dimensionId", message="a row has one cell per dimension"))
            else:
                rows_with[cell.dimensionId] += 1
            in_row.add(cell.dimensionId)
            citation = citations.get(cell.citationId)
            if citation is None:
                issues.append(
                    FieldIssue(path=f"{where}.citationId", message=f"no citation with id {cell.citationId!r}")
                )
                continue
            referenced.add(citation.id)
            if citation.docId != row.docId:
                issues.append(
                    FieldIssue(path=f"{where}.citationId", message="the cited chunk belongs to a different document")
                )
            if not label_in_quote(citation.quote, labels[cell.dimensionId]):
                issues.append(
                    FieldIssue(
                        path=f"{where}.citationId",
                        message=f"the cited quote does not contain the label {labels[cell.dimensionId]!r}",
                    )
                )

    for i, dimension in enumerate(data.dimensions):
        if rows_with.get(dimension.id, 0) < 2 and dimension.id in labels:
            issues.append(
                FieldIssue(path=f"data.dimensions.{i}", message="an entity must be evidenced in at least two documents")
            )

    issues += _citation_issues(data.citations, referenced, docs)
    return issues


def _graph_view_issues(block: GraphView, docs: DocStore) -> list[FieldIssue]:
    caps = _caps("GraphView")
    data, status = block.data, block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data.nodes or data.edges or data.citations:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry no nodes, edges or citations")]
        return []

    issues: list[FieldIssue] = []
    if status == "ready" and not data.edges:
        issues.append(FieldIssue(path="data.edges", message="a ready block needs at least one edge"))
    if len(data.nodes) > caps["nodes"]:
        issues.append(FieldIssue(path="data.nodes", message=f"at most {caps['nodes']} nodes may be drawn"))
    if len(data.edges) > caps["edges"]:
        issues.append(FieldIssue(path="data.edges", message=f"at most {caps['edges']} edges may be drawn"))

    labels: dict[str, str] = {}
    for i, node in enumerate(data.nodes):
        if node.id in labels:
            issues.append(FieldIssue(path=f"data.nodes.{i}.id", message="node ids must be unique"))
        labels[node.id] = node.label
        if not MIN_LABEL_CHARS <= len(node.label.strip()) <= caps["label_chars"]:
            issues.append(
                FieldIssue(
                    path=f"data.nodes.{i}.label",
                    message=f"a label is {MIN_LABEL_CHARS} to {caps['label_chars']} characters",
                )
            )

    citations = {c.id: c for c in data.citations}
    if len(citations) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    touched: set[str] = set()
    referenced: set[str] = set()
    for i, edge in enumerate(data.edges):
        if not edge.relation.strip() or len(edge.relation) > caps["relation_chars"]:
            issues.append(
                FieldIssue(
                    path=f"data.edges.{i}.relation", message=f"a relation is 1 to {caps['relation_chars']} characters"
                )
            )
        ends_ok = True
        for end, field_name in ((edge.source, "source"), (edge.target, "target")):
            if end not in labels:
                issues.append(FieldIssue(path=f"data.edges.{i}.{field_name}", message=f"no node with id {end!r}"))
                ends_ok = False
        if edge.source == edge.target:
            issues.append(FieldIssue(path=f"data.edges.{i}.target", message="an edge must join two different nodes"))
        touched.update((edge.source, edge.target))
        citation = citations.get(edge.citationId)
        if citation is None:
            issues.append(
                FieldIssue(path=f"data.edges.{i}.citationId", message=f"no citation with id {edge.citationId!r}")
            )
            continue
        referenced.add(citation.id)
        if ends_ok:
            for end in (edge.source, edge.target):
                if not label_in_quote(citation.quote, labels[end]):
                    issues.append(
                        FieldIssue(
                            path=f"data.edges.{i}.citationId",
                            message=f"the cited quote does not contain the label {labels[end]!r}",
                        )
                    )

    for i, node in enumerate(data.nodes):
        if node.id not in touched:
            issues.append(FieldIssue(path=f"data.nodes.{i}", message="a node must be an end of at least one edge"))

    issues += _citation_issues(data.citations, referenced, docs)
    return issues


def _traversal_view_issues(block: TraversalView, docs: DocStore, graph: GraphStore | None) -> list[FieldIssue]:
    """A traversal is a function of its seeds and the stores, so it is checked by running that function again: the
    validator re-derives the passages reached, the steps shown and how many were left out from the block's seeds, and the
    block must say exactly that. The seeds' `match` is taken as given (the question is not in the block)."""
    caps = _caps("TraversalView")
    data, status = block.data, block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data.seeds or data.nodes or data.steps or data.reached or data.citations or data.stepsLeftOut:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if graph is None:
        return [FieldIssue(path="data", message="a traversal can only be checked against the graph store")]

    issues: list[FieldIssue] = []
    if status == "ready" and not (data.seeds and data.steps and data.reached):
        issues.append(FieldIssue(path="data", message="a ready block needs a seed, a step and a passage"))
    for name, items, cap in (
        ("seeds", data.seeds, caps["seeds"]),
        ("nodes", data.nodes, caps["nodes"]),
        ("steps", data.steps, caps["steps"]),
        ("reached", data.reached, caps["reached"]),
    ):
        if len(items) > cap:
            issues.append(FieldIssue(path=f"data.{name}", message=f"at most {cap} may be shown"))

    labels: dict[str, str] = {}
    for i, node in enumerate(data.nodes):
        if node.id in labels:
            issues.append(FieldIssue(path=f"data.nodes.{i}.id", message="node ids must be unique"))
        labels[node.id] = node.label
        stored = graph.get_node(node.id)
        if stored is None:
            issues.append(FieldIssue(path=f"data.nodes.{i}.id", message="no stored node has this id"))
        elif stored.label != node.label:
            issues.append(FieldIssue(path=f"data.nodes.{i}.label", message="does not match the stored label"))
        if not MIN_LABEL_CHARS <= len(node.label.strip()) <= caps["label_chars"]:
            issues.append(
                FieldIssue(
                    path=f"data.nodes.{i}.label",
                    message=f"a label is {MIN_LABEL_CHARS} to {caps['label_chars']} characters",
                )
            )

    citations = {c.id: c for c in data.citations}
    if len(citations) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))
    seen_seeds: set[str] = set()
    for i, seed in enumerate(data.seeds):
        if seed.nodeId in seen_seeds:
            issues.append(FieldIssue(path=f"data.seeds.{i}.nodeId", message="a seed is listed once"))
        seen_seeds.add(seed.nodeId)
        if seed.nodeId not in labels:
            issues.append(FieldIssue(path=f"data.seeds.{i}.nodeId", message="a seed must be one of the nodes"))

    referenced: set[str] = set()
    for i, passage in enumerate(data.reached):
        if passage.citationId not in citations:
            issues.append(FieldIssue(path=f"data.reached.{i}.citationId", message="no citation has this id"))
        elif passage.citationId in referenced:
            issues.append(FieldIssue(path=f"data.reached.{i}.citationId", message="a passage is listed once"))
        referenced.add(passage.citationId)
    for i, step in enumerate(data.steps):
        if step.citationId not in referenced:
            issues.append(FieldIssue(path=f"data.steps.{i}.citationId", message="must cite a passage of this block"))
        if step.hop != 1:
            issues.append(FieldIssue(path=f"data.steps.{i}.hop", message="the graph signal expands one hop"))
        for end, field_name in ((step.source, "source"), (step.target, "target")):
            if end not in labels:
                issues.append(FieldIssue(path=f"data.steps.{i}.{field_name}", message=f"no node with id {end!r}"))

    issues += _citation_issues(data.citations, referenced, docs)
    if issues:
        return issues  # the re-derivation below reads the same fields: report the plain defects first

    held = [SeedNode(s.nodeId, labels[s.nodeId], s.match, seed_weight(s.match)) for s in data.seeds]
    try:
        derived = traverse(held, graph, docs, caps["reached"])
    except Exception:  # a store that cannot be read is a block that cannot be checked: refuse, never crash the turn
        return [FieldIssue(path="data", message="the traversal could not be re-derived from the stores")]
    if len(derived.seeds) != len(held):
        return [FieldIssue(path="data.seeds", message="a seed is not a node of the graph")]

    chunk_of = {cid: c.chunkId for cid, c in citations.items()}
    shown = [(p.rank, chunk_of[p.citationId], p.via, tuple(p.seedIds)) for p in data.reached]
    expected = [(r.rank, r.chunk_id, r.via, r.seed_ids) for r in derived.reached]
    if len(shown) != len(expected):
        issues.append(
            FieldIssue(
                path="data.reached.(count)",
                message=f"the graph signal returns {len(expected)} passages for these seeds",
            )
        )
    for i, (got, want) in enumerate(zip(shown, expected, strict=False)):
        for part, g, w in zip(("rank", "citationId", "via", "seedIds"), got, want, strict=True):
            if g != w:
                issues.append(
                    FieldIssue(path=f"data.reached.{i}.{part}", message="does not match what the graph signal returns")
                )

    wanted_steps, left_out = steps_for_display(derived, caps["steps"], caps["nodes"])
    got_steps = [(s.source, s.target, s.relation, chunk_of[s.citationId]) for s in data.steps]
    want_steps = [(s.edge.src, s.edge.dst, s.edge.relation, s.edge.chunk_id) for s in wanted_steps]
    if len(got_steps) != len(want_steps):
        issues.append(
            FieldIssue(
                path="data.steps.(count)", message=f"the traversal shows {len(want_steps)} steps for these seeds"
            )
        )
    for i, (got, want) in enumerate(zip(got_steps, want_steps, strict=False)):
        if got != want:
            issues.append(FieldIssue(path=f"data.steps.{i}", message="is not the edge the traversal followed here"))
    if data.stepsLeftOut != left_out:
        issues.append(FieldIssue(path="data.stepsLeftOut", message="does not match the steps the traversal left out"))

    want_nodes = {s.nodeId for s in data.seeds} | {e for s in wanted_steps for e in (s.edge.src, s.edge.dst)}
    if set(labels) != want_nodes:
        issues.append(
            FieldIssue(path="data.nodes.(set)", message="the nodes must be the seeds and the ends of the steps shown")
        )
    return issues


_MAX_DIFF_ISSUES = 8


def _differences(got: Any, want: Any, path: str, out: list[FieldIssue]) -> None:
    """The first places where a block's data differs from what the vault derives, as field issues (at most a few: the
    rest are the same defect repeated)."""
    if len(out) >= _MAX_DIFF_ISSUES:
        return
    if isinstance(want, dict) and isinstance(got, dict):
        for key in want:
            _differences(got.get(key), want[key], f"{path}.{key}", out)
    elif isinstance(want, list) and isinstance(got, list):
        if len(got) != len(want):
            out.append(FieldIssue(path=f"{path}.(count)", message=f"the vault derives {len(want)} here, not {len(got)}"))
        for i, (g, w) in enumerate(zip(got, want, strict=False)):
            _differences(g, w, f"{path}.{i}", out)
    elif got != want or type(got) is not type(want):
        out.append(FieldIssue(path=path, message="does not match what the vault derives"))


def _placeholder_empty(data: dict[str, Any], blank: dict[str, Any]) -> bool:
    return all(data.get(k) == v for k, v in blank.items())


_BLANK_PAGE: dict[str, Any] = {
    "kind": None,
    "aliases": [],
    "passages": 0,
    "documents": 0,
    "definitions": [],
    "links": [],
    "linksLeftOut": 0,
    "claims": [],
    "mentions": [],
    "mentionsLeftOut": 0,
    "citations": [],
    "mastery": None,
}


def _concept_page_issues(
    block: ConceptPage, docs: DocStore, vault: Vault | None, mastery: Mapping[str, MasteryScore] | None = None
) -> list[FieldIssue]:
    """A page is a function of its id and the vault, so it is checked by deriving it again: the block's data must equal the
    derived data exactly (every name, count, link, claim, backlink and citation)."""
    data, status = block.data.model_dump(), block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data["page"] != {"id": "", "label": ""} or not _placeholder_empty(data, _BLANK_PAGE):
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if vault is None:
        return [FieldIssue(path="data", message="a page can only be checked against the vault")]
    try:
        derived = derive_concept_page(vault, docs, block.data.page.id, mastery)
    except Exception:  # a store that cannot be read is a block that cannot be checked: refuse, never crash
        return [FieldIssue(path="data", message="the page could not be re-derived from the vault")]
    if derived is None:
        return [FieldIssue(path="data.page.id", message="the vault has no page with this id")]
    issues: list[FieldIssue] = []
    if status == "ready" and not derived["passages"]:
        return [FieldIssue(path="data.passages", message="a ready page needs at least one passage that mentions it")]
    referenced = {
        item["citationId"] for key in ("definitions", "mentions", "links", "claims") for item in data[key]
    }
    issues += _citation_issues(block.data.citations, referenced, docs)
    if issues:
        return issues  # plain citation defects first: the comparison below reads the same fields
    _differences(data, derived, "data", issues)
    return issues


_BLANK_GRAPH: dict[str, Any] = {"nodes": [], "edges": [], "nodesLeftOut": 0}


def _notes_graph_issues(
    block: NotesGraph, docs: DocStore, vault: Vault | None, mastery: Mapping[str, MasteryScore] | None = None
) -> list[FieldIssue]:
    """A notes graph is a function of its focus, its query and the vault, so it is checked by deriving it again."""
    data, status = block.data.model_dump(), block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if not _placeholder_empty(data, _BLANK_GRAPH) or data["focusId"] is not None:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if vault is None:
        return [FieldIssue(path="data", message="a notes graph can only be checked against the vault")]
    try:
        derived = derive_notes_graph(vault, docs, block.data.focusId, block.data.query, mastery)
    except Exception:
        return [FieldIssue(path="data", message="the graph could not be re-derived from the vault")]
    if derived is None:
        return [FieldIssue(path="data.focusId", message="the vault has no page with this id")]
    issues: list[FieldIssue] = []
    if status == "ready" and not data["nodes"]:
        issues.append(FieldIssue(path="data.nodes", message="a ready graph needs at least one page"))
    _differences(data, derived, "data", issues)
    return issues


def _verified_lab_issues(block: VerifiedLab, docs: DocStore, labs: LabStore | None) -> list[FieldIssue]:
    """THE DELIVERY GATE (D-36, hard constraint 3). A lab is delivered only if the stored, verified record of `labId` exists and the block
    equals what that record, its contract and the stored passage derive: the source byte for byte, its hash, the template version (the
    one the host holds), the parameters, the counts and the citation. A forged block, a changed byte, a stale template version, an
    unknown or unverified lab, a store that cannot be read, and a `partial` block are refused (fail closed). Placeholders carry nothing."""
    data, status = block.data.model_dump(), block.meta.status
    if status != "ready":
        if status == "partial":
            return [FieldIssue(path="meta.status", message="a lab is delivered whole: partial is not allowed")]
        return [] if data == BLANK_LAB_DATA else [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
    if labs is None:
        return [FieldIssue(path="data", message="a lab can only be checked against the verified lab store")]
    try:
        record = labs.get(block.data.labId)
        if record is None:
            return [FieldIssue(path="data.labId", message="no verified lab has this id")]
        make = CONTRACTS.get(record.contract_id)
        if make is None:
            return [FieldIssue(path="data.contractId", message="the lab's contract is unknown")]
        contract = make()
        if record.contract_sha256 != contract_sha256(contract):
            return [FieldIssue(path="data.contractId", message="the lab was verified for another version of its contract")]
        again = check_source(record.source, [p.name for p in contract.parameters])
        if not again.ok:  # the stored source is checked again on delivery, not trusted because it was stored
            return [FieldIssue(path="data.source", message="the stored source no longer passes the checker")]
        citation = find_source(docs, contract)
        if citation is None:
            return [FieldIssue(path="data.citations", message="no stored passage states this lab's formula")]
        derived = derive_lab_data(record, contract, citation)
    except Exception:  # an unreadable store is a lab that cannot be checked: refuse, never crash
        return [FieldIssue(path="data", message="the lab could not be re-derived from the verified record")]
    issues: list[FieldIssue] = []
    if record.template_version != TEMPLATE_VERSION:
        issues.append(FieldIssue(path="data.templateVersion", message="the lab was verified for another template version"))
    if len(record.source) > 4000:
        issues.append(FieldIssue(path="data.source", message="the source is longer than the fence allows"))
    _differences(data, derived, "data", issues)
    return issues


def _quiz_card_issues(
    block: QuizCard, docs: DocStore, vault: Vault | None, mastery: Mapping[str, MasteryScore] | None = None
) -> list[FieldIssue]:
    """A quiz is a function of its focus, the vault, the stored passages and the learner's mastery, so it is checked by deriving it
    again: every sentence, blank, option and its order, and the count of claims passed over must equal the derived ones. The block
    carries no answer (the schema forbids any extra field), so a block that names one is refused before this runs."""
    data, status = block.data.model_dump(), block.meta.status
    if status in {"loading", "error"} or (status == "empty" and vault is None):
        if data != {"focusId": None, "items": [], "skipped": 0}:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if vault is None:
        return [FieldIssue(path="data", message="a quiz can only be checked against the vault")]
    try:
        derived = derive_quiz(vault, docs, block.data.focusId, mastery)
    except Exception:  # a store that cannot be read is a block that cannot be checked: refuse, never crash
        return [FieldIssue(path="data", message="the quiz could not be re-derived from the vault")]
    if derived is None:
        return [FieldIssue(path="data.focusId", message="the vault has no page with this id")]
    issues: list[FieldIssue] = []
    if status == "ready" and not data["items"]:
        issues.append(FieldIssue(path="data.items", message="a ready quiz needs at least one question"))
    if status == "empty" and derived["items"]:
        issues.append(FieldIssue(path="data.items", message="the vault can make questions here: this block must not be empty"))
    _differences(data, derived, "data", issues)
    return issues


def _study_set_issues(
    block: StudySet, docs: DocStore, vault: Vault | None, mastery: Mapping[str, MasteryScore] | None = None
) -> list[FieldIssue]:
    """A study set is a function of its kind, its focus, the vault, the stored passages and the learner's mastery, so it is checked by
    deriving it again: every prompt, hint, note, citation, the summary and the count passed over must equal the derived ones. That
    includes the withholding: a prompt or hint that held a note's sentence would not equal what is derived."""
    data, status = block.data.model_dump(), block.meta.status
    blank = {"focusId": None, "items": [], "summary": None, "citations": [], "skipped": 0}
    if status in {"loading", "error"} or (status == "empty" and vault is None):
        if any(data.get(k) != v for k, v in blank.items()):
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if vault is None:
        return [FieldIssue(path="data", message="a study set can only be checked against the vault")]
    try:
        derived = derive_study_set(vault, docs, block.data.kind, block.data.focusId, mastery)
    except Exception:  # a store that cannot be read is a block that cannot be checked: refuse, never crash
        return [FieldIssue(path="data", message="the study set could not be re-derived from the vault")]
    if derived is None:
        return [FieldIssue(path="data.focusId", message="the vault has no page with this id")]
    issues: list[FieldIssue] = []
    if status == "ready" and not data["items"]:
        issues.append(FieldIssue(path="data.items", message="a ready study set needs at least one item"))
    if status == "empty" and derived["items"]:
        issues.append(FieldIssue(path="data.items", message="the vault can make items here: this block must not be empty"))
    _differences(data, derived, "data", issues)
    return issues


def _study_plan_issues(
    block: StudyPlan,
    vault: Vault | None,
    mastery: Mapping[str, MasteryScore] | None,
    last_rated: Mapping[str, datetime] | None,
) -> list[FieldIssue]:
    """A review schedule is a function of the vault, the learner's mastery and the dates of their ratings (and the day it is for, which
    the block states), so it is checked by deriving it again: every item, its due word and day count, and the totals must equal the
    derived ones."""
    data, status = block.data.model_dump(), block.meta.status
    if status in {"loading", "error"} or (status == "empty" and vault is None):
        if data["items"] or data["ratedPages"] or data["leftOut"]:
            return [FieldIssue(path="data", message=f"a '{status}' block must carry nothing")]
        return []
    if vault is None:
        return [FieldIssue(path="data", message="a review schedule can only be checked against the vault")]
    try:
        day = datetime.fromisoformat(data["asOf"]).replace(tzinfo=UTC)
    except ValueError:
        return [FieldIssue(path="data.asOf", message="must be a date, YYYY-MM-DD")]
    derived = derive_study_plan(vault, mastery, last_rated, day)
    issues: list[FieldIssue] = []
    if status == "ready" and not data["items"]:
        issues.append(FieldIssue(path="data.items", message="a ready schedule needs at least one page"))
    if status == "empty" and derived["items"]:
        issues.append(FieldIssue(path="data.items", message="pages are rated: this block must not be empty"))
    _differences(data, derived, "data", issues)
    return issues


def _cited_summary_issues(block: CitedSummary, docs: DocStore) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    status = block.meta.status

    data = block.data
    if status in PLACEHOLDER_STATUSES:
        if data.segments or data.citations:
            issues.append(
                FieldIssue(
                    path="data",
                    message=f"a '{status}' block must carry no segments or citations",
                )
            )
        return issues

    # "partial" and "ready": whatever is present must be grounded, within the template's fences.
    caps = _caps("CitedSummary")
    if len(data.segments) > caps["segments"]:
        issues.append(FieldIssue(path="data.segments", message=f"at most {caps['segments']} segments may be shown"))
    if len(data.citations) > caps["citations"]:
        issues.append(FieldIssue(path="data.citations", message=f"at most {caps['citations']} citations may be shown"))
    by_id = {c.id: c for c in data.citations}
    if len(by_id) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    if status == "ready" and not data.segments:
        issues.append(FieldIssue(path="data.segments", message="a ready block needs at least one segment"))

    referenced: set[str] = set()
    for i, segment in enumerate(data.segments):
        if not segment.citationIds:
            issues.append(FieldIssue(path=f"data.segments.{i}.citationIds", message="a segment must cite evidence"))
        seen_here: set[str] = set()
        for j, cid in enumerate(segment.citationIds):
            referenced.add(cid)
            if cid in seen_here:
                issues.append(
                    FieldIssue(
                        path=f"data.segments.{i}.citationIds.{j}",
                        message=f"{cid!r} is cited twice in this segment",
                    )
                )
            seen_here.add(cid)
            if cid not in by_id:
                issues.append(
                    FieldIssue(
                        path=f"data.segments.{i}.citationIds.{j}",
                        message=f"no citation with id {cid!r} in this block",
                    )
                )

    issues += _citation_issues(data.citations, referenced, docs)
    return issues


def _writing_draft_issues(block: WritingDraft, docs: DocStore) -> list[FieldIssue]:
    """A draft's rules (P5 S1, D-42): placeholders carry nothing; otherwise every passage stands on a citation in the block, every
    citation passes the rules every citation obeys, and the bibliography is exactly the references the stored records of the cited
    documents give (re-derived here, so a reference the store does not support is refused)."""
    issues: list[FieldIssue] = []
    data = block.data
    status = block.meta.status
    if status in PLACEHOLDER_STATUSES:
        if data.title or data.sections or data.citations or data.bibliography:
            issues.append(FieldIssue(path="data", message=f"a '{status}' block must carry no draft"))
        return issues

    caps = _caps("WritingDraft")
    if not data.title.strip():
        issues.append(FieldIssue(path="data.title", message="a draft needs a title"))
    elif len(data.title) > caps["title_chars"]:
        issues.append(FieldIssue(path="data.title", message=f"at most {caps['title_chars']} characters"))
    if len(data.sections) > caps["sections"]:
        issues.append(FieldIssue(path="data.sections", message=f"at most {caps['sections']} sections may be shown"))
    if status == "ready" and not data.sections:
        issues.append(FieldIssue(path="data.sections", message="a ready draft needs at least one section"))
    if len(data.citations) > caps["citations"]:
        issues.append(FieldIssue(path="data.citations", message=f"at most {caps['citations']} citations may be shown"))
    by_id = {c.id: c for c in data.citations}
    if len(by_id) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    referenced: set[str] = set()
    headings: set[str] = set()
    for i, section in enumerate(data.sections):
        heading = section.heading.strip()
        if not heading:
            issues.append(FieldIssue(path=f"data.sections.{i}.heading", message="a section needs a heading"))
        elif len(heading) > caps["heading_chars"]:
            issues.append(
                FieldIssue(path=f"data.sections.{i}.heading", message=f"at most {caps['heading_chars']} characters")
            )
        elif heading.lower() in headings:
            issues.append(FieldIssue(path=f"data.sections.{i}.heading", message="section headings must be unique"))
        headings.add(heading.lower())
        if not section.segments:
            issues.append(FieldIssue(path=f"data.sections.{i}.segments", message="a section needs at least one passage"))
        elif len(section.segments) > caps["segments"]:
            issues.append(
                FieldIssue(
                    path=f"data.sections.{i}.segments", message=f"at most {caps['segments']} passages per section"
                )
            )
        for j, segment in enumerate(section.segments):
            where = f"data.sections.{i}.segments.{j}"
            if not segment.text.strip():
                issues.append(FieldIssue(path=f"{where}.text", message="a passage needs text"))
            if not segment.citationIds:
                issues.append(FieldIssue(path=f"{where}.citationIds", message="a passage must cite evidence"))
            seen_here: set[str] = set()
            for k, cid in enumerate(segment.citationIds):
                referenced.add(cid)
                if cid in seen_here:
                    issues.append(
                        FieldIssue(path=f"{where}.citationIds.{k}", message=f"{cid!r} is cited twice in this passage")
                    )
                seen_here.add(cid)
                if cid not in by_id:
                    issues.append(
                        FieldIssue(path=f"{where}.citationIds.{k}", message=f"no citation with id {cid!r} in this block")
                    )

    issues += _citation_issues(data.citations, referenced, docs)

    # the bibliography: one derived reference per cited document, nothing else
    if len(data.bibliography) > caps["bibliography"]:
        issues.append(
            FieldIssue(path="data.bibliography", message=f"at most {caps['bibliography']} references may be shown")
        )
    cited_docs = {c.docId for c in data.citations}
    listed: set[str] = set()
    for i, entry in enumerate(data.bibliography):
        if entry.docId in listed:
            issues.append(FieldIssue(path=f"data.bibliography.{i}.docId", message="a document is listed once"))
        listed.add(entry.docId)
        document = docs.get_document(entry.docId)
        if document is None:
            issues.append(FieldIssue(path=f"data.bibliography.{i}.docId", message="no stored document has this id"))
            continue
        if entry.docId not in cited_docs:
            issues.append(FieldIssue(path=f"data.bibliography.{i}.docId", message="no citation in this draft is from this document"))
        want = reference_for(document)
        for style in ("apa", "ieee", "bibtex"):
            if getattr(entry, style) != want[style]:
                issues.append(
                    FieldIssue(
                        path=f"data.bibliography.{i}.{style}", message="does not match the reference the stored record gives"
                    )
                )
    for missing in sorted(cited_docs - listed):
        issues.append(FieldIssue(path="data.bibliography", message=f"a cited document has no reference ({missing})"))
    return issues


def _citation_issues(citations: list[Citation], referenced: set[str], docs: DocStore) -> list[FieldIssue]:
    """The rules every citation obeys, whichever component carries it: a stored chunk under the document it names,
    matching title and page, a verbatim quote long enough to be evidence, and cited by something in the block."""
    issues: list[FieldIssue] = []
    chunks = docs.get_chunks([c.chunkId for c in citations])
    titles: dict[str, str | None] = {}
    for i, citation in enumerate(citations):
        if citation.id not in referenced:
            issues.append(FieldIssue(path=f"data.citations.{i}", message="nothing in this block cites this citation"))
        stored = chunks.get(citation.chunkId)
        if stored is None:
            issues.append(FieldIssue(path=f"data.citations.{i}.chunkId", message="no stored chunk has this id"))
            continue
        if stored.doc_id != citation.docId:
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.docId",
                    message="the chunk belongs to a different document",
                )
            )
        else:
            if citation.docId not in titles:
                document = docs.get_document(citation.docId)
                titles[citation.docId] = document.title if document else None
            if citation.docTitle != titles[citation.docId]:
                issues.append(
                    FieldIssue(
                        path=f"data.citations.{i}.docTitle",
                        message="does not match the stored document's title",
                    )
                )
        if citation.page != stored.page:
            issues.append(FieldIssue(path=f"data.citations.{i}.page", message="does not match the cited chunk's page"))
        quote, chunk_text = _norm(citation.quote), _norm(stored.text)
        if not quote:
            issues.append(FieldIssue(path=f"data.citations.{i}.quote", message="a quote is required"))
        elif quote not in chunk_text:
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.quote",
                    message="the quote is not a verbatim span of the cited chunk",
                )
            )
        elif len(quote) < min(MIN_QUOTE_CHARS, len(chunk_text)):
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.quote",
                    message=f"the quote is too short to be evidence (under {MIN_QUOTE_CHARS} characters)",
                )
            )
    return issues
