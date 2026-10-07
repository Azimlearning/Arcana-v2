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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import Any

from langgraph.runtime import Runtime

from api.agents.framework import AgentResult, route_to_agent
from api.agents.state import TurnContext, TurnState
from api.core.errors import NotFound, PatternRefused, ValidationFailed
from api.core.logging import get_logger
from api.genui.builders import BUILDERS, cited_summary
from api.genui.catalog import (
    CATALOG,
    ComponentRecord,
    ComposerEvidence,
    Composition,
    Spec,
    ViewComponent,
    alignment_grid,
    cap,
    component_params,
    concept_path,
    graph_edges,
)
from api.genui.evidence import best_excerpt, excerpt_containing
from api.genui.generated import ErrorEnvelope, FieldIssue, LayoutSpec, SavedPattern, UIBlock
from api.genui.layout import compose_layout, compose_notes_layout, prebuilt_layout
from api.genui.patterns import params_of, validate_params
from api.genui.templates import (
    SUITES,
    TemplateRefused,
    fixture_graph,
    fixture_store,
    register_template,
)
from api.genui.validate import validate_block, validate_layout
from api.labs.contract import CONTRACTS
from api.labs.evidence import find_source
from api.labs.generator import LabGenerator
from api.labs.store import LabStore
from api.labs.verifier import LabToolError, VerificationFailed, verify
from api.learner.mastery import MasteryScore
from api.learner.store import LearnerStore
from api.stores.doc_store import DocStore, Document
from api.vault.quiz import derive_quiz
from api.vault.types import Vault
from api.vault.view import derive_concept_page, derive_notes_graph

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
        listed = [d for d in documents if d.status == "ready"][
            : cap("SourceList", "documents")
        ]  # counts only for what can be shown
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


def _source_items(documents: Iterable[Document], chunk_counts: Mapping[str, int], cap: int) -> list[dict[str, Any]]:
    """The ready documents as SourceList items, at most `cap`, with their stored titles and passage counts."""
    return [
        {"docId": d.id, "title": d.title, "chunkCount": chunk_counts.get(d.id, 0)}
        for d in documents
        if d.status == "ready"
    ][:cap]


