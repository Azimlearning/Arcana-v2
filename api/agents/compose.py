"""The Composer, P0 stub: the only place a block is made, and the terminal step of every turn.

It always produces a block, even when an agent failed or a hop was refused: a failure becomes an
error-state block carrying its reason, no evidence becomes an empty block. Whatever it builds must pass
validate_block; if the validator rejects it, the Composer replaces it with an error-state block carrying
the violation's field paths (fail closed). Choosing among several components and a layout arrives in P2;
the contract (agents return payloads, only the Composer returns blocks) is fixed now.

This module is the ONLY importer of api.genui.builders (a test enforces it): no other code can
construct a block, so nothing reaches the wire that the Composer did not build and validate.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langgraph.runtime import Runtime

from api.agents.framework import AgentResult
from api.agents.state import TurnContext, TurnState
from api.core.errors import ValidationFailed
from api.core.logging import get_logger
from api.genui.builders import BUILDERS, cited_summary
from api.genui.catalog import (
    CATALOG,
    MAX_SOURCES,
    ComponentRecord,
    ComposerEvidence,
    Composition,
    Spec,
    alignment_grid,
    concept_path,
    graph_edges,
)
from api.genui.generated import ErrorEnvelope, UIBlock
from api.genui.layout import compose_layout
from api.genui.validate import validate_block, validate_layout
from api.stores.doc_store import Document

log = get_logger(__name__)
_KEBAB = re.compile(r"(?<!^)(?=[A-Z])")

# Agents whose failure ends the turn. Their errors become the error block. The Fact Checker is handled
# separately in compose_block: it gates what may be shown, rather than producing the answer.
DECISIVE = ("orchestrator", "research")


def loading_block(ctx: TurnContext) -> UIBlock:
    """The placeholder streamed at once; the turn's final block replaces it (same id)."""
    return validate_block(cited_summary(ctx.block_id, "loading"), ctx.docs)


def error_block(ctx: TurnContext, error: ErrorEnvelope) -> UIBlock:
    """An error-state block for this turn, carrying `error`. Used whenever a turn cannot finish."""
    return validate_block(cited_summary(ctx.block_id, "error", error=error), ctx.docs)


def _failure(ctx: TurnContext) -> ErrorEnvelope | None:
    for name in DECISIVE:
        result: AgentResult | None = ctx.results.get(name)
        if result is not None and result.status in ("failed", "refused"):
            return result.error or ErrorEnvelope(
                code="internal", message="An agent could not finish.", issues=[], retryable=False
            )
    return None


def _gate(ctx: TurnContext) -> tuple[dict[str, Any] | None, ErrorEnvelope | None]:
    """The answer the Composer may show, or the error that replaces it. Fail closed: an agent that failed, a
    missing Research result, or (with a checker on the roster) a checker that did not run or did not pass,
    is an error, never the unchecked answer."""
    failure = _failure(ctx)
    if failure is not None:
        return None, failure
    research = ctx.results.get("research")
    if research is None:
        return None, ErrorEnvelope(code="internal", message="No agent produced an answer.", issues=[], retryable=False)
    answer = research.payload.get("answer")
    if ctx.roster.get("fact_checker"):
        checker = ctx.results.get("fact_checker")
        if checker is None or checker.status in ("failed", "refused"):
            return None, (
                checker.error
                if checker and checker.error
                else ErrorEnvelope(
                    code="internal",
                    message="The answer could not be checked.",
                    issues=[],
                    retryable=False,
                )
            )
        answer = checker.payload.get("answer")
    return (answer.data if answer is not None else None), None


def _documents(ctx: TurnContext) -> tuple[tuple[Document, ...], dict[str, int]]:
    """The corpus listing with each document's passage count. Every turn must end at the Composer (constraint 4),
    so a store that cannot list is treated as an empty corpus here, and any component that needs documents is
    simply not admitted."""
    try:
        documents = tuple(ctx.docs.list_documents())
        listed = [d for d in documents if d.status == "ready"][:MAX_SOURCES]  # counts only for what can be shown
        return documents, {d.id: len(ctx.docs.chunks_for_document(d.id)) for d in listed}
    except Exception as exc:
        log.warning("document_listing_failed", error=type(exc).__name__)
        return (), {}


