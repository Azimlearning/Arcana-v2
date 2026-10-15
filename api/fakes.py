"""One responder for fake LLM mode: dispatch on the request's purpose to the matching fake."""

from api.agents.fakes import (
    fake_check_responder,
    fake_draft_responder,
    fake_research_responder,
    fake_route_responder,
)
from api.ingestion.atomic import ATOMIC_MARKER
from api.ingestion.atomic2 import ATOMIC2_MARKER
from api.ingestion.fakes import (
    fake_atomic2_responder,
    fake_atomic_responder,
    fake_extraction_responder,
)
from api.llm.providers.fake import _echo
from api.llm.types import LLMRequest


def fake_llm_responder(request: LLMRequest) -> str:
    if request.purpose == "extract":
        if ATOMIC2_MARKER in (request.system or ""):
            return fake_atomic2_responder(request)
        if ATOMIC_MARKER in (request.system or ""):
            return fake_atomic_responder(request)
        return fake_extraction_responder(request)
    if request.purpose == "research":
        return fake_research_responder(request)
    if request.purpose == "draft":
        return fake_draft_responder(request)
    if request.purpose == "route":
        return fake_route_responder(request)
    if request.purpose == "check":
        return fake_check_responder(request)
    return _echo(request)
