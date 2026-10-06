"""Saved patterns (D-31): POST /patterns, GET /patterns, DELETE /patterns/{id}.

A pattern is saved from a recorded turn's view and holds a template id, its version, string parameters and the layout
mode: never evidence or document text. Everything is validated on the way in and out; a damaged stored row is an error
envelope, never half a pattern. The names are plain text with a length cap.
"""

from fastapi import APIRouter, Request, Response

from api.genui import patterns
from api.genui.generated import PatternList, SavedPattern, SavePatternRequest

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
