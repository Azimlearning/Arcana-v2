"""Cost estimates, in USD, used to enforce the monthly cap before a call is sent.

Prices are per million tokens (input, output), first-party Anthropic rates as of 2026-09. OpenRouter
serves the same models, so its ids are normalised onto the same table; when OpenRouter reports its
own cost for a call, that figure is what the ledger records. Estimates are deliberately
conservative: input tokens are over-counted and output is assumed to run to max_tokens.
"""

from __future__ import annotations

import math
import re

from api.llm.types import LLMRequest

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# An unknown model is priced as the most expensive one, so a typo can only over-reserve.
_FALLBACK_PRICE = max(PRICES_PER_MTOK.values())

FREE_PROVIDERS = frozenset({"fake"})

# ASSUMED: $0.13 per million tokens for text-embedding-3-large. The OpenAI reference page does not
# state a price; confirm against the pricing page before the first live run (P0 task 10).
EMBEDDING_PRICES_PER_MTOK: dict[str, float] = {"text-embedding-3-large": 0.13}


def embedding_cost_usd(model: str, tokens: int) -> float:
    # An unknown embedding model is priced as the dearest known one: a typo can only over-reserve.
    price = EMBEDDING_PRICES_PER_MTOK.get(model, max(EMBEDDING_PRICES_PER_MTOK.values()))
    return tokens * price / 1_000_000


def estimate_embedding_tokens(texts: list[str]) -> int:
    """About one token per 3 characters, as for LLM input: errs toward refusing."""
    return math.ceil(sum(len(t) for t in texts) / 3)


_DATE_SUFFIX = re.compile(r"-\d{8}$")


def _normalise(model: str) -> str:
    """An alias for a model id: no provider prefix, dots as dashes, no dated-snapshot suffix. The API may
    echo the dated id ("claude-haiku-4-5-20251001") for the alias that was requested; without this it
    would miss the table and be priced as the dearest model."""
    return _DATE_SUFFIX.sub("", model.removeprefix("anthropic/").replace(".", "-"))


def price_for(provider: str, model: str) -> tuple[float, float]:
    if provider in FREE_PROVIDERS:
        return (0.0, 0.0)
    return PRICES_PER_MTOK.get(_normalise(model), _FALLBACK_PRICE)


def estimate_input_tokens(request: LLMRequest) -> int:
    """About one token per 3 characters: higher than the usual ~4, so it errs toward refusing."""
    chars = len(request.prompt) + len(request.system or "")
    return math.ceil(chars / 3)


def cost_usd(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = price_for(provider, model)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def estimate_call_cost(provider: str, model: str, request: LLMRequest) -> float:
    """Worst case: the estimated input plus an output that fills max_tokens."""
    return cost_usd(provider, model, estimate_input_tokens(request), request.max_tokens)
