"""账单计算测试：改价、暂停、恢复、取消与取整。"""
import unittest
from datetime import datetime, timedelta, timezone

from subbill import Contract, Change, ChangeKind

UTC = timezone.utc
# 2024-01-01 ~ 2024-02-01（UTC），完整账期 31 天。
JAN_SECONDS = 31 * 86400
HALF = datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC)  # 恰好期中


def make_contract(price=1000):
    return Contract("UTC", datetime(2024, 1, 1, 0, 0, 0), 1, price)


def at(days=0, hours=0):
    return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=days, hours=hours)


class TestBilling(unittest.TestCase):
    def test_full_period_no_change(self):
        bill = make_contract().bill(0)
        self.assertEqual(bill.amount_cents, 1000)
        self.assertEqual(bill.start_utc, datetime(2024, 1, 1, tzinfo=UTC))
        self.assertEqual(bill.end_utc, datetime(2024, 2, 1, tzinfo=UTC))

    def test_mid_period_price_change_prorated(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PRICE, HALF, 2000))
        # 前半期 1000、后半期 2000，精确相加后取整。
        self.assertEqual(c.bill(0).amount_cents, 1500)

    def test_change_on_boundary_only_affects_new_period(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PRICE, datetime(2024, 2, 1, tzinfo=UTC), 2000))
        self.assertEqual(c.bill(0).amount_cents, 1000)
        self.assertEqual(c.bill(1).amount_cents, 2000)

    def test_pause_middle_segment(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PAUSE, at(days=8)))
        c.add_change(Change(ChangeKind.RESUME, at(days=24)))
        # 收费 15 天 / 31 天。
        self.assertEqual(
            c.bill(0).amount_cents, round_half_up(1000 * 15 * 86400, JAN_SECONDS)
        )

    def test_price_change_during_pause_survives_resume(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PAUSE, at(days=10)))
        c.add_change(Change(ChangeKind.PRICE, at(days=15), 3000))
        c.add_change(Change(ChangeKind.RESUME, at(days=20)))
        # 前 10 天按 1000，最后 11 天按 3000，中间暂停不计费。
        expected = round_half_up(
            1000 * 10 * 86400 + 3000 * 11 * 86400, JAN_SECONDS
        )
        self.assertEqual(c.bill(0).amount_cents, expected)

    def test_same_instant_changes_apply_in_order(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PRICE, HALF, 2000))
        c.add_change(Change(ChangeKind.PAUSE, HALF))
        # 同一时刻先改价后暂停：后半期暂停，金额为前半期 1000 价的一半。
        self.assertEqual(c.bill(0).amount_cents, 500)

    def test_cancel_mid_period_keeps_full_denominator(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.CANCEL, HALF))
        self.assertEqual(c.bill(0).amount_cents, 500)
        # 起点不早于取消时刻的账期不生成账单。
        self.assertIsNone(c.bill(1))
        self.assertIsNone(c.bill(2))

    def test_cancel_on_boundary(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.CANCEL, datetime(2024, 2, 1, tzinfo=UTC)))
        self.assertEqual(c.bill(0).amount_cents, 1000)
        self.assertIsNone(c.bill(1))

    def test_fully_paused_period_keeps_zero_bill(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PAUSE, datetime(2024, 1, 1, tzinfo=UTC)))
        bill = c.bill(0)
        self.assertIsNotNone(bill)
        self.assertEqual(bill.amount_cents, 0)
        self.assertEqual([b.amount_cents for b in c.bills(0, 2)], [0, 0])

    def test_rounding_half_up(self):
        c = make_contract(price=1)
        c.add_change(Change(ChangeKind.PAUSE, HALF))
        # 恰好半分，向上取整为 1。
        self.assertEqual(c.bill(0).amount_cents, 1)

    def test_rounding_down(self):
        c = make_contract(price=1)
        c.add_change(Change(ChangeKind.PAUSE, at(days=8)))
        c.add_change(Change(ChangeKind.RESUME, at(days=24)))
        # 仅 1/4 期计费，0.25 分舍去。
        self.assertEqual(c.bill(0).amount_cents, 0)

    def test_proration_uses_utc_seconds_across_dst(self):
        # America/New_York 跨春季切换的账期实际为 31*86400-3600 秒。
        c = Contract("America/New_York", datetime(2024, 2, 10, 2, 30, 0), 1, 2674800)
        start = datetime(2024, 3, 10, 7, 30, 0, tzinfo=UTC)
        c.add_change(Change(ChangeKind.PAUSE, start))
        c.add_change(Change(ChangeKind.RESUME, start + timedelta(days=1)))
        # 每期价等于整期秒数：暂停 86400 秒即少收 86400 分。
        self.assertEqual(c.bill(1).amount_cents, 2674800 - 86400)

    def test_changes_must_be_non_decreasing(self):
        c = make_contract()
        c.add_change(Change(ChangeKind.PAUSE, HALF))
        with self.assertRaises(ValueError):
            c.add_change(Change(ChangeKind.RESUME, at(days=1)))

    def test_invalid_contract_args(self):
        with self.assertRaises(ValueError):
            Contract("UTC", datetime(2024, 1, 1), 2, 1000)
        with self.assertRaises(ValueError):
            Contract("UTC", datetime(2024, 1, 1), 1, -1)


def round_half_up(numerator, denominator):
    q, r = divmod(numerator, denominator)
    return q + (1 if 2 * r >= denominator else 0)


if __name__ == "__main__":
    unittest.main()
