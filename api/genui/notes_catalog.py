"""The notes components' catalog (M2.6, D-35): `ConceptPage`, `NotesGraph` and (Q1, A8) `QuizCard`.

They are not turn components. The Composer never offers them to a question and the trace never lists them: they are shown by the
notes view, which asks for a page or for the vault's graph (`GET /vault/notes`). So they have their own small registry instead
of entries in `CATALOG` (whose `check` is a function of one turn's evidence). They still follow the same rules: a written
structural precondition (here satisfied by the vault, not by retrieval), fences with caps that the validator and the Composer
both read, a grounding rule, a11y requirements checked against the component's source, a placement hint the layout reads as
data, and a registration suite of planted defects (`api/genui/test_notes.py`) that the validator must reject.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.genui.catalog import A11yRequirement, Fences, PlacementHint
from api.vault.brief import brief_caps
from api.vault.quiz import MAX_ITEMS, OPTION_COUNT
from api.vault.review import MAX_ITEMS as PLAN_ITEMS
from api.vault.study import MAX_ITEMS as STUDY_ITEMS
from api.vault.study import MAX_NOTES as STUDY_NOTES
from api.vault.view import CAPS


@dataclass(frozen=True)
class NotesSpec:
    name: str
    """The `type` tag of the block, exactly as in the schema's UIBlock union."""
    precondition: str
    supplied_by: tuple[str, ...]
    fences: Fences
    placement: PlacementHint
    version: int = 1

    @property
    def caps(self) -> dict[str, int]:
        return self.fences.caps


CONCEPT_PAGE = NotesSpec(
    name="ConceptPage",
    precondition=(
        "The vault holds a page with this id, and at least one stored passage mentions it. Every sentence shown is a verbatim "
        "span of a stored passage."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps={
            k: CAPS[k]
            for k in ("definitions", "links", "claims", "mentions", "aliases", "label_chars")
        },
        grounding="vault_rederived",
        a11y=(
            A11yRequirement("region", "Definitions"),
            A11yRequirement("region", "Links"),
            A11yRequirement("region", "Claims"),
            A11yRequirement("region", "Mentions"),
        ),
    ),
    placement=PlacementHint(panel="chat", priority=10),
)

NOTES_GRAPH = NotesSpec(
    name="NotesGraph",
    precondition=(
        "The vault holds at least one page that matches the query (or the focus page). A focused graph shows that page and the "
        "pages linked to it; the overview shows the most linked pages."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps={k: CAPS[k] for k in ("nodes", "edges", "label_chars")},
        grounding="vault_rederived",
        a11y=(A11yRequirement("group", "Page graph"), A11yRequirement("region", "Pages")),
    ),
    placement=PlacementHint(panel="studio", priority=20),
)

QUIZ_CARD = NotesSpec(
    name="QuizCard",
    precondition=(
        "The vault holds claims, and at least one names a page whose name occurs literally in the claim's sentence and has at "
        "least three fair distractors (pages of its kind in two or more passages, not a paper's title, not in the sentence, not made of the same words). Every sentence is a "
        "verbatim span of a stored passage; the block never carries the answer."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps={"items": MAX_ITEMS, "options": OPTION_COUNT, "label_chars": CAPS["label_chars"]},
        grounding="vault_rederived",
        a11y=(A11yRequirement("region", "Quiz questions"), A11yRequirement("group", "Answer choices")),
    ),
    placement=PlacementHint(panel="chat", priority=10),
)

STUDY_SET = NotesSpec(
    name="StudySet",
    precondition=(
        "The vault holds at least one concept page with a stored definition or claim (for a Socratic set, a page with an asserted "
        "link whose evidence sentence is a verbatim span of a stored passage). Every sentence shown is a verbatim span of a stored "
        "passage and is cited; no prompt or hint contains a sentence it withholds."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps={"items": STUDY_ITEMS, "notes": STUDY_NOTES, "label_chars": CAPS["label_chars"]},
        grounding="vault_rederived",
        a11y=(A11yRequirement("region", "Study items"), A11yRequirement("group", "Rate yourself")),
    ),
    placement=PlacementHint(panel="chat", priority=18),
)

STUDY_PLAN = NotesSpec(
    name="StudyPlan",
    precondition=(
        "The learner has rated at least one page that the vault holds. Each item is a rated page with its mastery and the whole days "
        "since its last rating; when it is due follows a fixed rule over those two numbers."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps={"items": PLAN_ITEMS, "label_chars": CAPS["label_chars"]},
        grounding="vault_rederived",
        a11y=(A11yRequirement("region", "Review schedule"),),
    ),
    placement=PlacementHint(panel="chat", priority=19),
)

DOC_BRIEF = NotesSpec(
    name="DocBrief",
    precondition=(
        "The store holds the document, and the vault holds at least one claim or definition from it that is a verbatim span of a stored "
        "passage of that document. Every sentence shown is cited; the next steps follow a fixed rule over the learner's mastery."
    ),
    supplied_by=("vault",),
    fences=Fences(
        caps=brief_caps(),
        grounding="vault_rederived",
        a11y=(
            A11yRequirement("region", "Key points"),
            A11yRequirement("region", "Key terms"),
            A11yRequirement("region", "Next steps"),
        ),
    ),
    placement=PlacementHint(panel="chat", priority=17),
)

NOTES_CATALOG: dict[str, NotesSpec] = {
    s.name: s for s in (CONCEPT_PAGE, NOTES_GRAPH, QUIZ_CARD, STUDY_SET, STUDY_PLAN, DOC_BRIEF)
}
