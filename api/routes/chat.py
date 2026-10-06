"""POST /chat: one question in, a stream of validated blocks out (SSE).

The schema carries no length bounds, so they are enforced here: a non-empty message of bounded
length and a bounded history. History is accepted but not used yet (single-turn Research, P0).
"""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.agents.graph import build_turn_graph, run_turn
from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.core.errors import BadRequest
from api.core.logging import get_logger
from api.genui.generated import BlockEvent, ChatRequest, StreamErrorEvent
from api.genui.stream import SSE_HEADERS, sse
from api.stores.doc_store import Turn

log = get_logger(__name__)
router = APIRouter()

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY = 20
MAX_HISTORY_CHARS = 40_000
_graph = build_turn_graph()


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    container = request.app.state.container
    question = body.message.strip()
    if not question:
        raise BadRequest("The message is empty.")
    if len(question) > MAX_MESSAGE_CHARS:
        raise BadRequest(f"The message is longer than {MAX_MESSAGE_CHARS} characters.")
    if len(body.history) > MAX_HISTORY:
        raise BadRequest(f"The history is longer than {MAX_HISTORY} messages.")
    if sum(len(m.content) for m in body.history) > MAX_HISTORY_CHARS or any(
        len(m.content) > MAX_MESSAGE_CHARS for m in body.history
    ):
        raise BadRequest("The history is too long.")

    ctx = TurnContext(
        docs=container.docs,
        retrieve=container.retrieve,
        llm=container.llm,
        budget=TokenBudget(),
        block_id=f"turn-{uuid.uuid4().hex[:12]}",
        roster=default_roster(),
    )

    async def events() -> AsyncIterator[str]:
        started = time.perf_counter()
        error_code: str | None = None
        try:
            async for event in run_turn(_graph, question, ctx):
                if isinstance(event, StreamErrorEvent):
                    error_code = event.error.code
                elif isinstance(event, BlockEvent) and event.block.meta.status == "error":
                    error_code = event.block.meta.error.code if event.block.meta.error else "internal"
                yield sse(event)
        finally:  # also runs when the client disconnects mid-stream
            try:
                container.docs.record_turn(
                    Turn(
                        id=ctx.block_id,
                        created_at=datetime.now(UTC).isoformat(),
                        query=question[:500],
                        outcome="error" if error_code else "ok",
                        latency_ms=round((time.perf_counter() - started) * 1000),
                        error_code=error_code,
                    )
                )
            except Exception as exc:  # recording is bookkeeping: it must never break the response
                log.error("turn_not_recorded", error=type(exc).__name__)

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
