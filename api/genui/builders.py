"""Raw (unvalidated) block dicts. The Composer builds blocks with these and then hands them to
validate_block: nothing built here reaches the wire without passing the validator."""

from __future__ import annotations

from typing import Any

from api.genui.generated import ErrorEnvelope


def cited_summary(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    order: int = 0,
    panel: str = "chat",
) -> dict[str, Any]:
    return {
        "type": "CitedSummary",
        "id": block_id,
        "meta": {
            "panel": panel,
            "order": order,
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"segments": [], "citations": []},
    }
