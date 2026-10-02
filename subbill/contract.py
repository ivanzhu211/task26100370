"""合同：录入变更、计算账期账单。数据只保存在进程内存。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from .schedule import boundary_utc
from .types import Bill, Change, ChangeKind

_VALID_PERIOD_MONTHS = (1, 3, 12)


def _round_half_up(numerator: int, denominator: int) -> int:
    """非负分数 numerator/denominator 四舍五入到整数，恰好一半向上。"""
    q, r = divmod(numerator, denominator)
    if 2 * r >= denominator:
        q += 1
    return q


class _State:
    """某一时刻的计费状态。"""

    __slots__ = ("price_cents", "paused", "cancelled")

    def __init__(self, price_cents: int) -> None:
        self.price_cents = price_cents
        self.paused = False
        self.cancelled = False

    def apply(self, change: Change) -> None:
        if change.kind is ChangeKind.PRICE:
            self.price_cents = change.price_cents
        elif change.kind is ChangeKind.PAUSE:
            self.paused = True
        elif change.kind is ChangeKind.RESUME:
            self.paused = False
        elif change.kind is ChangeKind.CANCEL:
            self.cancelled = True

    @property
    def billing(self) -> bool:
        return not self.paused and not self.cancelled


class Contract:
    """一份订阅合同。

    tz: IANA 时区名；start_local: 原始本地起订时刻（无时区、整秒、有效无歧义）；
    period_months: 固定账期月数（1、3 或 12）；price_cents: 初始每期价（非负整数分）。
    """

    def __init__(
        self,
        tz: str,
        start_local: datetime,
        period_months: int,
        price_cents: int,
    ) -> None:
        if period_months not in _VALID_PERIOD_MONTHS:
            raise ValueError(f"账期月数必须是 1、3 或 12: {period_months!r}")
        if not isinstance(price_cents, int) or price_cents < 0:
            raise ValueError(f"每期价必须是非负整数分: {price_cents!r}")
        if start_local.tzinfo is not None:
            raise ValueError("起订时刻必须是不带时区的本地时刻")
        if start_local.microsecond != 0:
            raise ValueError("时间精度为整秒，不允许微秒")
        self._tz = ZoneInfo(tz)
        self._anchor = start_local
        self._period_months = period_months
        self._initial_price = price_cents
        self._changes: List[Change] = []

    def add_change(self, change: Change) -> None:
        """录入一次变更。生效时刻必须非递减；同一时刻按传入顺序生效。"""
        effective = change.effective_utc
        if effective.tzinfo is None:
            raise ValueError("变更生效时刻必须带时区")
        if effective.microsecond != 0:
            raise ValueError("时间精度为整秒，不允许微秒")
        effective = effective.astimezone(timezone.utc)
        if change.kind is ChangeKind.PRICE:
            if not isinstance(change.price_cents, int) or change.price_cents < 0:
                raise ValueError(f"改价必须给出非负整数分: {change.price_cents!r}")
        if self._changes and effective < self._changes[-1].effective_utc:
            raise ValueError("变更生效时刻必须非递减")
        self._changes.append(
            Change(change.kind, effective, change.price_cents)
        )

    def _boundary(self, n: int) -> datetime:
        return boundary_utc(self._tz, self._anchor, self._period_months, n)

    def bill(self, period_index: int) -> Optional[Bill]:
        """计算第 period_index 期（0 起）账单；不生成时返回 None。"""
        if period_index < 0:
            raise ValueError("账期序号必须非负")
        start = self._boundary(period_index)
        end = self._boundary(period_index + 1)

        # 期初状态：应用所有生效时刻 <= 期初的变更（边界上的变更影响新一期）。
        state = _State(self._initial_price)
        idx = 0
        while idx < len(self._changes) and self._changes[idx].effective_utc <= start:
            state.apply(self._changes[idx])
            idx += 1
        if state.cancelled:
            # 起点不早于取消时刻的账期不生成账单。
            return None

        # 期内变更切分区段；分母始终是原完整账期的实际秒数。
        numerator = 0
        cursor = start
        while idx < len(self._changes) and self._changes[idx].effective_utc < end:
            change = self._changes[idx]
            if state.billing:
                numerator += state.price_cents * _seconds(change.effective_utc - cursor)
            state.apply(change)
            cursor = change.effective_utc
            idx += 1
        if state.billing:
            numerator += state.price_cents * _seconds(end - cursor)

        full_seconds = _seconds(end - start)
        amount = _round_half_up(numerator, full_seconds)
        return Bill(period_index, start, end, amount)

    def bills(self, from_index: int, to_index: int) -> List[Bill]:
        """生成 [from_index, to_index) 范围内所有应生成的账单。"""
        result = []
        for i in range(from_index, to_index):
            bill = self.bill(i)
            if bill is not None:
                result.append(bill)
        return result


def _seconds(delta) -> int:
    return int(delta.total_seconds())
