"""数据类型定义：变更与账单。"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class ChangeKind(enum.Enum):
    """订阅变更类型。"""

    PRICE = "price"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


@dataclass(frozen=True)
class Change:
    """一次变更。effective_utc 为 UTC 生效时刻（整秒，tzinfo=utc）。

    kind 为 PRICE 时 price_cents 必填且为非负整数分。
    """

    kind: ChangeKind
    effective_utc: datetime
    price_cents: int | None = None


@dataclass(frozen=True)
class Bill:
    """一个账期的账单。金额为已按半分向上取整的分。"""

    period_index: int
    start_utc: datetime
    end_utc: datetime
    amount_cents: int
