"""The quiz's answer endpoint (Q1, D-35 A8): POST /quiz/answer.

A `QuizCard` carries no answer. The server derives the item again from its id (`derive_item`), so the id must name a claim and a
page the vault still holds and the item must still be makeable; the chosen page must be one of the item's four options. Then it
records `quiz_correct` or `quiz_wrong` for the **blanked** page (never the page that was chosen) and answers with whether the
choice was right, the right page, the sentence unblanked as a citation, and the page's mastery after the event. An item id the
vault cannot derive is a 404 `not_found`, a choice that is not an option a 422 `validation_failed`; neither records anything. The
public rating route (`POST /learner/events`) still accepts only the three self-ratings. No model call, nothing paid.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from api.core.errors import NotFound, ValidationFailed
from api.genui.generated import (
    Citation,
    FieldIssue,
    Mastery,
    PageRef,
    QuizAnswerRequest,
    QuizAnswerResponse,
)
from api.learner.mastery import LearnerEvent, mastery_of
from api.vault.quiz import derive_item, source_citation
from api.vault.view import _ref

router = APIRouter()


@router.post("/quiz/answer")
def answer(body: QuizAnswerRequest, request: Request) -> QuizAnswerResponse:
    container = request.app.state.container
    vault = container.fresh_vault()
    item = None if vault is None else derive_item(vault, container.docs, body.itemId)
    if vault is None or item is None:
        raise NotFound("The vault cannot make this question.")
    if body.chosenId not in item.options:
        raise ValidationFailed(
            "The choice is not one of the question's options.",
            [FieldIssue(path="chosenId", message="not an option")],
        )
    correct = body.chosenId == item.target
    now = datetime.now(UTC)
    event = LearnerEvent(item.target, "quiz_correct" if correct else "quiz_wrong", now)
    # The reply is built from the events as they will be, and the event is recorded last: nothing that can fail comes after the
    # record, so a failed answer never leaves an event behind for a retry to record again.
    score = mastery_of([*container.learner_store.events(item.target), event], now)
    assert score is not None
    reply = QuizAnswerResponse(
        itemId=item.id,
        correct=correct,
        answer=PageRef.model_validate(_ref(vault, item.target)),
        citation=Citation.model_validate(source_citation(container.docs, item)),
        mastery=Mastery(score=score.score, events=score.events),
    )
    container.learner_store.record(event)
    return reply
