"""The lab components' catalog (P4, D-36): `VerifiedLab`.

Like the notes components it is not a turn component: the Composer never offers it to a question and the trace never lists it. A lab is
made on request (`POST /labs`), by the lab tool, and the block can only be built from a verifier-minted artifact. It has its own small
registry for the same reasons (a written precondition, fences read by the validator and the Composer, a grounding rule, accessibility
requirements checked against the component's source, a placement hint, and a registration suite of planted defects).
"""

from __future__ import annotations

from api.genui.catalog import A11yRequirement, Fences, PlacementHint
from api.genui.notes_catalog import NotesSpec
from api.labs.contract import MAX_GRID, MAX_PARAMETERS

MAX_SOURCE_CHARS = 4000

VERIFIED_LAB = NotesSpec(
    name="VerifiedLab",
    precondition=(
        "A stored passage holds the sentence that states the lab's formula (the contract's source phrase), and a function written for "
        "the contract passed the checker (an AST allowlist) and the verifier (reference cases, properties, a fuzz, the Python reference) "
        "in an isolated runner. Only the verifier can mint the artifact the block is built from."
    ),
    supplied_by=("lab verifier",),
    fences=Fences(
        caps={"parameters": MAX_PARAMETERS, "grid_steps": MAX_GRID, "source_chars": MAX_SOURCE_CHARS},
        grounding="lab_verified_record",
        a11y=(A11yRequirement("region", "Lab"), A11yRequirement("group", "Parameters")),
    ),
    placement=PlacementHint(panel="studio", priority=30),
)

LAB_CATALOG: dict[str, NotesSpec] = {VERIFIED_LAB.name: VERIFIED_LAB}
