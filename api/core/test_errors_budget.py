import pytest

from api.core.budget import TokenBudget
from api.core.errors import (
    ArcanaError,
    BudgetExhausted,
    ProviderUnavailable,
    ValidationFailed,
    envelope_from_exception,
)
from api.genui.generated import FieldIssue


def test_arcana_error_maps_to_its_envelope():
    err = ValidationFailed("bad block", [FieldIssue(path="data.citations.0.chunkId", message="x")])
    env = err.to_envelope()
    assert env.code == "validation_failed"
    assert env.issues[0].path == "data.citations.0.chunkId"
    assert env.retryable is False


def test_provider_errors_are_retryable():
    assert ProviderUnavailable("down").to_envelope().retryable is True


def test_unexpected_exception_does_not_leak_detail():
    env = envelope_from_exception(RuntimeError("secret path C:\\Users\\x\\.env"))
    assert env.code == "internal"
    assert "secret" not in env.message
    assert env.issues == []


def test_arcana_error_base_is_internal():
    assert ArcanaError("x").to_envelope().code == "internal"


def test_budget_tracks_and_refuses_overspend():
    b = TokenBudget(limit=100)
    b.charge(60)
    assert b.remaining == 40
    assert b.can_afford(40) and not b.can_afford(41)
    with pytest.raises(BudgetExhausted) as exc:
        b.charge(41)
    assert exc.value.to_envelope().code == "budget_exhausted"


def test_budget_rejects_negative_charge():
    with pytest.raises(ValueError):
        TokenBudget(limit=10).charge(-1)
