"""Model ids per provider and tier (D-08: heavy, standard, light).

Anthropic ids are from the current model table (2026-09). OpenRouter ids are ASSUMED to follow its
dotted naming ("anthropic/claude-sonnet-5.5"); its public model list did not show the sonnet and
haiku entries when checked on 2026-10-05, so task 10's live run is where these get confirmed.
"""

from __future__ import annotations

from api.llm.types import Tier

ANTHROPIC_MODELS: dict[Tier, str] = {
    "heavy": "claude-opus-5-5",
    "standard": "claude-sonnet-5-5",
    "light": "claude-haiku-4-5",
}

OPENROUTER_MODELS: dict[Tier, str] = {
    "heavy": "anthropic/claude-opus-5.5",
    "standard": "anthropic/claude-sonnet-5.5",
    "light": "anthropic/claude-haiku-4.5",
}
