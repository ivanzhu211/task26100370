import unittest
from datetime import datetime, timezone

from subbill import Change, ChangeKind, Contract, bill_periods, period_boundary_utc


UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def make_utc_contract(start_local, months=1, price=100):
    return Contract(
        tz_name="UTC",
        start_local=start_local,
        period_months=months,
        initial_price_cents=price,
    )


class BoundaryTest(unittest.TestCase):
    def test_month_end_clamping_keeps_anchor_day(self):
        c = make_utc_contract(datetime(2024, 1, 31, 10, 20, 30))
        self.assertEqual(period_boundary_utc(c, 0), utc(2024, 1, 31, 10, 20, 30))
        self.assertEqual(period_boundary_utc(c, 1), utc(2024, 2, 29, 10, 20, 30))
        self.assertEqual(period_boundary_utc(c, 2), utc(2024, 3, 31, 10, 20, 30))
        self.assertEqual(period_boundary_utc(c, 3), utc(2024, 4, 30, 10, 20, 30))

    def test_quarterly_and_yearly_clamping(self):
        c = make_utc_contract(datetime(2023, 11, 30), months=3)
        self.assertEqual(period_boundary_utc(c, 1), utc(2024, 2, 29))
        self.assertEqual(period_boundary_utc(c, 2), utc(2024, 5, 30))
        c = make_utc_contract(datetime(2024, 2, 29), months=12)
        self.assertEqual(period_boundary_utc(c, 1), utc(2025, 2, 28))
        self.assertEqual(period_boundary_utc(c, 2), utc(2026, 2, 28))


class DstTest(unittest.TestCase):
    def test_spring_forward_gap_shifts_forward(self):
        c = Contract(
            tz_name="America/New_York",
            start_local=datetime(2024, 3, 10, 2, 30),
            period_months=1,
            initial_price_cents=100,
        )
        self.assertEqual(period_boundary_utc(c, 0), utc(2024, 3, 10, 7, 30))
        self.assertEqual(period_boundary_utc(c, 1), utc(2024, 4, 10, 6, 30))

    def test_fall_back_ambiguous_picks_earlier_utc(self):
        c = Contract(
            tz_name="America/New_York",
            start_local=datetime(2024, 11, 3, 1, 30),
            period_months=1,
            initial_price_cents=100,
        )
        self.assertEqual(period_boundary_utc(c, 0), utc(2024, 11, 3, 5, 30))
        self.assertEqual(period_boundary_utc(c, 1), utc(2024, 12, 3, 6, 30))

    def test_actual_seconds_across_spring_forward(self):
        c = Contract(
            tz_name="America/New_York",
            start_local=datetime(2024, 3, 1),
            period_months=1,
            initial_price_cents=2_674_800,
        )
        (bill,) = bill_periods(c, 0, 1)
        self.assertEqual(bill.start_utc, utc(2024, 3, 1, 5, 0))
        self.assertEqual(bill.end_utc, utc(2024, 4, 1, 4, 0))
        self.assertEqual(
            (bill.end_utc - bill.start_utc).total_seconds(), 31 * 86400 - 3600
        )
        self.assertEqual(bill.amount_cents, 2_674_800)

    def test_actual_seconds_across_fall_back(self):
        c = Contract(
            tz_name="America/New_York",
            start_local=datetime(2024, 10, 15),
            period_months=1,
            initial_price_cents=2_682_000,
        )
        (bill,) = bill_periods(c, 0, 1)
        self.assertEqual(bill.start_utc, utc(2024, 10, 15, 4, 0))
        self.assertEqual(bill.end_utc, utc(2024, 11, 15, 5, 0))
        self.assertEqual(
            (bill.end_utc - bill.start_utc).total_seconds(), 31 * 86400 + 3600
        )
        self.assertEqual(bill.amount_cents, 2_682_000)


