"""GET /workspace: the prebuilt workspace, shown before any question is asked (D-28).

The user first sees the Basic layout with the list of their sources, not an empty screen. The Composer builds it
(it is the only builder of blocks): a `SourceList` of the stored documents and the fixed prebuilt layout that places
it. No model call and no retrieval, so it is free and instant. Everything is validated before it is sent and it
fails closed: a block or layout that does not pass is an error envelope, never half a workspace.
"""

from fastapi import APIRouter, Request

from api.agents.compose import compose_workspace
from api.genui.generated import WorkspaceResponse

router = APIRouter()


@router.get("/workspace")
async def workspace(request: Request) -> WorkspaceResponse:
    layout, blocks = compose_workspace(request.app.state.container.docs)
    return WorkspaceResponse(layout=layout, blocks=blocks)
