"""The component catalog: what each component needs from retrieval before the Composer may show it (D-28).

A `Spec` is a component's written structural precondition (catalog.md, "The bound") as a pure function of
`ComposerEvidence`. The evidence is plain data built once per turn from what the agents returned: no store
handles, no model, so a check is deterministic and the Composer needs no provider call to decide.

This module knows nothing about blocks' wire shapes beyond the type name and nothing about agents. Adding a
component is a new `Spec` here plus the steps in catalog.md, "How to add a component"; the Composer and the
layout do not change (D-27).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from api.genui.generated import UIBlock
from api.stores.doc_store import Document


@dataclass(frozen=True)
class ComposerEvidence:
    """Everything the catalog may look at for one turn."""

    answer: dict[str, Any] | None
    """The CitedSummary payload after the Fact Checker, or None when nothing could be grounded."""
    graph: dict[str, Any] | None
    """The Graph agent's payload (mode, entities, nodes, edges, chunk_ids), or None when it did not run."""
    documents: tuple[Document, ...]
    intent: str


@dataclass(frozen=True)
class Placement:
    """A hint to the layout, not a position (D-27): the panel this component prefers and its priority in it."""

    panel: str
    priority: int


@dataclass(frozen=True)
class Result:
    satisfied: bool
    reasons: tuple[str, ...] = ()
    """Short codes saying why not (empty when satisfied)."""


@dataclass(frozen=True)
class Spec:
    name: str
    """The `type` tag of the block, exactly as in the schema's UIBlock union."""
    precondition: str
    """The structural precondition in words, as written in catalog.md."""
    supplied_by: tuple[str, ...]
    """The agents whose output the check reads."""
    caps: Mapping[str, int]
    placement: Placement
    check: Callable[[ComposerEvidence], Result]
    terminal: bool = False
    """The turn's answer component. When its precondition fails the Composer shows its empty state instead of
    omitting it, so every turn ends with a visible result (constraint 4)."""


RecordOutcome = Literal["admitted", "empty", "refused", "error"]


@dataclass(frozen=True)
class ComponentRecord:
    """What the Composer decided for one component this turn, kept for the trace."""

    component: str
    outcome: RecordOutcome
    reasons: tuple[str, ...] = ()
    block_id: str | None = None


@dataclass(frozen=True)
class Composition:
    """The Composer's whole output for a turn: the blocks to stream (the terminal one first) and one record
    per component the catalog considered."""

    blocks: tuple[UIBlock, ...]
    records: tuple[ComponentRecord, ...] = field(default=())

    @property
    def primary(self) -> UIBlock:
        return self.blocks[0]


# ── the components ────────────────────────────────────────────────────────────


def _check_cited_summary(evidence: ComposerEvidence) -> Result:
    segments = evidence.answer.get("segments") if evidence.answer else None
    return Result(True) if segments else Result(False, ("no_grounded_answer",))


CITED_SUMMARY = Spec(
    name="CitedSummary",
    precondition="The Research agent produced at least one segment, each citing a stored chunk.",
    supplied_by=("research", "fact_checker"),
    caps={"segments": 40, "citations": 40},
    placement=Placement(panel="chat", priority=0),
    check=_check_cited_summary,
    terminal=True,
)

CATALOG: dict[str, Spec] = {spec.name: spec for spec in (CITED_SUMMARY,)}
"""Every component the Composer may admit, in the order it considers them (the terminal one first)."""
