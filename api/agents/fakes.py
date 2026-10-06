"""Deterministic stand-in for the research LLM (ARCANA_LLM_MODE=fake). Costs nothing.

Reads the numbered passages out of the prompt and answers with one cited segment per passage, quoting
that passage's first sentence. When the passages come from several documents it takes the first passage
of each document (up to MAX_SEGMENTS), as a real comparison would; otherwise the leading passages. It
does not understand the question; it exists so the whole path (retrieval, citation mapping, validation,
streaming, rendering) runs without a key.
"""

import json
import re

from api.llm.types import LLMRequest

_PASSAGE = re.compile(r"^\[(\d+)\] \(([^\n]*)\)\n(.*?)(?=^\[\d+\] \(|\Z)", re.M | re.S)
_PAGE = re.compile(r", p\.\d+$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WS = re.compile(r"\s+")
MAX_SEGMENTS = 2


def fake_research_responder(request: LLMRequest) -> str:
    first_of: dict[str, tuple[str, str]] = {}  # document title -> (passage number, body) of its first passage
    leading: list[tuple[str, str]] = []
    for number, title, body in _PASSAGE.findall(request.prompt):
        first_of.setdefault(_PAGE.sub("", title), (number, body))
        leading.append((number, body))
    chosen = list(first_of.values()) if len(first_of) > 1 else leading
    segments = []
    for number, body in chosen[:MAX_SEGMENTS]:
        first = _SENTENCE.split(_WS.sub(" ", body).strip())[0][:160]
        segments.append({"text": f"The document states: {first}", "cites": [int(number)]})
    return json.dumps({"segments": segments})


def fake_check_responder(request: LLMRequest) -> str:
    """Fake mode has no judge: an empty reply gives no verdicts, so the Fact Checker's deterministic
    lexical rule decides every claim. Honest: a fake that approved everything would hide a broken check."""
    return "{}"


def fake_route_responder(request: LLMRequest) -> str:
    """Routes everything to the single-question plan, so fake mode never needs a real router."""
    return json.dumps({"intent": "single"})
