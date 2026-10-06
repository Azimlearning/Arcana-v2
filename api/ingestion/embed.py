"""Embeddings (D-14): OpenAI text-embedding-3-large, 3,072-dim, behind an interface.

Live calls go through the spend ledger: each attempt reserves its worst-case cost against the monthly
cap before the request is sent, and settles with the tokens OpenAI reports (constraint 8). The fake
embedder costs nothing and records nothing.

POST https://api.openai.com/v1/embeddings, body {model, input: [str, ...]}; response
data[].{index, embedding} and usage.prompt_tokens. At most 2,048 inputs and 300,000 tokens per
request; we send 64 chunks at a time, far below both.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx

from api.core.errors import ProviderUnavailable
from api.core.logging import get_logger
from api.core.settings import Settings
from api.llm.ledger import SpendLedger
from api.llm.pricing import embedding_cost_usd, estimate_embedding_tokens

log = get_logger(__name__)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
OPENAI_URL = "https://api.openai.com/v1/embeddings"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order, each EMBEDDING_DIM long."""


class FakeEmbedder(Embedder):
    """Deterministic hashed bag-of-words. Texts that share words get similar vectors, so dense
    retrieval tests have real signal, with no network and no cost."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            vec[int.from_bytes(digest, "big") % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0], norm = 1.0, 1.0  # never a zero vector
        return [v / norm for v in vec]


class CachingEmbedder(Embedder):
    """Memoises by text. The benchmark uses it for queries, so every arm sees the identical query
    vector (no embedding jitter between arms) and a live run pays for each question only once."""

    def __init__(self, inner: Embedder):
        self._inner = inner
        self._cache: dict[str, list[float]] = {}
        self.inner_calls = 0
        """How many texts were actually sent to the wrapped embedder."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            self.inner_calls += len(missing)
            self._cache.update(zip(missing, await self._inner.embed(missing), strict=True))
        return [self._cache[t] for t in texts]


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        api_key: str,
        ledger: SpendLedger,
        *,
        client: httpx.AsyncClient | None = None,
        batch_size: int = 64,
        attempts: int = 3,
        backoff_s: float = 0.5,
    ):
        self._api_key = api_key
        self._ledger = ledger
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._batch_size = batch_size
        self._attempts = attempts
        self._backoff_s = backoff_s

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            out.extend(await self._embed_batch(list(texts[start : start + self._batch_size])))
        return out

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        estimate = embedding_cost_usd(EMBEDDING_MODEL, estimate_embedding_tokens(batch))
        last_reason = "unknown"
        for attempt in range(self._attempts):
            if attempt:
                await asyncio.sleep(self._backoff_s * 2 ** (attempt - 1))
            reservation = self._ledger.reserve(estimate)  # may raise SpendCapExceeded: nothing sent
            try:
                reason, vectors, tokens = await self._request(batch)
            except BaseException:  # cancellation or a bug: release the reservation before propagating
                self._ledger.settle(
                    reservation,
                    provider="openai",
                    model=EMBEDDING_MODEL,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    purpose="embed",
                    status="failed",
                )
                raise
            if vectors is None:
                self._ledger.settle(
                    reservation,
                    provider="openai",
                    model=EMBEDDING_MODEL,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    purpose="embed",
                    status="failed",
                )
                last_reason = reason
                log.warning("embedding_attempt_failed", reason=reason, attempt=attempt + 1)
                if reason in {"status_400", "status_401", "status_403", "bad_response"}:
                    break  # retrying cannot help
                continue
            self._ledger.settle(
                reservation,
                provider="openai",
                model=EMBEDDING_MODEL,
                tokens_in=tokens,
                tokens_out=0,
                cost_usd=embedding_cost_usd(EMBEDDING_MODEL, tokens),
                purpose="embed",
            )
            return vectors
        raise ProviderUnavailable(f"Embeddings request failed ({last_reason}).")

    async def _request(self, batch: list[str]) -> tuple[str, list[list[float]] | None, int]:
        """One HTTP attempt. Returns (failure reason, vectors or None, prompt tokens)."""
        try:
            response = await self._client.post(
                OPENAI_URL,
                json={"model": EMBEDDING_MODEL, "input": batch},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TimeoutException:
            return "timeout", None, 0
        except httpx.HTTPError:
            return "connection", None, 0
        if response.status_code == 429:
            return "rate_limit", None, 0
        if response.status_code >= 400:
            return f"status_{response.status_code}", None, 0
        try:
            data = response.json()
            rows = sorted(data["data"], key=lambda r: r["index"])
            vectors = [[float(x) for x in r["embedding"]] for r in rows]
            tokens = int(data["usage"]["prompt_tokens"])
        except (ValueError, KeyError, TypeError):
            return "bad_response", None, 0
        if len(vectors) != len(batch) or any(len(v) != EMBEDDING_DIM for v in vectors):
            return "bad_response", None, 0
        return "", vectors, tokens


def build_embedder(settings: Settings, ledger: SpendLedger) -> Embedder:
    if settings.arcana_embed_mode == "fake":
        return FakeEmbedder()
    assert settings.openai_api_key  # load_settings() guarantees it in live mode
    return OpenAIEmbedder(settings.openai_api_key.get_secret_value(), ledger)
