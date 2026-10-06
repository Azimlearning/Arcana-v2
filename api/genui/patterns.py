"""Saved patterns (D-31, stages 4 and 5): a view the user keeps, as a template and the parameters that re-bind its evidence.

A pattern holds the template id and version, its parameters (strings: entity labels and document ids, validated against
the template's slots) and the layout mode it was shown in. It holds no evidence: no block data, no quote, no document
text. It is content-addressed, so saving the same view twice is one pattern. It is saved only from a turn whose view
was recorded as verified (the block passed `validate_block` and the last gate before it was sent).

This module is pure and store-agnostic except for the functions that take a `DocStore`; nothing here builds a block or
a layout (the Composer does), and nothing here calls a model.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import ValidationError

from api.core.errors import BadRequest, NotFound
from api.genui.catalog import CATALOG, Spec, ViewComponent
from api.genui.generated import PatternParam, SavedPattern
from api.stores.doc_store import DocStore, StoredPattern

NAME_MAX_CHARS = 80
MAX_PATTERNS = 200  # a saved view is cheap but not free: list and save scan every row
MAX_TURN_ID_CHARS = 64
VALUE_MAX_CHARS = 120
_DOC_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ADAPTIVE_MODES = ("research", "exploration")


# ── what a turn records about the views it showed ─────────────────────────────


def view_to_json(layout_mode: str, components: Sequence[ViewComponent]) -> str:
    return json.dumps(
        {
            "layoutMode": layout_mode,
            "components": [
                {"template": c.template, "version": c.version, "params": c.params, "verified": c.verified}
                for c in components
            ],
        },
        sort_keys=True,
    )


def view_from_json(raw: str) -> tuple[str, list[ViewComponent]] | None:
    """The layout mode and components of a recorded view, or None if the record is not a well-formed one."""
    try:
        data = json.loads(raw)
        mode, items = data["layoutMode"], data["components"]
        if not isinstance(mode, str) or not isinstance(items, list):
            return None
        components = []
        for item in items:
            params = item["params"]
            if not (
                isinstance(params, dict)
                and all(
                    isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v)
                    for k, v in params.items()
                )
                and isinstance(item["template"], str)
                and isinstance(item["version"], int)
                and isinstance(item["verified"], bool)
            ):
                return None
            components.append(ViewComponent(item["template"], item["version"], params, item["verified"]))
        return mode, components
    except (ValueError, KeyError, TypeError):
        return None


# ── parameters ────────────────────────────────────────────────────────────────


def validate_params(template: Spec, params: Mapping[str, Sequence[str]]) -> list[str]:
    """Why `params` are not a valid set of parameters for `template` (an empty list: they are valid). Every key must be
    one of the template's slots, every slot's count within its limits, and every value a short plain string of the
    slot's kind: nothing else can be carried."""
    problems: list[str] = []
    slots = {s.name: s for s in template.slots}
    for key in params:
        if key not in slots:
            problems.append(f"{key!r} is not a parameter of {template.name}")
    for slot in template.slots:
        values = list(params.get(slot.name, ()))
        if not slot.min_count <= len(values) <= slot.max_count:
            problems.append(f"{slot.name!r} takes {slot.min_count} to {slot.max_count} values, not {len(values)}")
        for value in values:
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > VALUE_MAX_CHARS
                or _CONTROL.search(value)
            ):
                problems.append(f"{slot.name!r} has a value that is not a short plain string")
            elif slot.kind == "document_id" and not _DOC_ID.match(value):
                problems.append(f"{slot.name!r} has a value that is not a document id")
        if len({v.strip().lower() for v in values if isinstance(v, str)}) != len(values):
            problems.append(f"{slot.name!r} repeats a value")
    return problems


