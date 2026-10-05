"""Server-sent events framing. Each SSE message carries exactly one StreamEvent as JSON in `data:`.

Only already-validated models are accepted: the events are the generated types, and the blocks inside
them came from validate_block."""

from api.genui.generated import BlockEvent, DoneEvent, StreamErrorEvent

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse(event: BlockEvent | StreamErrorEvent | DoneEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"
