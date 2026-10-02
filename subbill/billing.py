from __future__ import annotations

import calendar
from datetime import datetime, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo

from .contract import ChangeKind, Contract, PeriodBill


def _resolve_local(naive: datetime, tz: ZoneInfo) -> datetime:
    candidates = [naive.replace(tzinfo=tz, fold=fold) for fold in (0, 1)]
    valid = []
    for aware in candidates:
        back = aware.astimezone(timezone.utc).astimezone(tz)
        if back.replace(tzinfo=None) == naive:
            valid.append(aware.astimezone(timezone.utc))
    if valid:
        return min(valid)
    gap = candidates[1].utcoffset() - candidates[0].utcoffset()
    if gap.total_seconds() <= 0:
        raise ValueError(f"cannot resolve local time {naive} in {tz}")
    return _resolve_local(naive + gap, tz)


def period_boundary_utc(contract: Contract, n: int) -> datetime:
    if n < 0:
        raise ValueError("n must be >= 0")
    anchor = contract.start_local
    tz = ZoneInfo(contract.tz_name)
    total_months = anchor.month - 1 + n * contract.period_months
    year = anchor.year + total_months // 12
    month = total_months % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    local = anchor.replace(year=year, month=month, day=day)
    return _resolve_local(local, tz)


def _apply_change(state: dict, change) -> None:
    if change.kind is ChangeKind.SET_PRICE:
        state["price"] = change.price_cents
    elif change.kind is ChangeKind.PAUSE:
        state["paused"] = True
    elif change.kind is ChangeKind.RESUME:
        state["paused"] = False
    elif change.kind is ChangeKind.CANCEL:
        state["cancelled"] = True


def _bill_one_period(
    contract: Contract, index: int, start: datetime, end: datetime
) -> PeriodBill:
    full_seconds = Fraction(int((end - start).total_seconds()))
    state = {"price": contract.initial_price_cents, "paused": False, "cancelled": False}
    for change in contract.changes:
        if change.effective_at >= start:
            break
        _apply_change(state, change)

    total = Fraction(0)
    cursor = start

    def contribute(a: datetime, b: datetime) -> None:
        nonlocal total
        if state["paused"] or state["cancelled"] or b <= a:
            return
        seconds = int((b - a).total_seconds())
        total += Fraction(state["price"] * seconds, full_seconds)

    for change in contract.changes:
        if change.effective_at < start:
            continue
        if change.effective_at >= end:
            break
        contribute(cursor, change.effective_at)
        _apply_change(state, change)
        cursor = change.effective_at
    contribute(cursor, end)

    amount = (total * 2 + 1) // 2
    return PeriodBill(
        period_index=index, start_utc=start, end_utc=end, amount_cents=int(amount)
    )


def bill_periods(contract: Contract, from_index: int, to_index: int) -> list[PeriodBill]:
    if from_index < 0 or to_index < from_index:
        raise ValueError("invalid period range")
    cancel_at = None
    for change in contract.changes:
        if change.kind is ChangeKind.CANCEL:
            cancel_at = change.effective_at
            break
    bills = []
    for index in range(from_index, to_index):
        start = period_boundary_utc(contract, index)
        if cancel_at is not None and start >= cancel_at:
            continue
        end = period_boundary_utc(contract, index + 1)
        bills.append(_bill_one_period(contract, index, start, end))
    return bills
