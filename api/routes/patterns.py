"""Saved patterns (D-31): POST /patterns, GET /patterns, DELETE /patterns/{id}.

A pattern is saved from a recorded turn's view and holds a template id, its version, string parameters and the layout
mode: never evidence or document text. Everything is validated on the way in and out; a damaged stored row is an error
envelope, never half a pattern. The names are plain text with a length cap.
"""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from api.agents.compose import compose_from_pattern
from api.agents.graph import stream_composition
from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.core.errors import NotFound
from api.genui import patterns
from api.genui.generated import PatternList, SavedPattern, SavePatternRequest
from api.genui.stream import SSE_HEADERS, sse

router = APIRouter()


@router.post("/patterns")
async def save_pattern(body: SavePatternRequest, request: Request) -> SavedPattern:
    docs = request.app.state.container.docs
    return patterns.save_pattern(docs, body.turnId, body.templateId, body.name)


@router.get("/patterns")
async def list_patterns(request: Request) -> PatternList:
    return PatternList(patterns=patterns.list_patterns(request.app.state.container.docs))


@router.delete("/patterns/{pattern_id}", status_code=204)
async def delete_pattern(pattern_id: str, request: Request) -> Response:
    patterns.delete_pattern(request.app.state.container.docs, pattern_id)
    return Response(status_code=204)


@router.post("/patterns/{pattern_id}/apply")
async def apply_pattern(pattern_id: str, request: Request) -> StreamingResponse:
    """Apply a saved view: re-bind its evidence with the Graph agent's deterministic tools, then stream its block and
    layout like a turn. No Research, no Fact Checker, no model call. A view that can no longer be shown is refused
    **before** anything streams, as a `pattern_refused` envelope naming the reason (HTTP 409)."""
    container = request.app.state.container
    stored = container.docs.get_pattern(pattern_id) if len(pattern_id) <= patterns.MAX_TURN_ID_CHARS else None
    if stored is None:
        raise NotFound("No saved view has that id.")
    saved = patterns.to_saved(stored)
    ctx = TurnContext(
        docs=container.docs,
        retrieve=container.retrieve,
        llm=container.llm,
        budget=TokenBudget(),
        block_id=f"apply-{uuid.uuid4().hex[:12]}",
        roster=default_roster(),
        graph=container.graph,
    )
    composition = await compose_from_pattern(ctx, saved)  # a refusal is raised here, before the stream starts
    container.docs.mark_pattern_used(saved.id, patterns.now())

    async def events() -> AsyncIterator[str]:
        async for event in stream_composition(composition, ctx):
            yield sse(event)

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