def _raw_source_list(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    listed = _source_items(evidence.documents, evidence.chunk_counts, spec.fences.caps["documents"])
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", documents=listed)


def _raw_graph_view(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_graph_data(evidence))


def _traversal_data(ctx: TurnContext, evidence: ComposerEvidence) -> dict[str, Any]:
    """The TraversalView payload from the Graph agent's traversal: one citation per passage reached (a verbatim quote of
    its chunk, preferring a span that holds the label of a seed that reaches it), each step citing the passage its edge
    came from, and the nodes the seeds and the steps name with their stored labels. The validator re-derives all of it."""
    traversal = (evidence.graph or {}).get("traversal") or {}
    graph = ctx.graph
    labels: dict[str, str] = {s["id"]: s["label"] for s in traversal.get("seeds", [])}
    for step in traversal.get("steps", []):
        for end in (step["src"], step["dst"]):
            node = graph.get_node(end) if graph is not None else None
            if end not in labels and node is not None:
                labels[end] = node.label
    chunks = ctx.docs.get_chunks([r["chunk_id"] for r in traversal.get("reached", [])])
    citations: list[dict[str, Any]] = []
    reached: list[dict[str, Any]] = []
    cite_of: dict[str, str] = {}
    for r in traversal.get("reached", []):
        chunk = chunks.get(r["chunk_id"])
        document = ctx.docs.get_document(chunk.doc_id) if chunk is not None else None
        if chunk is None or document is None:
            continue
        seed_labels = [labels[s] for s in r["seed_ids"] if s in labels]
        quote = (excerpt_containing(chunk.text, seed_labels[:1]) if seed_labels else None) or best_excerpt(
            chunk.text, " ".join(seed_labels)
        )
        cid = f"c{r['rank']}"
        cite_of[chunk.id] = cid
        citations.append(
            {
                "id": cid,
                "chunkId": chunk.id,
                "docId": chunk.doc_id,
                "docTitle": document.title,
                "page": chunk.page,
                "quote": quote,
            }
        )
        reached.append({"citationId": cid, "via": r["via"], "rank": r["rank"], "seedIds": list(r["seed_ids"])})
    steps = [
        {
            "source": s["src"],
            "target": s["dst"],
            "relation": s["relation"],
            "citationId": cite_of[s["chunk_id"]],
            "hop": 1,
        }
        for s in traversal.get("steps", [])
        if s["chunk_id"] in cite_of
    ]
    ordered = list(
        dict.fromkeys(
            [s["id"] for s in traversal.get("seeds", [])] + [e for s in steps for e in (s["source"], s["target"])]
        )
    )
    return {
        "seeds": [{"nodeId": s["id"], "match": s["match"]} for s in traversal.get("seeds", [])],
        "nodes": [{"id": n, "label": labels[n]} for n in ordered if n in labels],
        "steps": steps,
        "reached": reached,
        "citations": citations,
        "stepsLeftOut": int(traversal.get("left_out", 0)),
    }


def _raw_traversal_view(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_traversal_data(ctx, evidence))


def _raw_comparison_grid(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_grid_data(evidence))


def _raw_concept_map(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, empty: bool) -> dict[str, Any]:
    return BUILDERS[spec.name](_block_id(spec, ctx), "ready", data=_concept_data(evidence))


RawBuilder = Callable[[Spec, TurnContext, ComposerEvidence, bool], dict[str, Any]]
_RAW: dict[str, RawBuilder] = {
    "CitedSummary": _raw_cited_summary,
    "SourceList": _raw_source_list,
    "GraphView": _raw_graph_view,
    "TraversalView": _raw_traversal_view,
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
        # The failure code stays on the answer block; the trace gets the closed code, never the message.
        record = ComponentRecord("CitedSummary", "error", ("answer_unavailable",), ctx.block_id)
        return Composition((error_block(ctx, failure),), (record,))

    evidence = _evidence(ctx, answer)
    blocks: list[UIBlock] = []
    records: list[ComponentRecord] = []
    view: list[ViewComponent] = []
    for spec in CATALOG.values():
        result = spec.check(evidence)
        if not result.satisfied and not spec.terminal:
            records.append(ComponentRecord(spec.name, "refused", result.reasons))
            continue
        empty = not result.satisfied
        try:
            block = validate_block(_raw(spec, ctx, evidence, empty=empty), ctx.docs, ctx.graph)
        except ValidationFailed as exc:
            log.warning("composed_block_rejected", component=spec.name, issues=[i.path for i in exc.issues])
            if spec.terminal:
                blocks.insert(0, error_block(ctx, exc.to_envelope()))
            # The field paths are in the log above; the trace carries only the closed code.
            records.append(ComponentRecord(spec.name, "error", ("block_failed_validation",), _block_id(spec, ctx)))
            continue
        blocks.append(block)
        records.append(ComponentRecord(spec.name, "empty" if empty else "admitted", result.reasons, block.id))
        if spec.reusable and not empty:
            params = component_params(spec.name, evidence.graph)
            if params is not None:  # the block passed validation just above: the view is verified
                view.append(ViewComponent(spec.name, spec.version, params, True))
    return Composition(tuple(blocks), tuple(records), view=tuple(view))


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


def resolved_labels(graph: dict[str, Any] | None) -> set[str]:
    """The concept labels the Graph agent resolved for a question: its first entities (the comparison's limit of 8) and
    every seed of the traversal (up to 10), lower case. A saved search path stores the traversal's seeds, so the check that
    a saved view's concepts still resolve must read both lists."""
    payload = graph or {}
    found = [*(payload.get("seeds") or []), *((payload.get("traversal") or {}).get("seeds") or [])]
    return {s.get("label", "").strip().lower() for s in found if isinstance(s, dict)}


async def compose_from_pattern(ctx: TurnContext, pattern: SavedPattern) -> Composition:
    """Apply a saved pattern (D-31, stage 5): re-bind its evidence with the Graph agent's deterministic tools, run its
    template through admission, build, validation and layout, and return the one block. **No Research, no Fact Checker
    and no model call.** Fails closed with a reason, never a partial block:
      - `template_changed`: the template is gone, or its version is not the one the pattern was made with, or the
        pattern's parameters are no longer the template's slots (it is stale until re-verified);
      - `document_missing`: a document the parameters name is gone or not ready;
      - `precondition_not_met`: the evidence of the day no longer satisfies the template (or its block no longer
        validates, or the question's entities no longer resolve)."""
    template = CATALOG.get(pattern.templateId)
    params = params_of(pattern)
    if template is None or template.version != pattern.templateVersion or not template.reusable:
        raise PatternRefused("template_changed", "This view was made with an older version of its template.")
    if validate_params(template, params):
        raise PatternRefused("template_changed", "This view no longer matches the shape of its template.")
    for doc_id in params.get("documents", []):
        document = ctx.docs.get_document(doc_id)
        if document is None or document.status != "ready":
            raise PatternRefused("document_missing", "A document this view needs is no longer in your library.")

    graph: dict[str, Any] | None = None
    entities = params.get("entities", [])
    if entities:
        result = await route_to_agent(ctx, "graph", " ".join(entities))
        graph = result.payload if result.status in ("ok", "partial") else None
        resolved = resolved_labels(graph)
        if not graph or not {e.strip().lower() for e in entities} <= resolved:
            raise PatternRefused(
                "precondition_not_met", "The concepts this view is about could not be found in your documents."
            )
    documents, chunk_counts = _documents(ctx)
    evidence = ComposerEvidence(
        answer=None, graph=graph, documents=documents, intent="relate", chunk_counts=chunk_counts
    )
    check = template.check(evidence)
    if not check.satisfied:
        raise PatternRefused("precondition_not_met", "Your documents no longer support this view.")
    try:
        block = validate_block(_raw(template, ctx, evidence, empty=False), ctx.docs, ctx.graph)
    except ValidationFailed as exc:
        log.warning("applied_block_rejected", component=template.name, issues=[i.path for i in exc.issues])
        raise PatternRefused("precondition_not_met", "Your documents no longer support this view.") from exc
    mode_intent = "relate" if pattern.layoutMode == "exploration" else "single"
    try:
        layout = validate_layout(compose_layout([(block.id, template.name)], mode_intent), {block.id})
    except ValidationFailed as exc:
        log.warning("applied_layout_rejected", issues=[i.path for i in exc.issues])
        raise PatternRefused("precondition_not_met", "This view could not be laid out.") from exc
    return Composition(
        (block,),
        (ComponentRecord(template.name, "admitted", (), block.id),),
        layout=layout,
    )


async def reverify_pattern(ctx: TurnContext, pattern: SavedPattern) -> int:
    """Re-verify a saved pattern (D-31, stage 5, E4): the template's registration suite is run again, and the pattern is
    applied as a dry run on today's evidence against the template's **current** version. Returns that version (the
    caller then marks the pattern current and `verified`). Raises `PatternRefused` with the reason otherwise, and the
    pattern is left as it was: stale, with the reason, never silently updated."""
    template = CATALOG.get(pattern.templateId)
    suite = SUITES.get(pattern.templateId)
    if template is None or suite is None or not template.reusable:
        raise PatternRefused("template_changed", "The layout this view was made with no longer exists.")
    valid, defects = suite()
    try:
        register_template(template, fixture_store(), valid, defects, {}, fixture_graph())  # a throwaway registry
    except TemplateRefused as exc:
        log.error("reverify_registration_refused", template=template.name, defect=exc.defect)
        raise PatternRefused("template_changed", "The layout this view was made with did not pass its checks.") from exc
    await compose_from_pattern(ctx, pattern.model_copy(update={"templateVersion": template.version}))
    return template.version


WORKSPACE_SOURCES_ID = "workspace-sources"
"""The id of the source list shown before any question. Fixed, so the prebuilt layout can place it."""


def compose_workspace(docs: DocStore) -> tuple[LayoutSpec, list[UIBlock]]:
    """The workspace before any question (D-28): the prebuilt layout and a validated source list of the stored
    documents (an `empty` one when there are none). No model call. Unlike a turn, this does not swallow a store
    failure or a validation failure: the caller gets the exception and answers with an error envelope, so a
    half-built workspace is never sent."""
    ready = [d for d in docs.list_documents() if d.status == "ready"][: cap("SourceList", "documents")]
    counts = {d.id: len(docs.chunks_for_document(d.id)) for d in ready}
    items = _source_items(ready, counts, len(ready))
    builder = BUILDERS["SourceList"]
    raw = builder(WORKSPACE_SOURCES_ID, "ready", documents=items) if items else builder(WORKSPACE_SOURCES_ID, "empty")
    block = validate_block(raw, docs)
    return validate_layout(prebuilt_layout(WORKSPACE_SOURCES_ID), {block.id}), [block]


NOTES_GRAPH_ID = "notes-graph"
"""The id of the notes view's graph block. Fixed, so a later one replaces it."""


def compose_notes(
    vault: Vault | None,
    docs: DocStore,
    page_id: str | None = None,
    query: str = "",
    learner: LearnerStore | None = None,
) -> tuple[LayoutSpec, list[UIBlock]]:
    """The notes view (M2.6, D-35): a `ConceptPage` for `page_id` (when given) and the `NotesGraph` around it, placed by the
    layout. With no `page_id` it is the overview graph narrowed by `query`. No model call. A page the vault does not hold is a
    NotFound the caller answers with an error envelope; a missing vault gives `empty` placeholders, never a half-built view.
    Everything is validated before it is returned, and this does not swallow a failure."""
    graph_builder, page_builder = BUILDERS["NotesGraph"], BUILDERS["ConceptPage"]
    # One snapshot of the learner's mastery for this request: a score depends on the clock, so the blocks are built and checked from
    # the same reading (D-35 A6).
    mastery = _mastery_snapshot(vault, learner)  # a damaged learner file gives none: every block then says no mastery
    blocks: list[UIBlock] = []
    admitted: list[tuple[str, str]] = []
    if vault is None or not vault.pages:
        empty = validate_block(graph_builder(NOTES_GRAPH_ID, "empty", query=query.strip()), docs, vault=vault)
        return validate_layout(compose_notes_layout([(empty.id, "NotesGraph")]), {empty.id}), [empty]
    if page_id is not None:
        data = derive_concept_page(vault, docs, page_id, mastery)
        if data is None:
            raise NotFound(f"The vault has no page {page_id!r}.")
        page = validate_block(page_builder(f"page:{page_id}", "ready", data=data), docs, vault=vault, mastery=mastery)
        blocks.append(page)
        admitted.append((page.id, "ConceptPage"))
    graph_data = derive_notes_graph(vault, docs, page_id, query, mastery)
    if graph_data is None:
        raise NotFound(f"The vault has no page {page_id!r}.")
    status = "ready" if graph_data["nodes"] else "empty"
    graph = validate_block(
        graph_builder(NOTES_GRAPH_ID, status, data=graph_data if graph_data["nodes"] else None, query=graph_data["query"]),
        docs,
        vault=vault,
        mastery=mastery,
    )
    blocks.append(graph)
    admitted.append((graph.id, "NotesGraph"))
    return validate_layout(compose_notes_layout(admitted), {b.id for b in blocks}), blocks


QUIZ_ID = "quiz"
"""The id of the quiz block. Fixed, so a new quiz replaces the last."""


def _mastery_snapshot(vault: Vault | None, learner: LearnerStore | None) -> Mapping[str, MasteryScore] | None:
    """One reading of the learner's mastery for a request (see `compose_notes`); None when there is none to read."""
    if learner is None or vault is None:
        return None
    try:
        return learner.mastery(vault.pages)
    except Exception as exc:  # a locked or damaged learner file must not take the quiz down
        log.warning("learner_unreadable", error=type(exc).__name__)
        return None


def compose_quiz(
    vault: Vault | None,
    docs: DocStore,
    focus_id: str | None = None,
    learner: LearnerStore | None = None,
) -> tuple[LayoutSpec, list[UIBlock]]:
    """A quiz from the vault's claims (Q1, D-35 A8) and the notes graph beside it: the quiz is in the chat panel's main area, the graph
    (around `focus_id`, or the overview) in the studio panel, so the colours move as the learner answers. No model call. With no
    vault the quiz is an `empty` placeholder; a page the vault does not hold is a NotFound. Everything is validated before it is
    returned, and this does not swallow a failure."""
    quiz_builder, graph_builder = BUILDERS["QuizCard"], BUILDERS["NotesGraph"]
    if vault is None or not vault.pages:
        empty = validate_block(quiz_builder(QUIZ_ID, "empty"), docs, vault=vault)
        return validate_layout(compose_notes_layout([(empty.id, "QuizCard")]), {empty.id}), [empty]
    mastery = _mastery_snapshot(vault, learner)
    data = derive_quiz(vault, docs, focus_id, mastery)
    if data is None:
        raise NotFound(f"The vault has no page {focus_id!r}.")
    quiz = validate_block(
        quiz_builder(QUIZ_ID, "ready" if data["items"] else "empty", data=data), docs, vault=vault, mastery=mastery
    )
    graph_data = derive_notes_graph(vault, docs, focus_id, "", mastery)
    assert graph_data is not None  # the focus page exists: derive_quiz found it
    blocks: list[UIBlock] = [quiz]
    admitted = [(quiz.id, "QuizCard")]
    if graph_data["nodes"]:
        graph = validate_block(
            graph_builder(NOTES_GRAPH_ID, "ready", data=graph_data), docs, vault=vault, mastery=mastery
        )
        blocks.append(graph)
        admitted.append((graph.id, "NotesGraph"))
    return validate_layout(compose_notes_layout(admitted), {b.id for b in blocks}), blocks


LAB_ID = "lab"
"""The id of the lab block. Fixed, so a new lab replaces the last."""


def _lab_error(code: str, message: str, stage: str, retryable: bool = False) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=code,  # type: ignore[arg-type]
        message=message,
        issues=[FieldIssue(path=stage, message=message)],
        retryable=retryable,
    )


def compose_lab(
    docs: DocStore,
    labs: LabStore,
    generator: LabGenerator | None,
    contract_id: str,
) -> tuple[LayoutSpec, list[UIBlock]]:
    """A lab for one of the server's contracts (P4, D-36), through every gate: the evidence (a stored passage states the formula), the generator
    (untrusted), the checker, the verifier, the mint, the store, and the block validator that re-derives the block from the stored record. A
    failure at any stage is an `empty` or `error` block that says which and why, never a half-built lab; nothing unverified is returned.
    No model call while the generator is the fake. An unknown contract is a NotFound."""
    make = CONTRACTS.get(contract_id)
    if make is None:
        raise NotFound(f"The server has no lab {contract_id[:80]!r}.")
    contract = make()
    builder = BUILDERS["VerifiedLab"]

    def shown(block_raw: dict[str, Any]) -> tuple[LayoutSpec, list[UIBlock]]:
        block = validate_block(block_raw, docs, labs=labs)
        return validate_layout(compose_layout([(block.id, "VerifiedLab")], "relate"), {block.id}), [block]

    citation = find_source(docs, contract)
    if citation is None:
        return shown(builder(LAB_ID, "empty"))  # the documents do not state this formula: no lab
    if generator is None:
        return shown(
            builder(LAB_ID, "error", error=_lab_error("provider_unavailable", "Live lab generation is not available yet.", "generator"))
        )
    source = generator.generate(contract)
    try:
        artifact = verify(contract, source)
    except VerificationFailed as failed:
        labs.put_rejected(contract.id, source, failed.stage, failed.reason)
        return shown(builder(LAB_ID, "error", error=_lab_error("validation_failed", failed.reason, failed.stage)))
    except LabToolError as unavailable:
        return shown(builder(LAB_ID, "error", error=_lab_error("internal", str(unavailable), "verifier")))
    labs.put_verified(artifact)
    return shown(builder(LAB_ID, "ready", artifact=artifact, contract=contract, citation=citation))


def compose_block(ctx: TurnContext) -> UIBlock:
    """The terminal block alone (the P0/P1 entry point, kept for callers that only need the answer)."""
    return compose(ctx).primary


def compose_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    composition = compose(runtime.context)
    return {"block": composition.primary, "composition": composition}
