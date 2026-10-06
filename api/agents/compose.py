"""The Composer, P0 stub: the only place a block is made, and the terminal step of every turn.

It always produces a block, even when an agent failed or a hop was refused: a failure becomes an
error-state block carrying its reason, no evidence becomes an empty block. Whatever it builds must pass
validate_block; if the validator rejects it, the Composer replaces it with an error-state block carrying
the violation's field paths (fail closed). Choosing among several components and a layout arrives in P2;
the contract (agents return payloads, only the Composer returns blocks) is fixed now.

This module is the ONLY importer of api.genui.builders (a test enforces it): no other code can
construct a block, so nothing reaches the wire that the Composer did not build and validate.
"""

from typing import Any

from langgraph.runtime import Runtime

from api.agents.framework import AgentResult
from api.agents.state import TurnContext, TurnState
from api.core.errors import ValidationFailed
from api.core.logging import get_logger
from api.genui.builders import BUILDERS, cited_summary
from api.genui.catalog import CATALOG, ComponentRecord, ComposerEvidence, Composition, Spec
from api.genui.generated import ErrorEnvelope, UIBlock
from api.genui.validate import validate_block
from api.stores.doc_store import Document

log = get_logger(__name__)

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


def _documents(ctx: TurnContext) -> tuple[Document, ...]:
    """The corpus listing. Every turn must end at the Composer (constraint 4), so a store that cannot list is
    treated as an empty corpus here, and any component that needs documents is simply not admitted."""
    try:
        return tuple(ctx.docs.list_documents())
    except Exception as exc:
        log.warning("document_listing_failed", error=type(exc).__name__)
        return ()


def _evidence(ctx: TurnContext, answer: dict[str, Any] | None) -> ComposerEvidence:
    graph = ctx.results.get("graph")
    return ComposerEvidence(
        answer=answer,
        graph=graph.payload if graph is not None and graph.status in ("ok", "partial") else None,
        documents=_documents(ctx),
        intent=ctx.intent,
    )


def _raw(spec: Spec, ctx: TurnContext, evidence: ComposerEvidence, *, empty: bool) -> dict[str, Any]:
    builder = BUILDERS[spec.name]
    if spec.name == "CitedSummary":
        return builder(ctx.block_id, "empty") if empty else builder(ctx.block_id, "ready", data=evidence.answer)
    raise AssertionError(f"no builder wiring for {spec.name}")  # unreachable while the catalog holds CitedSummary only


def compose(ctx: TurnContext) -> Composition:
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
            records.append(ComponentRecord(spec.name, "error", tuple(i.path for i in exc.issues), ctx.block_id))
            continue
        blocks.append(block)
        records.append(ComponentRecord(spec.name, "empty" if empty else "admitted", result.reasons, block.id))
    return Composition(tuple(blocks), tuple(records))


def compose_block(ctx: TurnContext) -> UIBlock:
    """The terminal block alone (the P0/P1 entry point, kept for callers that only need the answer)."""
    return compose(ctx).primary


def compose_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    composition = compose(runtime.context)
    return {"block": composition.primary, "composition": composition}
