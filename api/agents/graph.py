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
from api.genui.catalog import Composition
from api.genui.generated import (
    BlockEvent,
    DoneEvent,
    LayoutEvent,
    LayoutSpec,
    StreamErrorEvent,
    UIBlock,
)
from api.genui.validate import validate_block, validate_layout

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


def _checked_layout(layout: LayoutSpec | None, block_ids: set[str]) -> LayoutEvent | None:
    """The last gate before the wire for the layout, as `_checked` is for a block: re-validated from plain data against
    the blocks about to be sent, so a layout mutated or built around the validator is not streamed. Never raises: a
    layout that cannot be checked is left out, and layout never fails a turn."""
    if layout is None:
        return None
    try:
        return LayoutEvent(type="layout", layout=validate_layout(layout.model_dump(), block_ids))
    except Exception as exc:
        log.warning("layout_dropped_at_the_gate", error=type(exc).__name__)
        return None


def _checked(block: UIBlock, ctx: TurnContext) -> BlockEvent:
    """The last gate before the wire. Re-validates from plain data, so a block that was built with
    model_construct, or mutated after it was validated, cannot be streamed (constraint 2)."""
    # A notes-family block (a study set or a review schedule) is checked against the vault and the reading it was derived from.
    checked = validate_block(
        block.model_dump(),
        ctx.docs,
        ctx.graph,
        ctx.vault,
        ctx.mastery_snapshot,
        None,
        ctx.last_rated_snapshot,
        ctx.activity_snapshot,
    )
    return BlockEvent(type="block", block=checked)


async def stream_composition(
    composition: Composition, ctx: TurnContext
) -> AsyncIterator[BlockEvent | LayoutEvent | StreamErrorEvent | DoneEvent]:
    """Stream an already-composed result (a saved view applied): its blocks, each through the last gate, then its
    layout through the last gate, then done. No loading block: nothing is awaited. A block that fails the gate ends the
    stream with the error event instead of a partial view."""
    try:
        finals = [_checked(block, ctx) for block in composition.blocks]
    except Exception as exc:
        log.error("applied_view_failed", error=type(exc).__name__)
        yield StreamErrorEvent(type="error", error=envelope_from_exception(exc))
        yield DoneEvent(type="done")
        return
    for event in finals:
        yield event
    layout_event = _checked_layout(composition.layout, {e.block.id for e in finals})
    if layout_event is not None:
        yield layout_event
    yield DoneEvent(type="done")


async def run_turn(
    graph, question: str, ctx: TurnContext
) -> AsyncIterator[BlockEvent | LayoutEvent | StreamErrorEvent | DoneEvent]:
    """Stream one turn: a loading block at once, then every block the Composer chose (the answer has the
    loading block's id, so it replaces it), then the layout for them if it passed validation, then done.

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
        composition = state["composition"]
        finals = [_checked(block, ctx) for block in composition.blocks]
        ctx.composition = (
            composition.records
        )  # recorded only once the blocks passed the last gate: "offered" means sent
    except Exception as exc:
        log.error("turn_failed", error=type(exc).__name__)
        envelope = envelope_from_exception(exc)
        yield _checked(error_block(ctx, envelope), ctx)
        yield StreamErrorEvent(type="error", error=envelope)
        yield DoneEvent(type="done")
        return

    for event in finals:
        yield event
    layout_event = _checked_layout(composition.layout, {e.block.id for e in finals})
    ctx.view = composition.view  # recorded with the turn so a view can be saved from it
    ctx.layout_mode = layout_event.layout.mode if layout_event is not None else "research"
    if (
        layout_event is not None
    ):  # only a layout that passes the last gate is sent; without one the client keeps its own
        yield layout_event
    yield DoneEvent(type="done")
