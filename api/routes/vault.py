"""The notes view's endpoints (M2.6, D-35): GET /vault/notes and POST /vault/rebuild.

`GET /vault/notes?page=<id>&query=<text>` returns the same shape as `/workspace` (a layout and blocks): a `ConceptPage` for the
page (when one is asked for) and the `NotesGraph` around it, built by the Composer from the vault, placed by the layout and
validated by re-deriving them from the vault. No model call. A page the vault does not hold is a `not_found` envelope; with no
vault yet the graph is an `empty` placeholder. `POST /vault/rebuild` compiles the vault from the stored graph and passages
(deterministic, free) and says how large it is.
"""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from api.agents.compose import compose_notes
from api.genui.generated import WorkspaceResponse

router = APIRouter()

MAX_QUERY_CHARS = 120
MAX_PAGE_ID_CHARS = 200


class VaultRebuilt(BaseModel):
    pages: int
    asserted_links: int
    co_mention_links: int
    claims: int


@router.get("/vault/notes")
async def notes(
    request: Request,
    page: str | None = Query(default=None, max_length=MAX_PAGE_ID_CHARS),
    query: str = Query(default="", max_length=MAX_QUERY_CHARS),
) -> WorkspaceResponse:
    container = request.app.state.container
    layout, blocks = compose_notes(container.vault(), container.docs, page or None, query, container.learner_store)
    return WorkspaceResponse(layout=layout, blocks=blocks)


@router.post("/vault/rebuild")
def rebuild(request: Request) -> VaultRebuilt:
    vault = request.app.state.container.rebuild_vault()
    stats = vault.stats
    return VaultRebuilt(
        pages=len(vault.pages),
        asserted_links=int(stats.get("asserted_links", 0)),
        co_mention_links=int(stats.get("co_mention_links", 0)),
        claims=len(vault.claims),
    )
