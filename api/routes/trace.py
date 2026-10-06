"""GET /turns/{turn_id}/trace: what the agents did on one turn, as a validated TurnTrace.

The trace is the turn's own record (which agents ran, in what order, with what status, tokens and time).
It holds no question text, no passage and no secret: notes are short reason codes, and the composition record (what the
Composer offered and why it left a component out) uses a closed list of codes. A turn that was never
traced, or an id that is not one, is a not_found envelope. What is stored is validated again on the way
out, so a damaged row can never reach the client as a half-formed trace.
"""

import json

from fastapi import APIRouter, Request
from pydantic import ValidationError

from api.core.errors import NotFound
from api.core.logging import get_logger
from api.genui.generated import TurnTrace

log = get_logger(__name__)

router = APIRouter()

MAX_TURN_ID_CHARS = 64


@router.get("/turns/{turn_id}/trace")
async def turn_trace(turn_id: str, request: Request) -> TurnTrace:
    container = request.app.state.container
    raw = container.docs.get_trace(turn_id) if len(turn_id) <= MAX_TURN_ID_CHARS else None
    if raw is None:
        raise NotFound("No trace for that turn.")
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "composition" not in data:
            data["composition"] = []  # a trace stored before the composition record existed (P2 C4)
        return TurnTrace.model_validate(data)
    except (ValidationError, ValueError):  # fail closed (the client gets the generic 500 envelope), but leave a clue
        log.error("trace_corrupt", turn_id=turn_id)
        raise
