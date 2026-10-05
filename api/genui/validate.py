"""Server-side block validation. Every block passes through here before it can be streamed, and a
violation fails closed: it becomes a ValidationFailed carrying field-path issues, never a partial or
best-effort block (constraint 2).

Two layers:
  1. Schema: the generated strict models (types, required fields, no unknown fields, valid enum).
  2. Content rules the schema cannot express, per block status:
       - meta.error is set if and only if status is "error";
       - "empty", "loading" and "error" blocks are placeholders: no segments, no citations;
       - "ready" and "partial" blocks: every segment cites at least one citation that exists in the
         block, citation ids are unique, each citation's chunk resolves in the DocStore under the
         document it names, and its quote is a verbatim span of that chunk;
       - "ready" additionally needs at least one segment (so at least one citation);
       - no orphan citations (every citation is cited by some segment), no id cited twice in one
         segment, docTitle and page equal the stored document's title and the chunk's page, and a
         quote is at least MIN_QUOTE_CHARS long (or the whole chunk, if it is shorter);
       - any block: a non-empty id (upsert-by-id keys on it) and a non-negative order.

Issue paths are dotted and relative to the block, e.g. "data.segments.0.citationIds.1". When the
UIBlock union grows, the discriminator tag Pydantic puts at the front of a path is stripped so the
path still points into the block.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter, ValidationError

from api.core.errors import ValidationFailed
from api.genui.generated import CitedSummary, FieldIssue, UIBlock
from api.stores.doc_store import DocStore

_UI_BLOCK = TypeAdapter(UIBlock)
_WS = re.compile(r"\s+")
PLACEHOLDER_STATUSES = {"empty", "loading", "error"}
MIN_QUOTE_CHARS = 20  # "a" or "." is not evidence


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _path(loc: tuple[Any, ...], tag: str | None) -> str:
    parts = [str(p) for p in loc]
    if tag is not None and parts and parts[0] == tag:
        parts = parts[1:]  # drop the discriminator tag Pydantic prepends for a union member
    return ".".join(parts) or "(block)"


def _schema_issues(exc: ValidationError, tag: str | None) -> list[FieldIssue]:
    return [FieldIssue(path=_path(e["loc"], tag), message=e["msg"]) for e in exc.errors()]


def validate_block(raw: Mapping[str, Any], docs: DocStore) -> UIBlock:
    """Return the validated block, or raise ValidationFailed naming every violated field."""
    tag = raw.get("type") if isinstance(raw.get("type"), str) else None
    try:
        block = _UI_BLOCK.validate_python(dict(raw))
    except ValidationError as exc:
        raise ValidationFailed("The block does not match the wire schema.", _schema_issues(exc, tag)) from exc

    issues = _content_issues(block, docs)
    if issues:
        raise ValidationFailed("The block failed content validation.", issues)
    return block


def _content_issues(block: CitedSummary, docs: DocStore) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    status, error = block.meta.status, block.meta.error

    if not block.id.strip():
        issues.append(FieldIssue(path="id", message="must not be empty"))
    if block.meta.order < 0:
        issues.append(FieldIssue(path="meta.order", message="must not be negative"))
    if (status == "error") != (error is not None):
        issues.append(
            FieldIssue(
                path="meta.error",
                message="must be set if and only if status is 'error'",
            )
        )

    data = block.data
    if status in PLACEHOLDER_STATUSES:
        if data.segments or data.citations:
            issues.append(
                FieldIssue(
                    path="data",
                    message=f"a '{status}' block must carry no segments or citations",
                )
            )
        return issues

    # "partial" and "ready": whatever is present must be grounded.
    by_id = {c.id: c for c in data.citations}
    if len(by_id) != len(data.citations):
        issues.append(FieldIssue(path="data.citations", message="citation ids must be unique"))

    if status == "ready" and not data.segments:
        issues.append(FieldIssue(path="data.segments", message="a ready block needs at least one segment"))

    referenced: set[str] = set()
    for i, segment in enumerate(data.segments):
        if not segment.citationIds:
            issues.append(
                FieldIssue(path=f"data.segments.{i}.citationIds", message="a segment must cite evidence")
            )
        seen_here: set[str] = set()
        for j, cid in enumerate(segment.citationIds):
            referenced.add(cid)
            if cid in seen_here:
                issues.append(
                    FieldIssue(
                        path=f"data.segments.{i}.citationIds.{j}",
                        message=f"{cid!r} is cited twice in this segment",
                    )
                )
            seen_here.add(cid)
            if cid not in by_id:
                issues.append(
                    FieldIssue(
                        path=f"data.segments.{i}.citationIds.{j}",
                        message=f"no citation with id {cid!r} in this block",
                    )
                )

    chunks = docs.get_chunks([c.chunkId for c in data.citations])
    titles: dict[str, str | None] = {}
    for i, citation in enumerate(data.citations):
        if citation.id not in referenced:
            issues.append(FieldIssue(path=f"data.citations.{i}", message="no segment cites this citation"))
        stored = chunks.get(citation.chunkId)
        if stored is None:
            issues.append(
                FieldIssue(path=f"data.citations.{i}.chunkId", message="no stored chunk has this id")
            )
            continue
        if stored.doc_id != citation.docId:
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.docId",
                    message="the chunk belongs to a different document",
                )
            )
        else:
            if citation.docId not in titles:
                document = docs.get_document(citation.docId)
                titles[citation.docId] = document.title if document else None
            if citation.docTitle != titles[citation.docId]:
                issues.append(
                    FieldIssue(
                        path=f"data.citations.{i}.docTitle",
                        message="does not match the stored document's title",
                    )
                )
        if citation.page != stored.page:
            issues.append(
                FieldIssue(path=f"data.citations.{i}.page", message="does not match the cited chunk's page")
            )
        quote, chunk_text = _norm(citation.quote), _norm(stored.text)
        if not quote:
            issues.append(FieldIssue(path=f"data.citations.{i}.quote", message="a quote is required"))
        elif quote not in chunk_text:
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.quote",
                    message="the quote is not a verbatim span of the cited chunk",
                )
            )
        elif len(quote) < min(MIN_QUOTE_CHARS, len(chunk_text)):
            issues.append(
                FieldIssue(
                    path=f"data.citations.{i}.quote",
                    message=f"the quote is too short to be evidence (under {MIN_QUOTE_CHARS} characters)",
                )
            )
    return issues