def pattern_id(template_id: str, version: int, params: Mapping[str, Sequence[str]], layout_mode: str) -> str:
    """A content hash of everything that makes a view what it is. Parameter names are sorted; the order of a
    parameter's values is kept (a path from A to B is not a path from B to A)."""
    canonical = json.dumps(
        {
            "template": template_id,
            "version": version,
            "params": {k: list(params[k]) for k in sorted(params)},
            "layout": layout_mode,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def clean_name(name: str) -> str:
    """A pattern's name: plain text, trimmed, one to NAME_MAX_CHARS characters, no control characters."""
    cleaned = name.strip()
    if not cleaned:
        raise BadRequest("A saved view needs a name.")
    if len(cleaned) > NAME_MAX_CHARS:
        raise BadRequest(f"A name is at most {NAME_MAX_CHARS} characters.")
    if _CONTROL.search(cleaned):
        raise BadRequest("A name is plain text: no control characters.")
    return cleaned


# ── saving ────────────────────────────────────────────────────────────────────


def now() -> str:
    return datetime.now(UTC).isoformat()


def save_pattern(docs: DocStore, turn_id: str, template_id: str, name: str) -> SavedPattern:
    """Keep one view of a recorded turn. Refused (with the reason) unless the turn showed that view, it was verified
    (the block passed validation and the last gate), the template is reusable, and its parameters are the template's
    slots. The same view saved twice is one pattern (the first name is kept)."""
    cleaned = clean_name(name)
    raw = docs.get_view(turn_id) if len(turn_id) <= MAX_TURN_ID_CHARS else None
    if raw is None:
        raise NotFound("No views were recorded for that turn.")
    view = view_from_json(raw)
    if view is None:
        raise BadRequest("The recorded views for that turn could not be read.")
    layout_mode, components = view
    entry = next((c for c in components if c.template == template_id), None)
    if entry is None:
        raise BadRequest("That view was not shown on this turn.")
    template = CATALOG.get(template_id)
    if template is None or not template.reusable:
        raise BadRequest("That kind of view cannot be saved.")
    if not entry.verified:
        raise BadRequest("That view was not verified, so it cannot be saved.")
    if entry.version != template.version:
        raise BadRequest("That view was made with an older version of its template.")
    problems = validate_params(template, entry.params)
    if problems:
        raise BadRequest("That view cannot be saved: " + "; ".join(problems) + ".")
    mode = layout_mode if layout_mode in ADAPTIVE_MODES else "research"
    # The same view saved again is the same pattern, even if re-verification has since moved the original to a newer
    # template version (its id is fixed at creation): look for it by what it shows, not by its id.
    existing_patterns = docs.list_patterns()
    for existing in existing_patterns:
        if (
            existing.template_id == template_id
            and existing.layout_mode == mode
            and _same_params(existing, entry.params)
        ):
            if existing.template_version != template.version:
                # The user has just saved a verified view of the current template: that brings a stale pattern up to date.
                docs.update_pattern(existing.id, state="saved", template_version=template.version)
                refreshed = docs.get_pattern(existing.id)
                assert refreshed is not None
                return to_saved(refreshed)
            return to_saved(existing)
    if len(existing_patterns) >= MAX_PATTERNS:
        raise BadRequest(f"You can keep at most {MAX_PATTERNS} saved views. Delete one to save another.")
    stored = docs.put_pattern(
        StoredPattern(
            id=pattern_id(template_id, template.version, entry.params, mode),
            name=cleaned,
            template_id=template_id,
            template_version=template.version,
            params_json=json.dumps([{"key": k, "values": entry.params[k]} for k in sorted(entry.params)]),
            layout_mode=mode,
            state="saved",
            use_count=0,
            created_at=now(),
            last_used_at=None,
        )
    )
    return to_saved(stored)


# ── reading back (validated on the way out) ───────────────────────────────────


def to_saved(stored: StoredPattern) -> SavedPattern:
    """A stored pattern as the wire type. Raises if the row is damaged (it is never returned half-formed): the JSON must
    parse and every field must fit the generated model."""
    try:
        params = [PatternParam.model_validate(p) for p in json.loads(stored.params_json)]
        saved = SavedPattern(
            id=stored.id,
            name=stored.name,
            templateId=stored.template_id,
            templateVersion=stored.template_version,
            params=params,
            layoutMode=stored.layout_mode,  # pyright: ignore[reportArgumentType]
            state=stored.state,  # pyright: ignore[reportArgumentType]
            useCount=stored.use_count,
            createdAt=stored.created_at,
            lastUsedAt=stored.last_used_at,
        )
    except (ValueError, TypeError, ValidationError) as exc:
        raise ValueError(f"stored pattern {stored.id!r} is damaged") from exc
    # Whether the parameters still fit the template's slots is NOT checked here: a pattern whose template has moved on is
    # stale, not damaged. It is listed, and applying or re-verifying it is refused with `template_changed`.
    return saved


def _same_params(stored: StoredPattern, params: Mapping[str, Sequence[str]]) -> bool:
    try:
        return {p["key"]: list(p["values"]) for p in json.loads(stored.params_json)} == {
            k: list(v) for k, v in params.items()
        }
    except (ValueError, KeyError, TypeError):
        return False


def params_of(saved: SavedPattern) -> dict[str, list[str]]:
    return {p.key: list(p.values) for p in saved.params}


def list_patterns(docs: DocStore) -> list[SavedPattern]:
    return [to_saved(p) for p in docs.list_patterns()]


def delete_pattern(docs: DocStore, pattern_id_: str) -> None:
    if len(pattern_id_) > MAX_TURN_ID_CHARS or not docs.delete_pattern(pattern_id_):
        raise NotFound("No saved view has that id.")
