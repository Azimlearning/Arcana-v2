"""The turn graph (LangGraph 1.x): START -> orchestrate -> compose -> END.

The orchestrate node runs the Orchestrator through route_to_agent, which runs every other agent; agents
are dispatched, budgeted and traced there, not by graph topology (ADR D-22). The graph stays linear and
every turn ends at compose, whatever happened in orchestrate.

Services reach nodes through LangGraph's runtime context (`context_schema=TurnContext`,
`graph.ainvoke(..., context=ctx)`), not through global state.
"""

from collections.abc import AsyncIterator

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from api.agents.compose import compose_node, error_block, loading_block
from api.agents.framework import route_to_agent
from api.agents.state import TurnContext, TurnState
from api.core.errors import envelope_from_exception
from api.core.logging import get_logger
from api.genui.generated import BlockEvent, DoneEvent, StreamErrorEvent, UIBlock
from api.genui.validate import validate_block

log = get_logger(__name__)


async def orchestrate_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict:
    """Never raises: route_to_agent turns any failure into a result, so compose always runs."""
    await route_to_agent(runtime.context, "orchestrator", state.get("question", ""))
    return {}


def build_turn_graph():
    builder = StateGraph(TurnState, context_schema=TurnContext)
    builder.add_node("orchestrate", orchestrate_node)
    builder.add_node("compose", compose_node)
    builder.add_edge(START, "orchestrate")
    builder.add_edge("orchestrate", "compose")
    builder.add_edge("compose", END)
    return builder.compile()


def _checked(block: UIBlock, ctx: TurnContext) -> BlockEvent:
    """The last gate before the wire. Re-validates from plain data, so a block that was built with
    model_construct, or mutated after it was validated, cannot be streamed (constraint 2)."""
    return BlockEvent(type="block", block=validate_block(block.model_dump(), ctx.docs))


async def run_turn(graph, question: str, ctx: TurnContext) -> AsyncIterator[BlockEvent | StreamErrorEvent | DoneEvent]:
    """Stream one turn: a loading block at once, then every block the Composer chose (the answer has the
    loading block's id, so it replaces it), then done.

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
        finals = [_checked(block, ctx) for block in state["composition"].blocks]
    except Exception as exc:
        log.error("turn_failed", error=type(exc).__name__)
        envelope = envelope_from_exception(exc)
        yield _checked(error_block(ctx, envelope), ctx)
        yield StreamErrorEvent(type="error", error=envelope)
        yield DoneEvent(type="done")
        return

    for event in finals:
        yield event
    yield DoneEvent(type="done")
