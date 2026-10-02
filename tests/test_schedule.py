"""账期边界推算测试：月份截短与夏令时处理。"""
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from subbill.schedule import boundary_local, boundary_utc

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


class TestMonthTruncation(unittest.TestCase):
    def test_jan31_monthly_boundaries(self):
        # 2024-01-31 月付起订：边界依次落在 2月29日、3月31日。
        anchor = datetime(2024, 1, 31, 10, 20, 30)
        self.assertEqual(boundary_local(anchor, 1, 0), datetime(2024, 1, 31, 10, 20, 30))
        self.assertEqual(boundary_local(anchor, 1, 1), datetime(2024, 2, 29, 10, 20, 30))
        self.assertEqual(boundary_local(anchor, 1, 2), datetime(2024, 3, 31, 10, 20, 30))

    def test_truncation_does_not_move_anchor(self):
        # 2月截短到29日后，后续月份仍使用原始日号31。
        anchor = datetime(2024, 1, 31, 0, 0, 0)
        self.assertEqual(boundary_local(anchor, 1, 3), datetime(2024, 4, 30))
        self.assertEqual(boundary_local(anchor, 1, 4), datetime(2024, 5, 31))

    def test_quarterly_and_yearly(self):
        anchor = datetime(2024, 1, 31, 8, 0, 0)
        self.assertEqual(boundary_local(anchor, 3, 1), datetime(2024, 4, 30, 8, 0, 0))
        self.assertEqual(boundary_local(anchor, 12, 1), datetime(2025, 1, 31, 8, 0, 0))

    def test_cross_year_month_addition(self):
        anchor = datetime(2024, 11, 15, 0, 0, 0)
        self.assertEqual(boundary_local(anchor, 3, 1), datetime(2025, 2, 15))
        self.assertEqual(boundary_local(anchor, 1, 2), datetime(2025, 1, 15))


class TestDstTransitions(unittest.TestCase):
    def test_spring_forward_gap_shifts_backward(self):
        # America/New_York 2024-03-10 02:30 不存在，按 1 小时缺口平移到 03:30。
        anchor = datetime(2024, 2, 10, 2, 30, 0)
        boundary = boundary_utc(NY, anchor, 1, 1)
        self.assertEqual(boundary, datetime(2024, 3, 10, 7, 30, 0, tzinfo=UTC))
        local = boundary.astimezone(NY)
        self.assertEqual(local.replace(tzinfo=None), datetime(2024, 3, 10, 3, 30, 0))
        self.assertEqual(local.utcoffset(), timedelta(hours=-4))  # 已进入 EDT

    def test_fall_back_fold_picks_earlier_utc(self):
        # America/New_York 2024-11-03 01:30 重复，选择对应 UTC 较早的一次（fold=0）。
        anchor = datetime(2024, 10, 3, 1, 30, 0)
        boundary = boundary_utc(NY, anchor, 1, 1)
        self.assertEqual(boundary, datetime(2024, 11, 3, 5, 30, 0, tzinfo=UTC))
        local = boundary.astimezone(NY)
        self.assertEqual(local.replace(tzinfo=None), datetime(2024, 11, 3, 1, 30, 0))
        self.assertEqual(local.fold, 0)
        self.assertEqual(local.utcoffset(), timedelta(hours=-4))  # 仍是 EDT

    def test_actual_seconds_across_spring_forward(self):
        # 跨春季切换的账期实际秒数少 1 小时（按 UTC 计）。
        anchor = datetime(2024, 2, 10, 2, 30, 0)
        start = boundary_utc(NY, anchor, 1, 1)  # 2024-03-10 07:30 UTC
        end = boundary_utc(NY, anchor, 1, 2)    # 2024-04-10 06:30 UTC
        self.assertEqual(end, datetime(2024, 4, 10, 6, 30, 0, tzinfo=UTC))
        self.assertEqual(
            int((end - start).total_seconds()), 31 * 86400 - 3600
        )

    def test_actual_seconds_across_fall_back(self):
        # 跨秋季切换的账期实际秒数多 1 小时（按 UTC 计）。
        anchor = datetime(2024, 10, 3, 1, 30, 0)
        start = boundary_utc(NY, anchor, 1, 1)  # 2024-11-03 05:30 UTC
        end = boundary_utc(NY, anchor, 1, 2)    # 2024-12-03 06:30 UTC
        self.assertEqual(end, datetime(2024, 12, 3, 6, 30, 0, tzinfo=UTC))
        self.assertEqual(
            int((end - start).total_seconds()), 30 * 86400 + 3600
        )

    def test_gap_adjustment_does_not_move_anchor(self):
        # 3 月边界被跳时平移，但 4 月边界仍按原始锚点 02:30 推算。
        anchor = datetime(2024, 2, 10, 2, 30, 0)
        boundary = boundary_utc(NY, anchor, 1, 2)
        local = boundary.astimezone(NY)
        self.assertEqual(local.replace(tzinfo=None), datetime(2024, 4, 10, 2, 30, 0))


if __name__ == "__main__":
    unittest.main()
