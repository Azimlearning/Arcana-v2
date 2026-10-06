"""Findings of the pre-live cost audit (2026-10-06), each pinned by a test: what the ledger prices a call at,
where the ledger lives, when a cap is required, and that no paid call can escape or leak the ledger."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from api.container import build_container
from api.core.settings import ConfigError, Settings, load_settings
from api.ingestion import pipeline
from api.ingestion.embed import OpenAIEmbedder
from api.ingestion.pipeline import ingest_pdf
from api.llm.ledger import SpendLedger
from api.llm.pricing import cost_usd, price_for
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.llm.types import LLMRequest, ProviderResponse

# ── pricing: a dated snapshot id must not be priced as the dearest model ──────


@pytest.mark.parametrize(
    "model",
    ["claude-haiku-4-5", "claude-haiku-4-5-20251001", "anthropic/claude-haiku-4.5", "anthropic/claude-haiku-4-5-20251001"],
)
def test_every_spelling_of_haiku_is_priced_as_haiku(model: str):
    assert price_for("anthropic", model) == (1.0, 5.0)


def test_an_unknown_model_is_still_priced_as_the_dearest():
    assert price_for("anthropic", "claude-mystery-9") == (4.0, 20.0)  # a typo can only over-reserve


class Echo:
    """A provider that answers with a different model id than the one requested, as an API may."""

    def __init__(self, echoed: str, reported_cost: float | None = None, name: str = "anthropic"):
        self.name, self._echoed, self._reported = name, echoed, reported_cost

    def model_for(self, tier: str) -> str:
        return "claude-haiku-4-5"

    async def complete(self, request: LLMRequest, model: str) -> ProviderResponse:
        return ProviderResponse("ok", self._echoed, 1_000_000, 1_000_000, self._reported)


def ledger_in(tmp_path: Path, cap: float | None = None) -> SpendLedger:
    return SpendLedger(create_engine(f"sqlite:///{tmp_path / 'l.db'}"), cap)


REQ = LLMRequest(prompt="hi", purpose="test", tier="light", max_tokens=10)


async def test_the_call_is_priced_by_the_model_requested_not_the_id_echoed_back(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    result = await LLMService(Echo("some-id-the-table-has-never-seen"), None, ledger).complete(REQ)
    assert result.cost_usd == cost_usd("anthropic", "claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0  # not $24
    (row,) = ledger.rows()
    assert row["model"] == "some-id-the-table-has-never-seen"  # what was echoed is still recorded, for the record


async def test_a_reported_cost_below_the_estimate_is_booked_at_the_estimate(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    result = await LLMService(Echo("claude-haiku-4-5", reported_cost=0.0, name="openrouter"), None, ledger).complete(REQ)
    assert result.cost_usd == 6.0  # a bring-your-own-key route that reports 0 still costs money


async def test_a_reported_cost_above_the_estimate_is_kept(tmp_path: Path):
    ledger = ledger_in(tmp_path)
    result = await LLMService(Echo("claude-haiku-4-5", reported_cost=9.5, name="openrouter"), None, ledger).complete(REQ)
    assert result.cost_usd == 9.5


# ── a cap is required whenever anything paid is live ──────────────────────────


def test_live_embeddings_with_a_fake_llm_still_need_a_cap():
    s = Settings(_env_file=None, arcana_embed_mode="live", openai_api_key="k")  # pyright: ignore[reportCallIssue]
    assert [n for n, _ in s.missing_for_mode()] == ["LLM_MONTHLY_CAP_USD"]
    ok = Settings(_env_file=None, arcana_embed_mode="live", openai_api_key="k", llm_monthly_cap_usd=5)  # pyright: ignore[reportCallIssue]
    assert ok.missing_for_mode() == []


def test_the_cap_must_be_positive_for_live_embeddings(monkeypatch: pytest.MonkeyPatch):
    for name, value in {"ARCANA_EMBED_MODE": "live", "OPENAI_API_KEY": "k", "LLM_MONTHLY_CAP_USD": "0"}.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError):
        load_settings(env_file=None)


# ── the ledger is one file in a live mode, whatever the data directory ────────


def live_settings(data: Path, **extra) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        arcana_llm_mode="live",
        arcana_embed_mode="live",
        anthropic_api_key="a",
        openrouter_api_key="o",
        openai_api_key="k",
        llm_monthly_cap_usd=5,
        arcana_data_dir=data,
        **extra,
    )


def test_in_live_mode_two_data_directories_share_one_ledger_and_one_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    api = build_container(live_settings(tmp_path / "data"))
    eval_run = build_container(live_settings(tmp_path / "data" / "eval-live-live"))
    reservation = api.ledger.reserve(0.01)
    api.ledger.settle(reservation, provider="anthropic", model="m", tokens_in=1, tokens_out=1, cost_usd=1.25, purpose="t")
    assert eval_run.ledger.month_total() == pytest.approx(1.25)  # the eval sees what the API spent
    assert (tmp_path / "data" / "ledger.db").exists()


def test_deleting_a_data_directory_does_not_erase_the_spend_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    first = build_container(live_settings(tmp_path / "scratch"))
    first.ledger.settle(first.ledger.reserve(0.01), provider="a", model="m", tokens_in=1, tokens_out=1, cost_usd=2.0, purpose="t")
    first.engine.dispose()
    again = build_container(live_settings(tmp_path / "a-different-clean-dir"))  # "start clean"
    assert again.ledger.month_total() == pytest.approx(2.0)


def test_in_fake_mode_the_ledger_stays_beside_the_data_so_tests_stay_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    one = build_container(Settings(_env_file=None, arcana_data_dir=tmp_path / "one"))  # pyright: ignore[reportCallIssue]
    two = build_container(Settings(_env_file=None, arcana_data_dir=tmp_path / "two"))  # pyright: ignore[reportCallIssue]
    one.ledger.settle(one.ledger.reserve(0.0), provider="fake", model="m", tokens_in=0, tokens_out=0, cost_usd=0.5, purpose="t")
    assert two.ledger.month_total() == 0.0 and not (tmp_path / "data" / "ledger.db").exists()


def test_an_explicit_ledger_path_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    where = tmp_path / "elsewhere" / "spend.db"
    build_container(live_settings(tmp_path / "d", arcana_ledger_path=where))
    assert where.exists() and not (tmp_path / "data" / "ledger.db").exists()


# ── a cancelled embedding request releases its reservation ────────────────────


async def test_a_cancelled_embedding_request_releases_its_reservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ledger = ledger_in(tmp_path, cap=1.0)
    embedder = OpenAIEmbedder("k", ledger, backoff_s=0)

    async def cancelled(batch):
        raise asyncio.CancelledError

    monkeypatch.setattr(embedder, "_request", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await embedder.embed(["some text"])
    assert ledger.remaining_usd() == pytest.approx(1.0)  # nothing left in flight
    assert [r["status"] for r in ledger.rows()] == ["failed"]


def test_remaining_usd_is_the_cap_less_spend_and_in_flight(tmp_path: Path):
    assert ledger_in(tmp_path).remaining_usd() is None  # no cap, no limit
    ledger = ledger_in(tmp_path, cap=5.0)
    held = ledger.reserve(1.0)
    assert ledger.remaining_usd() == pytest.approx(4.0)
    ledger.settle(held, provider="a", model="m", tokens_in=1, tokens_out=1, cost_usd=0.5, purpose="t")
    assert ledger.remaining_usd() == pytest.approx(4.5)


# ── one upload cannot spend the month's cap ───────────────────────────────────


async def test_a_document_over_the_chunk_limit_is_refused_before_any_paid_call(pdf_bytes, make_deps, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_CHUNKS_PER_DOC", 2)  # the fixture has 4
    provider = FakeProvider()
    deps = make_deps(provider=provider)
    result = await ingest_pdf(pdf_bytes, "x.pdf", deps)
    assert result.status == "failed" and "limit is 2" in (result.error or "")
    assert provider.calls == [] and deps.vectors.count() == 0


async def test_a_document_that_could_exceed_the_remaining_cap_is_refused_up_front(pdf_bytes, make_deps):
    provider = FakeProvider()
    deps = make_deps(provider=provider, cap=0.001)  # far below the worst case for 4 chunks
    result = await ingest_pdf(pdf_bytes, "x.pdf", deps)
    assert result.status == "failed" and "monthly cap" in (result.error or "") and "Nothing was sent" in (result.error or "")
    assert provider.calls == [] and deps.vectors.count() == 0
    assert deps.docs.chunks_for_document(result.doc_id) == []  # nothing half-ingested


async def test_a_document_that_fits_the_remaining_cap_ingests_normally(pdf_bytes, make_deps):
    result = await ingest_pdf(pdf_bytes, "x.pdf", make_deps(cap=10.0))
    assert result.status == "ready"
