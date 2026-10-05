from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from api.core.budget import TokenBudget
from api.core.errors import BadRequest, BudgetExhausted, ProviderUnavailable, SpendCapExceeded
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.llm.types import LLMRequest


def make_ledger(tmp_path: Path, cap: float | None = None, clock=None) -> SpendLedger:
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}")
    if clock is None:
        return SpendLedger(engine, cap)
    return SpendLedger(engine, cap, clock)


def req() -> LLMRequest:
    return LLMRequest(prompt="hello world", purpose="test", max_tokens=100)


# A fake named "anthropic" prices like Anthropic (standard tier, $2/$10 per MTok), so the cap has
# real numbers to count. One req() reserves about $0.001 and settles at about $0.00005.


async def test_fake_call_is_recorded_and_free(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    result = await LLMService(FakeProvider(), None, ledger).complete(req())
    assert result.provider == "fake" and result.cost_usd == 0.0 and not result.fell_back
    rows = ledger.rows()
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["purpose"] == "test"


async def test_primary_failure_uses_fallback_and_records_both_attempts(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    primary = FakeProvider(name="anthropic", fail_with="rate_limit")
    fallback = FakeProvider(name="openrouter")
    result = await LLMService(primary, fallback, ledger).complete(req())
    assert result.provider == "openrouter" and result.fell_back
    assert len(primary.calls) == 1 and len(fallback.calls) == 1
    assert [(r["provider"], r["status"]) for r in ledger.rows()] == [
        ("anthropic", "failed"),
        ("openrouter", "ok"),
    ]
    assert ledger.rows()[0]["cost_usd"] == 0.0


async def test_every_successful_call_writes_one_row(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    service = LLMService(FakeProvider(), None, ledger)
    for _ in range(3):
        await service.complete(req())
    assert [r["status"] for r in ledger.rows()] == ["ok", "ok", "ok"]


async def test_all_providers_failing_raises_provider_unavailable(tmp_path: Path):
    service = LLMService(
        FakeProvider(name="anthropic", fail_with="timeout"),
        FakeProvider(name="openrouter", fail_with="status_500"),
        make_ledger(tmp_path),
    )
    with pytest.raises(ProviderUnavailable) as exc:
        await service.complete(req())
    assert exc.value.to_envelope().retryable is True


async def test_call_over_the_cap_is_refused_before_the_provider_is_invoked(tmp_path: Path):
    ledger = make_ledger(tmp_path, cap=0.0000001)
    provider = FakeProvider(name="anthropic")
    with pytest.raises(SpendCapExceeded):
        await LLMService(provider, None, ledger).complete(req())
    assert provider.calls == []
    assert ledger.rows() == []


async def test_cap_counts_spend_already_recorded(tmp_path: Path):
    # Reserve ~$0.001008 per call, settle ~$0.000066. Cap $0.0011: calls 1 and 2 fit
    # (0.000066 + 0.001008 <= 0.0011); call 3 does not (0.000132 + 0.001008 > 0.0011).
    ledger = make_ledger(tmp_path, cap=0.0011)
    provider = FakeProvider(name="anthropic")
    service = LLMService(provider, None, ledger)
    await service.complete(req())
    await service.complete(req())
    with pytest.raises(SpendCapExceeded) as exc:
        await service.complete(req())
    assert len(provider.calls) == 2
    assert exc.value.to_envelope().code == "spend_cap_exceeded"


async def test_a_new_month_starts_a_fresh_total(tmp_path: Path):
    now = {"t": datetime(2026, 9, 30, tzinfo=UTC)}
    ledger = make_ledger(tmp_path, cap=0.0015, clock=lambda: now["t"])
    service = LLMService(FakeProvider(name="anthropic"), None, ledger)
    await service.complete(req())
    assert ledger.month_total() > 0
    now["t"] = datetime(2026, 10, 1, tzinfo=UTC)
    assert ledger.month_total() == 0.0
    await service.complete(req())


async def test_failed_attempt_releases_its_reservation(tmp_path: Path):
    # Cap fits one reservation at a time. If the failed primary attempt kept its reservation, the
    # fallback's would be refused.
    ledger = make_ledger(tmp_path, cap=0.0015)
    service = LLMService(
        FakeProvider(name="anthropic", fail_with="timeout"),
        FakeProvider(name="openrouter"),
        ledger,
    )
    result = await service.complete(req())
    assert result.fell_back


async def test_turn_budget_refuses_before_sending(tmp_path: Path):
    provider = FakeProvider()
    service = LLMService(provider, None, make_ledger(tmp_path))
    with pytest.raises(BudgetExhausted):
        await service.complete(req(), TokenBudget(limit=50))
    assert provider.calls == []


async def test_turn_budget_is_charged_with_actual_usage(tmp_path: Path):
    service = LLMService(FakeProvider(), None, make_ledger(tmp_path))
    budget = TokenBudget(limit=10_000)
    result = await service.complete(req(), budget)
    assert budget.used == result.tokens_in + result.tokens_out > 0


async def test_max_output_is_validated(tmp_path: Path):
    service = LLMService(FakeProvider(), None, make_ledger(tmp_path))
    with pytest.raises(BadRequest):
        await service.complete(LLMRequest(prompt="x", purpose="t", max_tokens=0))
    with pytest.raises(BadRequest):
        await service.complete(LLMRequest(prompt="x", purpose="t", max_tokens=1_000_000))
