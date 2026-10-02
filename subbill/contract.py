from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ChangeKind(Enum):
    SET_PRICE = "set_price"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


@dataclass(frozen=True)
class Change:
    effective_at: datetime
    kind: ChangeKind
    price_cents: int | None = None


@dataclass(frozen=True)
class PeriodBill:
    period_index: int
    start_utc: datetime
    end_utc: datetime
    amount_cents: int


@dataclass
class Contract:
    tz_name: str
    start_local: datetime
    period_months: int
    initial_price_cents: int
    changes: list[Change] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.start_local.tzinfo is not None:
            raise ValueError("start_local must be naive local time")
        if self.period_months not in (1, 3, 12):
            raise ValueError("period_months must be 1, 3 or 12")
        if not isinstance(self.initial_price_cents, int) or self.initial_price_cents < 0:
            raise ValueError("initial_price_cents must be a non-negative integer")

    def add_change(self, change: Change) -> None:
        if change.effective_at.tzinfo is None:
            raise ValueError("change.effective_at must be timezone-aware UTC")
        if change.effective_at.utcoffset().total_seconds() != 0:
            raise ValueError("change.effective_at must be in UTC")
        if change.effective_at.microsecond != 0:
            raise ValueError("change.effective_at must be whole seconds")
        if change.kind is ChangeKind.SET_PRICE:
            if (
                not isinstance(change.price_cents, int)
                or change.price_cents is None
                or change.price_cents < 0
            ):
                raise ValueError("SET_PRICE requires a non-negative integer price_cents")
        elif change.price_cents is not None:
            raise ValueError("price_cents only allowed for SET_PRICE")
        if self.changes and change.effective_at < self.changes[-1].effective_at:
            raise ValueError("changes must be non-decreasing in effective_at")
        self.changes.append(change)
