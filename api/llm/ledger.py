"""The spend ledger: every paid call is written here, and the monthly cap is enforced from it.

The ledger owns its own table in the shared SQLite file (it is not part of DocStore). Callers go
through reserve() then settle(): reserve() refuses, before anything is sent, if the month's recorded
spend plus calls already in flight plus this call's worst case would exceed the cap. Embeddings use
the same ledger as LLM calls (constraint 8).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Column, Engine, Float, Integer, MetaData, String, Table, func, insert, select

from api.core.errors import SpendCapExceeded
from api.core.logging import get_logger

log = get_logger(__name__)

metadata = MetaData()

spend_ledger = Table(
    "spend_ledger",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String, nullable=False),
    Column("month", String, nullable=False, index=True),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("tokens_in", Integer, nullable=False),
    Column("tokens_out", Integer, nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("purpose", String, nullable=False),
    Column("status", String, nullable=False),  # "ok" or "failed" (failed attempts cost nothing)
)


@dataclass(frozen=True)
class Reservation:
    estimate_usd: float


class SpendLedger:
    def __init__(
        self,
        engine: Engine,
        monthly_cap_usd: float | None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._engine = engine
        self._cap = monthly_cap_usd
        self._clock = clock
        self._lock = threading.Lock()
        self._pending = 0.0
        metadata.create_all(engine)

    def month_total(self) -> float:
        month = self._clock().strftime("%Y-%m")
        with self._engine.connect() as conn:
            total = conn.execute(
                select(func.coalesce(func.sum(spend_ledger.c.cost_usd), 0.0)).where(
                    spend_ledger.c.month == month
                )
            ).scalar_one()
        return float(total)

    def remaining_usd(self) -> float | None:
        """Cap minus this month's spend and in-flight reservations; None when there is no cap."""
        if self._cap is None:
            return None
        with self._lock:
            return max(self._cap - self.month_total() - self._pending, 0.0)

    def reserve(self, estimate_usd: float) -> Reservation:
        """Claim budget for one call, or raise SpendCapExceeded. Call before the provider."""
        with self._lock:
            if self._cap is not None:
                spent = self.month_total()
                if spent + self._pending + estimate_usd > self._cap:
                    log.warning(
                        "spend_cap_refused",
                        cap_usd=self._cap,
                        spent_usd=round(spent, 6),
                        in_flight_usd=round(self._pending, 6),
                        estimate_usd=round(estimate_usd, 6),
                    )
                    raise SpendCapExceeded(
                        f"Monthly LLM cap of ${self._cap:.2f} would be exceeded "
                        f"(${spent:.4f} spent this month, this call may cost up to "
                        f"${estimate_usd:.4f}). The call was not sent."
                    )
            self._pending += estimate_usd
            return Reservation(estimate_usd)

    def settle(
        self,
        reservation: Reservation,
        *,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        purpose: str,
        status: str = "ok",
    ) -> None:
        """Release the reservation and record what actually happened."""
        now = self._clock()
        with self._lock:
            self._pending = max(self._pending - reservation.estimate_usd, 0.0)
            with self._engine.begin() as conn:
                conn.execute(
                    insert(spend_ledger).values(
                        ts=now.isoformat(),
                        month=now.strftime("%Y-%m"),
                        provider=provider,
                        model=model,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost_usd=cost_usd,
                        purpose=purpose,
                        status=status,
                    )
                )
        log.info(
            "spend_recorded",
            provider=provider,
            model=model,
            purpose=purpose,
            status=status,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost_usd, 6),
        )

    def rows(self) -> list[dict]:
        with self._engine.connect() as conn:
            result = conn.execute(select(spend_ledger).order_by(spend_ledger.c.id))
            return [dict(r._mapping) for r in result]
