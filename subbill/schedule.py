"""账期边界推算：日历月加法与本地时刻到 UTC 的解析。"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def add_months_to_ym(year: int, month: int, months: int) -> tuple[int, int]:
    """返回 (year, month) 延后 months 个日历月后的 (年, 月)。"""
    total = year * 12 + (month - 1) + months
    return total // 12, total % 12 + 1


def _roundtrip(tz: ZoneInfo, local: datetime, fold: int) -> datetime:
    """把本地时刻按指定 fold 转到 UTC 再转回本地（无时区），用于检测有效性。"""
    aware = local.replace(tzinfo=tz, fold=fold)
    return aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)


def resolve_local(tz: ZoneInfo, local: datetime) -> datetime:
    """把无时区的本地时刻解析为带时区的时刻。

    落在夏令时缺失区间时按缺口向后平移；重复时刻选择对应 UTC 较早的一次。
    """
    valid = [f for f in (0, 1) if _roundtrip(tz, local, f) == local]
    if len(valid) == 2:
        # 重复时刻：fold=0 对应较早的 UTC。
        return local.replace(tzinfo=tz, fold=0)
    if len(valid) == 1:
        return local.replace(tzinfo=tz, fold=valid[0])
    # 缺失区间：两个 fold 的 UTC 之差即为跳时缺口，向后平移缺口长度。
    utc0 = local.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)
    utc1 = local.replace(tzinfo=tz, fold=1).astimezone(timezone.utc)
    gap = utc0 - utc1
    if gap <= timedelta(0):
        raise ValueError(f"无法解析的本地时刻: {local!r} @ {tz}")
    return resolve_local(tz, local + gap)


def boundary_local(anchor: datetime, period_months: int, n: int) -> datetime:
    """第 n 个账期边界的本地时刻（无时区）。

    由原始锚点直接延后 n*period_months 个月；目标月没有原始日号时取该月最后一天，
    但锚点日号不变。本地时分秒保持原值。
    """
    year, month = add_months_to_ym(anchor.year, anchor.month, period_months * n)
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def boundary_utc(tz: ZoneInfo, anchor: datetime, period_months: int, n: int) -> datetime:
    """第 n 个账期边界的 UTC 时刻（tzinfo=utc）。"""
    local = boundary_local(anchor, period_months, n)
    return resolve_local(tz, local).astimezone(timezone.utc)
