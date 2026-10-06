"""Template registration: a template cannot register unless the validator rejects every defect planted in it (D-31).

A catalog `Spec` is a template: a reviewed, versioned recipe with typed slots and fences (the limits it stays inside).
Before a template may be used, `register_template` builds a valid block from a fixture, applies each **planted
defect** (a missing chunk, a quote that is not verbatim, a quote without a label, a cell citing another document, an
over-cap list, an orphan citation, and whatever else the template declares), runs `validate_block`, and refuses unless
every defect is rejected. A hole in the validator is therefore found when the template is registered, not when a user
meets it. The five built-in components register through it (`ensure_builtin_registered`, run at start-up).

The suites are the tamper tests of the component tasks, made declarative: the same defects, now a gate rather than a
test file. This module imports the block builders only to build the fixture blocks the suites start from; the Composer
remains the only importer that builds blocks for the wire.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from api.core.errors import ValidationFailed
from api.genui.builders import BUILDERS
from api.genui.catalog import CATALOG, Spec
from api.genui.validate import validate_block
from api.stores.doc_store import Chunk, DocStore, Document
from api.stores.local.sqlite_doc import SqliteDocStore


@dataclass(frozen=True)
class PlantedDefect:
    """One way a block of this template could be wrong. `apply` damages a valid raw block in place."""

    name: str
    apply: Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class Registration:
    template: str
    version: int
    rejected: tuple[str, ...]
    """The planted defects the validator rejected: all of them, or the template would not be registered."""


class TemplateRefused(Exception):
    """A template was not registered. `defect` names the planted defect that validated (None: the fixture itself
    failed, or no defects were declared)."""

    def __init__(self, template: str, defect: str | None, reason: str):
        super().__init__(f"template {template!r} refused: {reason}" + (f" (defect {defect!r})" if defect else ""))
        self.template = template
        self.defect = defect
        self.reason = reason


REGISTRY: dict[str, Registration] = {}
"""The templates that passed registration, by name."""


def register_template(
    template: Spec,
    docs: DocStore,
    valid: Mapping[str, Any],
    defects: Sequence[PlantedDefect],
    registry: dict[str, Registration] | None = None,
) -> Registration:
    """Register `template` only if `valid` validates and every planted defect is rejected."""
    registry = REGISTRY if registry is None else registry
    if valid.get("type") != template.name:
        raise TemplateRefused(template.name, None, f"the fixture is a {valid.get('type')!r} block")
    if not defects:
        raise TemplateRefused(template.name, None, "no planted defects were declared")
    try:
        validate_block(copy.deepcopy(dict(valid)), docs)
    except ValidationFailed as exc:
        paths = ", ".join(i.path for i in exc.issues)
        raise TemplateRefused(template.name, None, f"the fixture block does not validate ({paths})") from exc

    names = [d.name for d in defects]
    if len(set(names)) != len(names):
        raise TemplateRefused(template.name, None, "planted defect names must be unique")
    for defect in defects:
        damaged = copy.deepcopy(dict(valid))
        defect.apply(damaged)
        if damaged == dict(valid):
            raise TemplateRefused(template.name, defect.name, "the defect changes nothing")
        try:
            validate_block(damaged, docs)
        except ValidationFailed:
            continue  # rejected, as it must be
        raise TemplateRefused(template.name, defect.name, "the validator accepted a block with this defect")

    registration = Registration(template.name, template.version, tuple(names))
    registry[template.name] = registration
    return registration


# ── the built-in suites ───────────────────────────────────────────────────────

A1 = "Alpha Method builds on Beta Index for fast lookup in the pipeline."
A2 = "Beta Index is compared with Gamma Cache in the experiments."
B1 = "In this second paper, Alpha Method underpins the baseline pipeline."
B2 = "The second paper uses Beta Index as the sparse arm of its pipeline."
TITLE_A, TITLE_B = "Fixture Paper A", "Fixture Paper B"


def fixture_store() -> DocStore:
    """A throwaway in-memory store with two small papers whose sentences name a few concepts."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    docs = SqliteDocStore(engine)
    for doc_id, title in (("fx-a", TITLE_A), ("fx-b", TITLE_B)):
        docs.put_document(Document(doc_id, title, f"{doc_id}.pdf", "ready", 1, None, "2026-01-01"))
    docs.put_chunks(
        [
            Chunk("fx-a-1", "fx-a", 0, 1, A1),
            Chunk("fx-a-2", "fx-a", 1, 2, A2),
            Chunk("fx-b-1", "fx-b", 0, 1, B1),
            Chunk("fx-b-2", "fx-b", 1, 2, B2),
        ]
    )
    return docs


