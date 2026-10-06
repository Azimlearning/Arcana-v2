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
from typing import Any

from pydantic import TypeAdapter, ValidationError

from api.core.errors import ValidationFailed
from api.genui.catalog import CATALOG
from api.genui.generated import (
    Citation,
    CitedSummary,
    ComparisonGrid,
    ConceptMap,
    FieldIssue,
    GraphView,
    LayoutSpec,
    SourceList,
    UIBlock,
)
from api.genui.text import MIN_LABEL_CHARS, MIN_QUOTE_CHARS, label_in_quote
from api.genui.text import normalise as _norm
from api.stores.doc_store import DocStore

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


def validate_block(raw: Mapping[str, Any], docs: DocStore) -> UIBlock:
    """Return the validated block, or raise ValidationFailed naming every violated field."""
    tag = raw.get("type") if isinstance(raw.get("type"), str) else None
    try:
        block = _UI_BLOCK.validate_python(dict(raw))
    except ValidationError as exc:
        raise ValidationFailed("The block does not match the wire schema.", _schema_issues(exc, tag)) from exc

    issues = _content_issues(block, docs)
    if issues:
        raise ValidationFailed("The block failed content validation.", issues)
    return block


def _content_issues(block: UIBlock, docs: DocStore) -> list[FieldIssue]:
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


LAYOUT_VERSION = 1
MIN_CHAT_WIDTH = 25
_LAYOUT = TypeAdapter(LayoutSpec)


def validate_layout(raw: LayoutSpec | Mapping[str, Any], known_block_ids: Collection[str] | None = None) -> LayoutSpec:
    """Return the validated layout, or raise ValidationFailed naming every violated field. Fail closed: a layout
    that fails is not sent, and the client keeps the layout it has. `known_block_ids`, when given, are the blocks the
    turn produced: a placement for any other block is a violation."""
    data = raw.model_dump() if isinstance(raw, LayoutSpec) else dict(raw)
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
    for i, panel in enumerate(layout.panels):
        if panel.id in widths:
            issues.append(FieldIssue(path=f"panels.{i}.id", message="panel ids must be unique"))
        widths[panel.id] = panel.width
        if not 0 <= panel.width <= 100:
            issues.append(FieldIssue(path=f"panels.{i}.width", message="a width is a whole number from 0 to 100"))
    if sum(p.width for p in layout.panels) != 100:
        issues.append(FieldIssue(path="panels", message="widths must sum to 100"))
    if "chat" not in widths:
        issues.append(FieldIssue(path="panels", message="the chat panel is required"))
    elif widths["chat"] < MIN_CHAT_WIDTH:
        issues.append(FieldIssue(path="panels", message=f"the chat panel must be at least {MIN_CHAT_WIDTH} wide"))

    seen_blocks: set[str] = set()
    orders: set[tuple[str, int]] = set()
    for i, placement in enumerate(layout.placements):
        where = f"placements.{i}"
        if placement.blockId in seen_blocks:
            issues.append(FieldIssue(path=f"{where}.blockId", message="a block is placed once"))
        seen_blocks.add(placement.blockId)
        if known_block_ids is not None and placement.blockId not in known_block_ids:
            issues.append(FieldIssue(path=f"{where}.blockId", message="this turn produced no such block"))
        if placement.panel not in widths:
            issues.append(FieldIssue(path=f"{where}.panel", message="the panel is not in this layout"))
        elif widths[placement.panel] == 0:
            issues.append(FieldIssue(path=f"{where}.panel", message="a hidden panel (width 0) holds no blocks"))
        if placement.order < 0:
            issues.append(FieldIssue(path=f"{where}.order", message="must not be negative"))
        if (placement.panel, placement.order) in orders:
            issues.append(FieldIssue(path=f"{where}.order", message="orders are unique within a panel"))
        orders.add((placement.panel, placement.order))
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
