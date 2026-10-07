"""The lab endpoint (P4 V4, D-36): POST /labs.

`POST /labs {contractId}` makes a lab from one of the server's contracts and answers with a workspace body (a layout and blocks), like the
notes and quiz views. Everything goes through `compose_lab`: the evidence precondition, the (untrusted) generator, the checker, the
verifier, the mint, the store and the block validator. The block carries the verified source as inert data; the web host renders it in a
sandboxed iframe after checking its hash. A contract the server does not know is a 404 `not_found`; a lab that does not pass is an `error`
block that names the stage; the documents not stating the formula is an `empty` block. No model call while the generator is the fake.
"""

from fastapi import APIRouter, Request

from api.agents.compose import compose_lab
from api.genui.generated import LabRequest, WorkspaceResponse

router = APIRouter()


@router.post("/labs")
def make_lab(body: LabRequest, request: Request) -> WorkspaceResponse:
    container = request.app.state.container
    layout, blocks = compose_lab(
        container.docs, container.lab_store, container.lab_generator, body.contractId
    )
    return WorkspaceResponse(layout=layout, blocks=blocks)
