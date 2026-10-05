"""Deterministic stand-in for the extraction LLM (ARCANA_LLM_MODE=fake). Costs nothing.

Reads the passage out of the prompt, takes the distinct capitalised terms as entities and links
consecutive ones, so chunks that mention the same term share a graph node, as they would with a
real model. Not a model of anything: it exists so the pipeline runs end to end without a key.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise

from api.ingestion.extract import PASSAGE_CLOSE, PASSAGE_OPEN
from api.llm.types import LLMRequest

# A capitalised word, optionally followed by more capitalised words or acronyms ("Reciprocal Rank Fusion").
_TERM_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}(?:[ -][A-Z][A-Za-z0-9]+)*")
_MAX_TERMS = 6


def fake_extraction_responder(request: LLMRequest) -> str:
    prompt = request.prompt
    start, end = prompt.find(PASSAGE_OPEN), prompt.rfind(PASSAGE_CLOSE)
    passage = prompt[start + len(PASSAGE_OPEN) : end] if start != -1 and end > start else prompt

    terms: list[str] = []
    for match in _TERM_RE.findall(passage):
        if match not in terms:
            terms.append(match)
        if len(terms) == _MAX_TERMS:
            break

    entities = [{"label": t, "type": "concept"} for t in terms]
    relationships = [
        {"src": a, "dst": b, "type": "related to"} for a, b in pairwise(terms)
    ]
    return json.dumps({"entities": entities, "relationships": relationships})
