"""Raw (unvalidated) block dicts. The Composer builds blocks with these and then hands them to
validate_block: nothing built here reaches the wire without passing the validator."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from api.genui.generated import ErrorEnvelope


def cited_summary(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "CitedSummary",
        "id": block_id,
        "meta": {
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
) -> dict[str, Any]:
    return {
        "type": "SourceList",
        "id": block_id,
        "meta": {
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
) -> dict[str, Any]:
    return {
        "type": "GraphView",
        "id": block_id,
        "meta": {
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"nodes": [], "edges": [], "citations": []},
    }


def traversal_view(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "TraversalView",
        "id": block_id,
        "meta": {
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data
        if data is not None
        else {"seeds": [], "nodes": [], "steps": [], "reached": [], "citations": [], "stepsLeftOut": 0},
    }


_EMPTY_PAGE = {
    "page": {"id": "", "label": ""},
    "kind": None,
    "aliases": [],
    "passages": 0,
    "documents": 0,
    "definitions": [],
    "links": [],
    "linksLeftOut": 0,
    "claims": [],
    "mentions": [],
    "mentionsLeftOut": 0,
    "citations": [],
    "mastery": None,
}


def concept_page(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "ConceptPage",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data if data is not None else copy.deepcopy(_EMPTY_PAGE),
    }


def notes_graph(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    query: str = "",
) -> dict[str, Any]:
    return {
        "type": "NotesGraph",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data
        if data is not None
        else {"focusId": None, "query": query, "nodes": [], "edges": [], "nodesLeftOut": 0},
    }


def quiz_card(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    focus_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "QuizCard",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data if data is not None else {"focusId": focus_id, "items": [], "skipped": 0},
    }


def comparison_grid(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "ComparisonGrid",
        "id": block_id,
        "meta": {
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"dimensions": [], "rows": [], "citations": []},
    }


def concept_map(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "ConceptMap",
        "id": block_id,
        "meta": {
            "status": status,
            "error": error.model_dump() if error is not None else None,
        },
        "data": data if data is not None else {"steps": [], "citations": []},
    }


BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "CitedSummary": cited_summary,
    "SourceList": source_list,
    "GraphView": graph_view,
    "TraversalView": traversal_view,
    "ComparisonGrid": comparison_grid,
    "ConceptMap": concept_map,
    "ConceptPage": concept_page,
    "NotesGraph": notes_graph,
    "QuizCard": quiz_card,
}
"""One builder per catalog component, keyed by block type. A test keeps this in step with the catalog and the schema."""
