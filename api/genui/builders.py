"""Raw (unvalidated) block dicts. The Composer builds blocks with these and then hands them to
validate_block: nothing built here reaches the wire without passing the validator."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from api.genui.generated import ErrorEnvelope
from api.labs.contract import LabContract
from api.labs.evidence import BLANK_LAB_DATA, derive_lab_data
from api.labs.verifier import VerifiedArtifact


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


def writing_draft(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    return {
        "type": "WritingDraft",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data
        if data is not None
        else {"title": "", "sections": [], "citations": [], "bibliography": []},
    }


def study_set(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    kind: str = "flashcard",
    focus_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "StudySet",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data
        if data is not None
        else {"kind": kind, "focusId": focus_id, "items": [], "summary": None, "citations": [], "skipped": 0},
    }


def study_plan(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
    as_of: str = "1970-01-01",
) -> dict[str, Any]:
    return {
        "type": "StudyPlan",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data
        if data is not None
        else {"asOf": as_of, "items": [], "ratedPages": 0, "leftOut": 0},
    }


def doc_brief(
    block_id: str,
    status: str,
    *,
    data: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    blank = {
        "docId": "",
        "docTitle": "",
        "keyPoints": [],
        "terms": [],
        "actions": [],
        "citations": [],
        "claimsInDocument": 0,
        "leftOut": 0,
    }
    return {
        "type": "DocBrief",
        "id": block_id,
        "meta": {"status": status, "error": error.model_dump() if error is not None else None},
        "data": data if data is not None else blank,
    }


def verified_lab(
    block_id: str,
    status: str,
    *,
    artifact: VerifiedArtifact | None = None,
    contract: LabContract | None = None,
    citation: dict[str, Any] | None = None,
    error: ErrorEnvelope | None = None,
) -> dict[str, Any]:
    """A `VerifiedLab` block. A ready one is built ONLY from a `VerifiedArtifact` (the type the verifier alone mints, D-36); any other type
    is refused here, and the validator re-derives the block from the stored record besides."""
    meta = {"status": status, "error": error.model_dump() if error is not None else None}
    if status == "ready":
        if not isinstance(artifact, VerifiedArtifact) or contract is None or citation is None:
            raise TypeError("a ready VerifiedLab is built from a VerifiedArtifact, its contract and its citation")
        return {"type": "VerifiedLab", "id": block_id, "meta": meta, "data": derive_lab_data(artifact, contract, citation)}
    return {"type": "VerifiedLab", "id": block_id, "meta": meta, "data": copy.deepcopy(BLANK_LAB_DATA)}


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
    "VerifiedLab": verified_lab,
    "WritingDraft": writing_draft,
    "StudySet": study_set,
    "StudyPlan": study_plan,
    "DocBrief": doc_brief,
}
"""One builder per catalog component, keyed by block type. A test keeps this in step with the catalog and the schema."""