def _evidence(ctx: TurnContext, answer: dict[str, Any] | None) -> ComposerEvidence:
    graph = ctx.results.get("graph")
    documents, chunk_counts = _documents(ctx)
    return ComposerEvidence(
        answer=answer,
        graph=graph.payload if graph is not None and graph.status in ("ok", "partial") else None,
        documents=documents,
        intent=ctx.intent,
        chunk_counts=chunk_counts,
    )


def _block_id(spec: Spec, ctx: TurnContext) -> str:
    """The id of the block a spec produces: the turn's id for the answer (it replaces the loading block), a derived
    id for every other component so it never replaces anything. One place, so records and builders agree."""
    return ctx.block_id if spec.terminal else f"{ctx.block_id}-{_KEBAB.sub('-', spec.name).lower()}"


def _graph_data(evidence: ComposerEvidence) -> dict[str, Any]:
    """GraphViewData from the Graph agent's drawable edges: one citation per distinct (chunk, quote), nodes only
    where an edge ends, in first-seen order, so the same payload always gives the same block."""
    graph = evidence.graph or {}
    labels: dict[str, str] = graph.get("labels") or {}
    citations: dict[tuple[str, str], dict[str, Any]] = {}
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    for edge in graph_edges(evidence.graph):
        key = (edge["chunk_id"], edge["quote"])
        if key not in citations:
            citations[key] = {
                "id": f"c{len(citations) + 1}",
                "chunkId": edge["chunk_id"],
                "docId": edge["doc_id"],
                "docTitle": edge["doc_title"],
                "page": edge["page"],
                "quote": edge["quote"],
            }
        for end in (edge["src"], edge["dst"]):
            nodes.setdefault(end, {"id": end, "label": labels[end]})
        edges.append(
            {
                "source": edge["src"],
                "target": edge["dst"],
                "relation": edge["relation"],
                "citationId": citations[key]["id"],
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges, "citations": list(citations.values())}


def _grid_data(evidence: ComposerEvidence) -> dict[str, Any]:
    """ComparisonGridData from the settled alignment: one citation per distinct (chunk, quote), a cell per
    (document, entity) with evidence and none where there is none."""
    documents, dimensions, cells = alignment_grid(evidence.graph)
    citations: dict[tuple[str, str], dict[str, Any]] = {}
    by_row: dict[str, list[dict[str, str]]] = {d["doc_id"]: [] for d in documents}
    for cell in cells:
        key = (cell["chunk_id"], cell["quote"])
        if key not in citations:
            citations[key] = {
                "id": f"c{len(citations) + 1}",
                "chunkId": cell["chunk_id"],
                "docId": cell["doc_id"],
                "docTitle": cell["doc_title"],
                "page": cell["page"],
                "quote": cell["quote"],
            }
        by_row[cell["doc_id"]].append({"dimensionId": cell["dimension_id"], "citationId": citations[key]["id"]})
    return {
        "dimensions": [{"id": d["id"], "label": d["label"]} for d in dimensions],
        "rows": [{"docId": d["doc_id"], "docTitle": d["title"], "cells": by_row[d["doc_id"]]} for d in documents],
        "citations": list(citations.values()),
    }


def _concept_data(evidence: ComposerEvidence) -> dict[str, Any]:
    """ConceptMapData from the Graph agent's path: one citation per distinct (chunk, quote), steps in path order."""
    steps, _ = concept_path(evidence.graph)
    citations: dict[tuple[str, str], dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for step in steps:
        key = (step["chunk_id"], step["quote"])
        if key not in citations:
            citations[key] = {
                "id": f"c{len(citations) + 1}",
                "chunkId": step["chunk_id"],
                "docId": step["doc_id"],
                "docTitle": step["doc_title"],
                "page": step["page"],
                "quote": step["quote"],
            }
        out.append(
            {
                "source": step["source"],
                "target": step["target"],
                "relation": step["relation"],
                "reversed": step["reversed"],
                "citationId": citations[key]["id"],
            }
        )
    return {"steps": out, "citations": list(citations.values())}


def _raw_cited_summary(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    builder = BUILDERS[spec.name]
    if empty:
        return builder(_block_id(spec, ctx), "empty")
    return builder(_block_id(spec, ctx), "ready", data=evidence.answer)


def _raw_source_list(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    listed = [
        {"docId": d.id, "title": d.title, "chunkCount": evidence.chunk_counts.get(d.id, 0)}
        for d in evidence.documents
        if d.status == "ready"
    ][: spec.caps["documents"]]
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", documents=listed)


def _raw_graph_view(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_graph_data(evidence))


def _raw_comparison_grid(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_grid_data(evidence))


def _raw_concept_map(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_concept_data(evidence))


RawBuilder = Callable[[Spec, TurnContext, ComposerEvidence, bool], dict[str, Any]]
_RAW: dict[str, RawBuilder] = {
    "CitedSummary": _raw_cited_summary,
    "SourceList": _raw_source_list,
    "GraphView": _raw_graph_view,
    "ComparisonGrid": _raw_comparison_grid,
    "ConceptMap": _raw_concept_map,
}
"""How each catalog component's raw block is made from the evidence: one entry per component (the recipe in
catalog.md, "How to add a component"). The completeness test keeps this, the catalog and the builders in step."""


def _raw(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, *, empty: bool) -> dict[str, Any]:
    """The unvalidated block for one admitted (or, for the terminal component, empty) spec."""
    return _RAW[spec.name](spec, ctx, evidence, empty)


def _compose_blocks(ctx: TurnContext) -> Composition:
    """Walk the catalog and build every block whose precondition the evidence satisfies. Never raises and never
    returns nothing: the terminal component is always present, as an error or empty block if it must be."""
    answer, failure = _gate(ctx)
    if failure is not None:
        record = ComponentRecord("CitedSummary", "error", (failure.code,), ctx.block_id)
        return Composition((error_block(ctx, failure),), (record,))

    evidence = _evidence(ctx, answer)
    blocks: list[UIBlock] = []
    records: list[ComponentRecord] = []
    for spec in CATALOG.values():
        result = spec.check(evidence)
        if not result.satisfied and not spec.terminal:
            records.append(ComponentRecord(spec.name, "refused", result.reasons))
            continue
        empty = not result.satisfied
        try:
            block = validate_block(_raw(spec, ctx, evidence, empty=empty), ctx.docs)
        except ValidationFailed as exc:
            log.warning("composed_block_rejected", component=spec.name, issues=[i.path for i in exc.issues])
            if spec.terminal:
                blocks.insert(0, error_block(ctx, exc.to_envelope()))
            records.append(ComponentRecord(spec.name, "error", tuple(i.path for i in exc.issues), _block_id(spec, ctx)))
            continue
        blocks.append(block)
        records.append(ComponentRecord(spec.name, "empty" if empty else "admitted", result.reasons, block.id))
    return Composition(tuple(blocks), tuple(records))


def compose(ctx: TurnContext) -> Composition:
    """The turn's blocks (see `_compose_blocks`) and, last, the adaptive layout for them. The layout is validated
    against the blocks actually produced; if it is invalid it is left out and the reason recorded, and the turn is
    unaffected: layout never fails a turn."""
    composition = _compose_blocks(ctx)
    components = {r.block_id: r.component for r in composition.records if r.block_id}
    admitted = [(b.id, components.get(b.id, "")) for b in composition.blocks]
    try:
        layout = validate_layout(compose_layout(admitted, ctx.intent), {b.id for b in composition.blocks})
    except ValidationFailed as exc:
        log.warning("layout_rejected", issues=[i.path for i in exc.issues])
        return replace(composition, layout_failure=tuple(i.path for i in exc.issues))
    except Exception as exc:  # a bug in layout must not end the turn either
        log.error("layout_failed", error=type(exc).__name__)
        return replace(composition, layout_failure=("internal",))
    return replace(composition, layout=layout)


def compose_block(ctx: TurnContext) -> UIBlock:
    """The terminal block alone (the P0/P1 entry point, kept for callers that only need the answer)."""
    return compose(ctx).primary


def compose_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    composition = compose(runtime.context)
    return {"block": composition.primary, "composition": composition}
