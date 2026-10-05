"""The turn graph (LangGraph 1.x): START -> research -> compose -> END.

One agent node and a terminal Composer. Later agents join through route_to_agent (P1) without
changing this shape: every turn still ends at compose.

Services reach nodes through LangGraph's runtime context (`context_schema=TurnContext`,
`graph.ainvoke(..., context=ctx)`), not through global state.
"""

from collections.abc import AsyncIterator

from langgraph.graph import END, START, StateGraph

from api.agents.compose import compose_node, error_block, loading_block
from api.agents.research import research_node
from api.agents.state import TurnContext, TurnState
from api.core.errors import envelope_from_exception
from api.core.logging import get_logger
from api.genui.generated import BlockEvent, DoneEvent, StreamErrorEvent, UIBlock
from api.genui.validate import validate_block

log = get_logger(__name__)


def build_turn_graph():
    builder = StateGraph(TurnState, context_schema=TurnContext)
    builder.add_node("research", research_node)
    builder.add_node("compose", compose_node)
    builder.add_edge(START, "research")
    builder.add_edge("research", "compose")
    builder.add_edge("compose", END)
    return builder.compile()


def _checked(block: UIBlock, ctx: TurnContext) -> BlockEvent:
    """The last gate before the wire. Re-validates from plain data, so a block that was built with
    model_construct, or mutated after it was validated, cannot be streamed (constraint 2)."""
    return BlockEvent(type="block", block=validate_block(block.model_dump(), ctx.docs))


async def run_turn(
    graph, question: str, ctx: TurnContext
) -> AsyncIterator[BlockEvent | StreamErrorEvent | DoneEvent]:
    """Stream one turn: a loading block at once, then the final block (same id, so it replaces the
    loading one), then done.

    If the graph itself fails, the Composer still terminates the turn: an error-state block with the
    same id replaces the loading one, then the stream carries the error event, then done. The client
    is never left with a loading block that nothing will resolve.
    """
    try:
        yield _checked(loading_block(ctx), ctx)
    except Exception as exc:  # not even a placeholder can be composed: nothing to replace
        log.error("loading_block_failed", error=type(exc).__name__)
        yield StreamErrorEvent(type="error", error=envelope_from_exception(exc))
        yield DoneEvent(type="done")
        return

    try:
        state = await graph.ainvoke({"question": question}, context=ctx)
        final = _checked(state["block"], ctx)
    except Exception as exc:
        log.error("turn_failed", error=type(exc).__name__)
        envelope = envelope_from_exception(exc)
        yield _checked(error_block(ctx, envelope), ctx)
        yield StreamErrorEvent(type="error", error=envelope)
        yield DoneEvent(type="done")
        return

    yield final
    yield DoneEvent(type="done")
