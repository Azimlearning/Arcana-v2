"""POST /ingest: upload one PDF. The request is multipart/form-data; the response is IngestResponse.

An upload that cannot be ingested (not a PDF, no text, a failed model call) still answers 200 with
status "failed" and the reason: the request itself was well formed. A malformed request (no file,
wrong type, too large) is a 400 with the error envelope.
"""

from fastapi import APIRouter, Request, UploadFile

from api.core.errors import BadRequest
from api.genui.generated import IngestResponse
from api.ingestion.pipeline import ingest_pdf
from api.ingestion.types import doc_id_for

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_PDF_MAGIC = b"%PDF-"


@router.post("/ingest")
async def ingest(file: UploadFile, request: Request) -> IngestResponse:
    container = request.app.state.container
    name = file.filename or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        raise BadRequest("Only PDF files can be ingested.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise BadRequest(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not raw.startswith(_PDF_MAGIC):
        raise BadRequest("The file does not look like a PDF.")

    result = await ingest_pdf(raw, name, container.ingest_deps)
    if result.status == "ready":  # keep the original beside the stores, named by its content hash
        container.uploads_dir.mkdir(parents=True, exist_ok=True)
        (container.uploads_dir / f"{doc_id_for(raw)}.pdf").write_bytes(raw)
    return IngestResponse(
        docId=result.doc_id,
        title=result.title,
        status="ready" if result.status == "ready" else "failed",
        chunkCount=result.chunk_count,
        error=result.error,
    )
