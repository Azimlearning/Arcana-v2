"""Parse a JSON object out of a model reply, tolerating a markdown fence or surrounding prose."""

from __future__ import annotations

import json
import re


def parse_json_object(raw: str) -> dict:
    """The outermost {...} in `raw` as a dict. Raises ValueError with a short, safe message."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    first, last = s.find("{"), s.rfind("}")
    if first == -1 or last <= first:
        raise ValueError("reply contained no JSON object")
    try:
        parsed = json.loads(s[first : last + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("reply was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("reply was not a JSON object")
    return parsed