class BillingTest(unittest.TestCase):
    def test_full_period_no_changes(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        bills = bill_periods(c, 0, 3)
        self.assertEqual([b.amount_cents for b in bills], [100, 100, 100])
        self.assertEqual([b.period_index for b in bills], [0, 1, 2])

    def test_mid_period_price_change_prorated(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 16), ChangeKind.SET_PRICE, 200))
        (bill,) = bill_periods(c, 0, 1)
        # 15 days at 100 + 16 days at 200 over 31 days
        # = (100*1296000 + 200*1382400) / 2678400 = 151.6129... -> 152
        self.assertEqual(bill.amount_cents, 152)

    def test_change_on_boundary_only_affects_new_period(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 2, 1), ChangeKind.SET_PRICE, 300))
        bills = bill_periods(c, 0, 2)
        self.assertEqual([b.amount_cents for b in bills], [100, 300])

    def test_pause_and_resume(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 16), ChangeKind.PAUSE))
        c.add_change(Change(utc(2024, 1, 21), ChangeKind.RESUME))
        (bill,) = bill_periods(c, 0, 1)
        # 26 of 31 days charged: 100*2246400/2678400 = 83.8709... -> 84
        self.assertEqual(bill.amount_cents, 84)

    def test_price_change_during_pause_survives_resume(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 10), ChangeKind.PAUSE))
        c.add_change(Change(utc(2024, 1, 15), ChangeKind.SET_PRICE, 200))
        c.add_change(Change(utc(2024, 1, 20), ChangeKind.RESUME))
        (bill,) = bill_periods(c, 0, 1)
        # 9 days at 100 + 10 days paused + 12 days at 200
        # = (100*777600 + 200*1036800) / 2678400 = 106.4516... -> 106
        self.assertEqual(bill.amount_cents, 106)

    def test_same_instant_changes_apply_in_input_order(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 16), ChangeKind.PAUSE))
        c.add_change(Change(utc(2024, 1, 16), ChangeKind.RESUME))
        (bill,) = bill_periods(c, 0, 1)
        self.assertEqual(bill.amount_cents, 100)

    def test_half_cent_rounds_up(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=0)
        c.add_change(Change(utc(2024, 1, 16, 12), ChangeKind.SET_PRICE, 1))
        (bill,) = bill_periods(c, 0, 1)
        # exactly half of 2678400 seconds at 1 cent -> 0.5 -> 1
        self.assertEqual(bill.amount_cents, 1)

    def test_rounding_per_period_not_on_total(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=1)
        c.add_change(Change(utc(2024, 1, 16, 12), ChangeKind.PAUSE))
        bills = bill_periods(c, 0, 2)
        # period 0: 0.5 -> 1; period 1 fully paused -> 0
        self.assertEqual([b.amount_cents for b in bills], [1, 0])

    def test_fully_paused_period_kept_as_zero_bill(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 15), ChangeKind.PAUSE))
        bills = bill_periods(c, 0, 3)
        self.assertEqual(len(bills), 3)
        # period 0: 14 of 31 days -> 100*1209600/2678400 = 45.16... -> 45
        self.assertEqual(bills[0].amount_cents, 45)
        self.assertEqual(bills[1].amount_cents, 0)
        self.assertEqual(bills[2].amount_cents, 0)

    def test_cancel_mid_period_and_no_bills_after(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 2, 10), ChangeKind.CANCEL))
        bills = bill_periods(c, 0, 5)
        self.assertEqual([b.period_index for b in bills], [0, 1])
        self.assertEqual(bills[0].amount_cents, 100)
        # Feb has 29 days in 2024; 9 of 29 days charged
        # 100*777600/2505600 = 31.0344... -> 31
        self.assertEqual(bills[1].amount_cents, 31)

    def test_cancel_on_boundary_skips_from_that_period(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 2, 1), ChangeKind.CANCEL))
        bills = bill_periods(c, 0, 4)
        self.assertEqual([b.period_index for b in bills], [0])
        self.assertEqual(bills[0].amount_cents, 100)

    def test_changes_must_be_non_decreasing(self):
        c = make_utc_contract(datetime(2024, 1, 1), price=100)
        c.add_change(Change(utc(2024, 1, 10), ChangeKind.PAUSE))
        with self.assertRaises(ValueError):
            c.add_change(Change(utc(2024, 1, 9), ChangeKind.RESUME))


if __name__ == "__main__":
    unittest.main()
