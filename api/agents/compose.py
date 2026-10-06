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
from api.genui.builders import cited_summary
from api.genui.generated import ErrorEnvelope, UIBlock
from api.genui.validate import validate_block

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


def compose_block(ctx: TurnContext) -> UIBlock:
    failure = _failure(ctx)
    if failure is not None:
        return error_block(ctx, failure)

    research = ctx.results.get("research")
    if research is None:
        return error_block(
            ctx, ErrorEnvelope(code="internal", message="No agent produced an answer.", issues=[], retryable=False)
        )
    answer = research.payload.get("answer")
    if ctx.roster.get("fact_checker"):
        # Fail closed: with a checker on the roster, only what it passed is shown. A checker that was
        # never run, failed or was refused is an error block, never the unchecked answer.
        checker = ctx.results.get("fact_checker")
        if checker is None or checker.status in ("failed", "refused"):
            error = checker.error if checker else None
            return error_block(
                ctx,
                error
                or ErrorEnvelope(code="internal", message="The answer could not be checked.", issues=[], retryable=False),
            )
        answer = checker.payload.get("answer")
    raw: dict[str, Any] = (
        cited_summary(ctx.block_id, "empty")
        if answer is None
        else cited_summary(ctx.block_id, "ready", data=answer.data)
    )
    try:
        return validate_block(raw, ctx.docs)
    except ValidationFailed as exc:
        log.warning("composed_block_rejected", issues=[i.path for i in exc.issues])
        return error_block(ctx, exc.to_envelope())


def compose_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    return {"block": compose_block(runtime.context)}
