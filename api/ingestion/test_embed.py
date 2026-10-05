from pathlib import Path

import httpx
import numpy as np
import pytest
import respx
from sqlalchemy import create_engine

from api.core.errors import ProviderUnavailable, SpendCapExceeded
from api.ingestion.embed import EMBEDDING_DIM, FakeEmbedder, OpenAIEmbedder
from api.llm.ledger import SpendLedger

URL = "https://api.openai.com/v1/embeddings"


def ledger_in(tmp_path: Path, cap: float | None = None) -> SpendLedger:
    return SpendLedger(create_engine(f"sqlite:///{tmp_path / 'l.db'}"), cap)


def openai_reply(count: int, prompt_tokens: int, *, dim: int = EMBEDDING_DIM, shuffled: bool = False):
    rows = [{"object": "embedding", "index": i, "embedding": [float(i)] + [0.0] * (dim - 1)} for i in range(count)]
    if shuffled:
        rows.reverse()
    return httpx.Response(200, json={"data": rows, "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens}})


def cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ── FakeEmbedder ──────────────────────────────────────────────────────────────


async def test_fake_vectors_have_the_real_dimension_and_unit_length():
    (v,) = await FakeEmbedder().embed(["graph retrieval"])
    assert len(v) == EMBEDDING_DIM and np.linalg.norm(v) == pytest.approx(1.0, abs=1e-6)


async def test_fake_is_deterministic_and_word_sensitive():
    e = FakeEmbedder()
    a1, a2, related, unrelated = await e.embed(
        ["dense retrieval of passages", "dense retrieval of passages", "passages for dense retrieval", "zebra giraffe lion"]
    )
    assert a1 == a2
    # 3 of 4 words shared gives a cosine of 0.75; no shared words gives about 0
    assert cosine(a1, related) == pytest.approx(0.75, abs=0.01)
    assert cosine(a1, unrelated) < 0.1


async def test_fake_never_returns_a_zero_vector():
    (v,) = await FakeEmbedder().embed(["!!! ???"])
    assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-6)


# ── OpenAIEmbedder ────────────────────────────────────────────────────────────


@respx.mock
async def test_openai_embeds_in_order_and_records_spend(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    route = respx.post(URL).mock(return_value=openai_reply(3, prompt_tokens=1_000_000, shuffled=True))
    vectors = await OpenAIEmbedder("k", ledger, backoff_s=0).embed(["a", "b", "c"])
    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]  # re-ordered by "index", not arrival order
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer k"
    rows = ledger.rows()
    assert len(rows) == 1 and rows[0]["provider"] == "openai" and rows[0]["purpose"] == "embed"
    assert rows[0]["tokens_in"] == 1_000_000
    assert rows[0]["cost_usd"] == pytest.approx(0.13)  # 1M tokens at the assumed $0.13 per million


@respx.mock
async def test_openai_splits_into_batches(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    respx.post(URL).mock(side_effect=[openai_reply(2, 10), openai_reply(2, 10), openai_reply(1, 5)])
    vectors = await OpenAIEmbedder("k", ledger, batch_size=2, backoff_s=0).embed(list("abcde"))
    assert len(vectors) == 5 and len(ledger.rows()) == 3


@respx.mock
async def test_openai_retries_a_rate_limit_then_succeeds(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    respx.post(URL).mock(side_effect=[httpx.Response(429), openai_reply(1, 7)])
    await OpenAIEmbedder("k", ledger, backoff_s=0).embed(["a"])
    assert [r["status"] for r in ledger.rows()] == ["failed", "ok"]
    assert ledger.rows()[0]["cost_usd"] == 0.0


@respx.mock
async def test_openai_gives_up_after_its_attempts(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    route = respx.post(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderUnavailable) as exc:
        await OpenAIEmbedder("k", ledger, backoff_s=0).embed(["a"])
    assert route.call_count == 3 and "status_503" in exc.value.message
    assert [r["status"] for r in ledger.rows()] == ["failed"] * 3


@respx.mock
async def test_openai_does_not_retry_a_rejected_key(tmp_path: Path):
    route = respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderUnavailable):
        await OpenAIEmbedder("k", ledger_in(tmp_path), backoff_s=0).embed(["a"])
    assert route.call_count == 1


@respx.mock
async def test_openai_rejects_a_wrong_dimension(tmp_path: Path):
    respx.post(URL).mock(return_value=openai_reply(1, 5, dim=8))
    with pytest.raises(ProviderUnavailable):
        await OpenAIEmbedder("k", ledger_in(tmp_path), backoff_s=0).embed(["a"])


@respx.mock
async def test_openai_over_the_cap_is_refused_before_anything_is_sent(tmp_path: Path):
    route = respx.post(URL).mock(return_value=openai_reply(1, 5))
    ledger = ledger_in(tmp_path, cap=1e-12)
    with pytest.raises(SpendCapExceeded):
        await OpenAIEmbedder("k", ledger, backoff_s=0).embed(["some text to embed"])
    assert not route.called and ledger.rows() == []