def _cite(cid: str, chunk: str, doc: str, title: str, page: int, quote: str) -> dict[str, Any]:
    return {"id": cid, "chunkId": chunk, "docId": doc, "docTitle": title, "page": page, "quote": quote}


def _data(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["data"]


def _first_citation(raw: dict[str, Any]) -> dict[str, Any]:
    return _data(raw)["citations"][0]


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    """A defect that sets one dotted path (list indexes are numbers) in the block."""

    def apply(raw: dict[str, Any]) -> None:
        node: Any = raw
        *head, last = path.split(".")
        for part in head:
            node = node[int(part)] if isinstance(node, list) else node[part]
        node[int(last) if isinstance(node, list) else last] = value

    return apply


def _common(raw_citations_path: str = "data.citations") -> list[PlantedDefect]:
    """Defects every citation-bearing template must reject, whatever its component."""
    return [
        PlantedDefect("missing_chunk", _set(f"{raw_citations_path}.0.chunkId", "no-such-chunk")),
        PlantedDefect(
            "non_verbatim_quote",
            _set(f"{raw_citations_path}.0.quote", "This sentence does not appear in the cited chunk at all."),
        ),
        PlantedDefect("quote_too_short", _set(f"{raw_citations_path}.0.quote", "Alpha")),
        PlantedDefect("wrong_doc_title", _set(f"{raw_citations_path}.0.docTitle", "A Different Title")),
        PlantedDefect("wrong_page", _set(f"{raw_citations_path}.0.page", 99)),
        PlantedDefect("unknown_field", lambda raw: raw.update(surprise=True)),
        PlantedDefect("empty_id", _set("id", "  ")),
        PlantedDefect("error_status_without_envelope", _set("meta.status", "error")),
        PlantedDefect("unknown_status", _set("meta.status", "great")),
        PlantedDefect(
            "orphan_citation",
            lambda raw: _data(raw)["citations"].append(
                _cite("c99", "fx-a-2", "fx-a", TITLE_A, 2, A2)  # a real, verbatim citation that nothing cites
            ),
        ),
    ]


def _repeat(raw: dict[str, Any], key: str, times: int) -> None:
    _data(raw)[key] = _data(raw)[key] * times


def _cited_summary() -> tuple[dict[str, Any], list[PlantedDefect]]:
    raw = BUILDERS["CitedSummary"](
        "fx-summary",
        "ready",
        data={
            "segments": [{"text": "Alpha Method builds on Beta Index.", "citationIds": ["c1"]}],
            "citations": [_cite("c1", "fx-a-1", "fx-a", TITLE_A, 1, A1)],
        },
    )
    return raw, [
        *_common(),
        PlantedDefect("uncited_segment", _set("data.segments.0.citationIds", [])),
        PlantedDefect("segment_cites_missing_citation", _set("data.segments.0.citationIds", ["c7"])),
        PlantedDefect("ready_without_segments", lambda r: _data(r).update(segments=[])),
        PlantedDefect("over_cap_segments", lambda r: _repeat(r, "segments", 41)),
        PlantedDefect("placeholder_with_content", _set("meta.status", "empty")),
    ]


def _source_list() -> tuple[dict[str, Any], list[PlantedDefect]]:
    items = [{"docId": "fx-a", "title": TITLE_A, "chunkCount": 2}, {"docId": "fx-b", "title": TITLE_B, "chunkCount": 2}]
    raw = BUILDERS["SourceList"]("fx-sources", "ready", documents=items)
    return raw, [
        PlantedDefect("unknown_document", _set("data.documents.0.docId", "no-such-document")),
        PlantedDefect("wrong_title", _set("data.documents.0.title", "A Different Title")),
        PlantedDefect("wrong_chunk_count", _set("data.documents.0.chunkCount", 99)),
        PlantedDefect("duplicate_document", _set("data.documents.1.docId", "fx-a")),
        PlantedDefect("over_cap_documents", lambda r: _repeat(r, "documents", 26)),
        PlantedDefect("ready_without_documents", lambda r: _data(r).update(documents=[])),
        PlantedDefect("placeholder_with_documents", _set("meta.status", "loading")),
        PlantedDefect("error_status_without_envelope", _set("meta.status", "error")),
        PlantedDefect("unknown_field", lambda r: r.update(surprise=True)),
        PlantedDefect("empty_id", _set("id", "  ")),
    ]


def _graph_view() -> tuple[dict[str, Any], list[PlantedDefect]]:
    raw = BUILDERS["GraphView"](
        "fx-graph",
        "ready",
        data={
            "nodes": [{"id": "alpha", "label": "Alpha Method"}, {"id": "beta", "label": "Beta Index"}],
            "edges": [{"source": "alpha", "target": "beta", "relation": "builds on", "citationId": "c1"}],
            "citations": [_cite("c1", "fx-a-1", "fx-a", TITLE_A, 1, A1)],
        },
    )

    def extra_nodes(r: dict[str, Any], count: int) -> None:
        """More nodes than the cap, each joined to the first by a grounded edge: only the cap is violated."""
        _data(r)["nodes"] += [{"id": f"x{i}", "label": "Beta Index"} for i in range(count)]
        _data(r)["edges"] += [
            {"source": "alpha", "target": f"x{i}", "relation": "builds on", "citationId": "c1"} for i in range(count)
        ]

    return raw, [
        *_common(),
        PlantedDefect("edge_to_missing_node", _set("data.edges.0.target", "ghost")),
        PlantedDefect("quote_without_label", _set("data.nodes.1.label", "Louvain communities")),
        PlantedDefect("orphan_node", lambda r: _data(r)["nodes"].append({"id": "lonely", "label": "Alpha Method"})),
        PlantedDefect("duplicate_node_id", _set("data.nodes.1.id", "alpha")),
        PlantedDefect("self_loop", _set("data.edges.0.target", "alpha")),
        PlantedDefect("edge_citing_nothing", _set("data.edges.0.citationId", "c9")),
        PlantedDefect("over_long_relation", _set("data.edges.0.relation", "x" * 81)),
        PlantedDefect("over_cap_nodes", lambda r: extra_nodes(r, 29)),
        PlantedDefect("over_cap_edges", lambda r: _repeat(r, "edges", 41)),
        PlantedDefect("ready_without_edges", lambda r: _data(r).update(edges=[])),
        PlantedDefect("placeholder_with_graph", _set("meta.status", "empty")),
    ]


def _comparison_grid() -> tuple[dict[str, Any], list[PlantedDefect]]:
    citations = [
        _cite("c1", "fx-a-1", "fx-a", TITLE_A, 1, A1),
        _cite("c2", "fx-a-2", "fx-a", TITLE_A, 2, A2),
        _cite("c3", "fx-b-1", "fx-b", TITLE_B, 1, B1),
        _cite("c4", "fx-b-2", "fx-b", TITLE_B, 2, B2),
    ]
    rows = [
        {
            "docId": "fx-a",
            "docTitle": TITLE_A,
            "cells": [{"dimensionId": "alpha", "citationId": "c1"}, {"dimensionId": "beta", "citationId": "c2"}],
        },
        {
            "docId": "fx-b",
            "docTitle": TITLE_B,
            "cells": [{"dimensionId": "alpha", "citationId": "c3"}, {"dimensionId": "beta", "citationId": "c4"}],
        },
    ]
    raw = BUILDERS["ComparisonGrid"](
        "fx-grid",
        "ready",
        data={
            "dimensions": [{"id": "alpha", "label": "Alpha Method"}, {"id": "beta", "label": "Beta Index"}],
            "rows": rows,
            "citations": citations,
        },
    )
    return raw, [
        *_common(),
        PlantedDefect("cell_citing_another_document", _set("data.rows.0.cells.0.citationId", "c3")),
        PlantedDefect("quote_without_label", _set("data.dimensions.1.label", "Louvain communities")),
        PlantedDefect("dimension_in_one_row", lambda r: _data(r)["rows"][1]["cells"].pop()),
        PlantedDefect("row_without_cells", _set("data.rows.1.cells", [])),
        PlantedDefect("wrong_row_title", _set("data.rows.1.docTitle", "A Different Title")),
        PlantedDefect("unknown_row_document", _set("data.rows.1.docId", "no-such-document")),
        PlantedDefect(
            "duplicate_cell", lambda r: _data(r)["rows"][0]["cells"].append(dict(_data(r)["rows"][0]["cells"][0]))
        ),
        PlantedDefect("duplicate_column_label", _set("data.dimensions.1.label", "alpha method")),
        PlantedDefect("over_cap_rows", lambda r: _repeat(r, "rows", 4)),
        PlantedDefect(
            "over_cap_dimensions",
            lambda r: _data(r)["dimensions"].extend({"id": f"x{i}", "label": f"Entity {i}"} for i in range(7)),
        ),
        PlantedDefect("cell_for_unknown_dimension", _set("data.rows.0.cells.0.dimensionId", "ghost")),
        PlantedDefect("placeholder_with_rows", _set("meta.status", "empty")),
    ]


def _concept_map() -> tuple[dict[str, Any], list[PlantedDefect]]:
    raw = BUILDERS["ConceptMap"](
        "fx-map",
        "ready",
        data={
            "steps": [
                {
                    "source": "Alpha Method",
                    "target": "Beta Index",
                    "relation": "builds on",
                    "reversed": False,
                    "citationId": "c1",
                },
                {
                    "source": "Beta Index",
                    "target": "Gamma Cache",
                    "relation": "compared with",
                    "reversed": False,
                    "citationId": "c2",
                },
            ],
            "citations": [
                _cite("c1", "fx-a-1", "fx-a", TITLE_A, 1, A1),
                _cite("c2", "fx-a-2", "fx-a", TITLE_A, 2, A2),
            ],
        },
    )
    return raw, [
        *_common(),
        PlantedDefect("non_contiguous_steps", _set("data.steps.1.source", "Somewhere Else")),
        PlantedDefect("repeated_concept", _set("data.steps.1.target", "Alpha Method")),
        PlantedDefect("quote_without_label", _set("data.steps.1.target", "Louvain communities")),
        PlantedDefect("step_citing_nothing", _set("data.steps.0.citationId", "c9")),
        PlantedDefect("single_step_path", lambda r: _data(r)["steps"].pop()),
        PlantedDefect("over_cap_steps", lambda r: _repeat(r, "steps", 4)),
        PlantedDefect("over_long_relation", _set("data.steps.0.relation", "x" * 81)),
        PlantedDefect("placeholder_with_steps", _set("meta.status", "empty")),
    ]


SUITES: dict[str, Callable[[], tuple[dict[str, Any], list[PlantedDefect]]]] = {
    "CitedSummary": _cited_summary,
    "SourceList": _source_list,
    "GraphView": _graph_view,
    "ComparisonGrid": _comparison_grid,
    "ConceptMap": _concept_map,
}
"""For each built-in template, a valid fixture block and its planted defects."""


def ensure_builtin_registered(registry: dict[str, Registration] | None = None) -> dict[str, Registration]:
    """Register every template in the catalog through its suite, if not already registered at its current version.
    Raises `TemplateRefused` naming the template and the defect: the application must not start with a template whose
    validator has a hole. A template in the catalog with no declared suite is refused too."""
    registry = REGISTRY if registry is None else registry
    pending = [
        t for name, t in CATALOG.items() if registry.get(name, None) is None or registry[name].version != t.version
    ]
    if not pending:
        return registry
    docs = fixture_store()
    for template in pending:
        suite = SUITES.get(template.name)
        if suite is None:
            raise TemplateRefused(template.name, None, "no planted-defect suite is declared for it")
        valid, defects = suite()
        register_template(template, docs, valid, defects, registry)
    return registry


# ── the guide must state the same fences ──────────────────────────────────────

_FENCES_LINE = re.compile(r"\*\*Fences:\*\*\s*caps\s*`([^`]*)`;\s*grounding\s*`([^`]*)`;\s*a11y\s*`([^`]*)`")


@dataclass(frozen=True)
class DocFences:
    caps: dict[str, int]
    grounding: str
    a11y: tuple[tuple[str, str], ...]


def doc_fences(guide: str) -> dict[str, DocFences]:
    """The fences each `## Component` section of catalog.md states, parsed from its `**Fences:**` line."""
    found: dict[str, DocFences] = {}
    for section in re.split(r"^## ", guide, flags=re.M)[1:]:
        title = section.split("\n", 1)[0].strip().removesuffix("(stretch)").strip()
        match = _FENCES_LINE.search(section)
        if match is None:
            continue
        caps = {k: int(v) for k, v in (pair.split("=") for pair in match.group(1).split())}
        a11y = tuple(
            (role.strip(), label.strip())
            for role, label in (item.split(":", 1) for item in match.group(3).split("|") if ":" in item)
        )
        found[title] = DocFences(caps, match.group(2), a11y)
    return found


def fence_mismatches(guide: str, catalog: Mapping[str, Spec] | None = None) -> list[str]:
    """Every difference between the fences in the guide and the registered templates' fences (empty: they agree)."""
    catalog = CATALOG if catalog is None else catalog
    stated = doc_fences(guide)
    problems: list[str] = []
    for name, template in catalog.items():
        doc = stated.get(name)
        if doc is None:
            problems.append(f"{name}: the guide has no Fences line")
            continue
        if doc.caps != template.fences.caps:
            problems.append(f"{name}: caps in the guide {doc.caps} differ from the template's {template.fences.caps}")
        if doc.grounding != template.fences.grounding:
            problems.append(f"{name}: grounding rule {doc.grounding!r} differs from {template.fences.grounding!r}")
        wanted = tuple((r.role, r.label) for r in template.fences.a11y)
        if doc.a11y != wanted:
            problems.append(f"{name}: accessibility requirements in the guide {doc.a11y} differ from {wanted}")
    return problems


__all__ = [
    "REGISTRY",
    "PlantedDefect",
    "Registration",
    "TemplateRefused",
    "doc_fences",
    "ensure_builtin_registered",
    "fence_mismatches",
    "fixture_store",
    "register_template",
]
