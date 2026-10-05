"""The Composer, P0 stub: the only place a block is made, and the terminal step of every turn.

It always produces a block, even when research failed or found nothing: a failure becomes an
error-state block carrying its reason, no evidence becomes an empty block. Whatever it builds must
pass validate_block; if the validator rejects it, the Composer replaces it with an error-state block
carrying the violation's field paths (fail closed). Choosing among several components and a layout
arrives in P2; the contract (agents return payloads, only the Composer returns blocks) is fixed now.

This module is the ONLY importer of api.genui.builders (a test enforces it): no other code can
construct a block, so nothing reaches the wire that the Composer did not build and validate.
"""

from typing import Any

from langgraph.runtime import Runtime

from api.agents.state import TurnContext, TurnState
from api.core.errors import ValidationFailed
from api.core.logging import get_logger
from api.genui.builders import cited_summary
from api.genui.generated import ErrorEnvelope, UIBlock
from api.genui.validate import validate_block

log = get_logger(__name__)


def loading_block(ctx: TurnContext) -> UIBlock:
    """The placeholder streamed at once; the turn's final block replaces it (same id)."""
    return validate_block(cited_summary(ctx.block_id, "loading"), ctx.docs)


def error_block(ctx: TurnContext, error: ErrorEnvelope) -> UIBlock:
    """An error-state block for this turn, carrying `error`. Used whenever a turn cannot finish."""
    return validate_block(cited_summary(ctx.block_id, "error", error=error), ctx.docs)


def compose_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    ctx = runtime.context
    error, answer = state.get("error"), state.get("answer")

    if error is not None:
        return {"block": error_block(ctx, error)}
    raw = cited_summary(ctx.block_id, "empty") if answer is None else cited_summary(
        ctx.block_id, "ready", data=answer.data
    )
    try:
        return {"block": validate_block(raw, ctx.docs)}
    except ValidationFailed as exc:
        log.warning("composed_block_rejected", issues=[i.path for i in exc.issues])
        return {"block": error_block(ctx, exc.to_envelope())}
