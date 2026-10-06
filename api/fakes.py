"""One responder for fake LLM mode: dispatch on the request's purpose to the matching fake."""

from api.agents.fakes import fake_research_responder, fake_route_responder
from api.ingestion.fakes import fake_extraction_responder
from api.llm.providers.fake import _echo
from api.llm.types import LLMRequest


def fake_llm_responder(request: LLMRequest) -> str:
    if request.purpose == "extract":
        return fake_extraction_responder(request)
    if request.purpose == "research":
        return fake_research_responder(request)
    if request.purpose == "route":
        return fake_route_responder(request)
    return _echo(request)
