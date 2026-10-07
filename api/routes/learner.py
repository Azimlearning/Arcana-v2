"""The learner layer's endpoints (M2.7, D-35 A6): POST /learner/events and DELETE /learner.

A learner event is a page of the vault and a self-rating (`know`, `unsure`, `dont_know`); quiz results will join as the same kind of
event once the Studio generators exist. The page id must be a page the vault holds (a 404 `not_found` envelope otherwise), so the
store never accumulates events about nothing. The response is the page's mastery after the event. The data is personal: events
only, no document text, kept in `learner.db`, and `DELETE /learner` removes all of it. No model call and nothing paid.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from api.core.errors import NotFound
from api.genui.generated import LearnerEventRequest, LearnerEventResponse, Mastery
from api.learner.mastery import LearnerEvent, mastery_of

router = APIRouter()


@router.post("/learner/events")
def record_event(body: LearnerEventRequest, request: Request) -> LearnerEventResponse:
    container = request.app.state.container
    vault = container.vault()
    if vault is None or body.pageId not in vault.pages:
        raise NotFound(f"The vault has no page {body.pageId!r}.")
    now = datetime.now(UTC)
    container.learner_store.record(LearnerEvent(body.pageId, body.signal, now))
    score = mastery_of(container.learner_store.events(body.pageId), now)
    assert score is not None  # an event was just recorded
    return LearnerEventResponse(pageId=body.pageId, mastery=Mastery(score=score.score, events=score.events))


@router.delete("/learner", status_code=204)
def forget(request: Request) -> Response:
    request.app.state.container.learner_store.delete_all()
    return Response(status_code=204)
