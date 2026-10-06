"""Raw (unvalidated) block dicts. The Composer builds blocks with these and then hands them to
validate_block: nothing built here reaches the wire without passing the validator."""

from __future__ import annotations

from collections.abc import Callable
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


def source_list(
    block_id: str,
    status: str,
    *,
    documents: list[dict[str, Any]] | None = None,
    error: ErrorEnvelope | None = None,
    order: int = 0,
    panel: str = "sources",
) -> dict[str, Any]:
    return {
        "type": "SourceList",
        "id": block_id,
        "meta": {
            "panel": panel,
            "order": order,
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": {"documents": documents if documents is not None else []},
    }


def graph_view(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    order: int = 0,
    panel: str = "studio",
) -> dict[str, Any]:
    return {
        "type": "GraphView",
        "id": block_id,
        "meta": {
            "panel": panel,
            "order": order,
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"nodes": [], "edges": [], "citations": []},
    }


def comparison_grid(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    order: int = 0,
    panel: str = "chat",
) -> dict[str, Any]:
    return {
        "type": "ComparisonGrid",
        "id": block_id,
        "meta": {
            "panel": panel,
            "order": order,
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"dimensions": [], "rows": [], "citations": []},
    }


BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "CitedSummary": cited_summary,
    "SourceList": source_list,
    "GraphView": graph_view,
    "ComparisonGrid": comparison_grid,
}
"""One builder per catalog component, keyed by block type. A test keeps this in step with the catalog and the schema."""
