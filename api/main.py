"""FastAPI app. `uv run uvicorn api.main:app --reload`.

Importing this module has no side effects: settings are loaded and stores opened in the startup
lifespan, so a missing key fails loudly there (naming the variable), not at import.

Every failure that leaves this app is an ErrorEnvelope, including the ones Starlette raises itself
(404, 405) and unexpected exceptions (500, which also carry CORS headers so a browser can read them).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from api.container import build_container
from api.core.errors import HTTP_STATUS, ArcanaError, envelope_from_exception
from api.core.logging import configure_logging, get_logger
from api.core.settings import Settings, load_settings
from api.genui.generated import ErrorCode, ErrorEnvelope, FieldIssue
from api.routes import chat, ingest, patterns, trace, vault, workspace

log = get_logger(__name__)

# Local development: the Next.js dev server. A deployed host would add its origin (D-13).
WEB_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# Declared Content-Length limits, checked before the body is read. A chunked body without a
# Content-Length is not caught here; the route still bounds what it keeps.
MAX_BODY_BYTES = {"/chat": 512 * 1024, "/ingest": ingest.MAX_UPLOAD_BYTES + 1024 * 1024, "/patterns": 16 * 1024}


def _envelope(code: ErrorCode, message: str, issues: list[FieldIssue] | None = None) -> ErrorEnvelope:
    return ErrorEnvelope(code=code, message=message, issues=issues or [], retryable=False)


def _json_error(
    envelope: ErrorEnvelope, status: int | None = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(envelope.model_dump(), status_code=status or HTTP_STATUS[envelope.code], headers=headers)


class BodyLimit:
    """Reject a request whose declared Content-Length exceeds its path's limit, before any parsing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            limit = MAX_BODY_BYTES.get(scope["path"])
            declared = dict(scope["headers"]).get(b"content-length")
            if limit is not None and declared is not None and declared.isdigit() and int(declared) > limit:
                response = _json_error(_envelope("bad_request", "The request body is too large."), 413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        loaded = settings or load_settings()
        configure_logging(loaded.log_level)
        app.state.container = build_container(loaded)
        log.info("started", llm_mode=loaded.arcana_llm_mode, embed_mode=loaded.arcana_embed_mode)
        yield

    app = FastAPI(title="Arcana v2", lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.add_middleware(
        CORSMiddleware, allow_origins=WEB_ORIGINS, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"]
    )

    @app.exception_handler(ArcanaError)
    async def arcana_error(_: Request, exc: ArcanaError) -> JSONResponse:
        return _json_error(exc.to_envelope())

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code: ErrorCode = (
            "not_found" if exc.status_code == 404 else ("bad_request" if exc.status_code < 500 else "internal")
        )
        message = {404: "Not found.", 405: "Method not allowed."}.get(
            exc.status_code, "The request could not be handled."
        )
        return _json_error(_envelope(code, message), exc.status_code, dict(exc.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def bad_request_shape(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            FieldIssue(
                # A body that is not JSON at all has no field to point at; the loc is a byte offset.
                path="(body)" if e["type"] == "json_invalid" else ".".join(str(p) for p in e["loc"][1:]) or "(body)",
                message=e["msg"],
            )
            for e in exc.errors()
        ]
        return _json_error(_envelope("validation_failed", "The request is malformed.", issues))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled", error=type(exc).__name__)
        headers: dict[str, str] = {}
        origin = request.headers.get("origin")
        if origin in WEB_ORIGINS:  # this handler runs outside CORSMiddleware, so add the header here
            headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        return _json_error(envelope_from_exception(exc), headers=headers)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat.router)
    app.include_router(ingest.router)
    app.include_router(trace.router)
    app.include_router(workspace.router)
    app.include_router(patterns.router)
    app.include_router(vault.router)
    return app


app = create_app()
