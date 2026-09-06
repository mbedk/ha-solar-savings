"""Unit tests for the calendar-period tracker.

Same import trick as test_ledger.py: reach periods.py directly, bypassing
the custom_components.solar_savings package __init__ (which pulls in Home
Assistant, not available in this test environment).

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "solar_savings")
)

from periods import PeriodTracker  # noqa: E402


class FreshTrackerTests(unittest.TestCase):
    def test_first_update_starts_every_period_at_zero(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 6, 10, 0), current_total=42.0)
        for period in ("daily", "weekly", "monthly", "yearly"):
            self.assertAlmostEqual(tracker.value(period), 0.0)

    def test_value_tracks_change_within_the_same_period(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 6, 10, 0), current_total=10.0)
        tracker.update(datetime(2026, 9, 6, 12, 0), current_total=13.5)
        for period in ("daily", "weekly", "monthly", "yearly"):
            self.assertAlmostEqual(tracker.value(period), 3.5)


class RolloverTests(unittest.TestCase):
    def test_daily_rollover_resets_only_the_daily_baseline(self) -> None:
        tracker = PeriodTracker()
        # Tuesday -> Wednesday, both in ISO week 37 of 2026: isolates the day
        # boundary from the week one (Sept 6->7 crosses both, see the weekly
        # test below).
        tracker.update(datetime(2026, 9, 8, 23, 59), current_total=100.0)
        tracker.update(datetime(2026, 9, 9, 0, 1), current_total=101.0)
        self.assertAlmostEqual(tracker.value("daily"), 0.0)
        # Same week/month/year, so those keep the original baseline (100.0).
        self.assertAlmostEqual(tracker.value("weekly"), 1.0)
        self.assertAlmostEqual(tracker.value("monthly"), 1.0)
        self.assertAlmostEqual(tracker.value("yearly"), 1.0)

    def test_weekly_rollover_is_iso_week_monday_start(self) -> None:
        tracker = PeriodTracker()
        # 2026-09-06 is a Sunday (end of ISO week 36).
        tracker.update(datetime(2026, 9, 6, 12, 0), current_total=50.0)
        # 2026-09-07 is a Monday (start of ISO week 37).
        tracker.update(datetime(2026, 9, 7, 0, 5), current_total=51.0)
        self.assertAlmostEqual(tracker.value("weekly"), 0.0)
        self.assertAlmostEqual(tracker.value("monthly"), 1.0)

    def test_monthly_rollover(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 30, 23, 0), current_total=200.0)
        tracker.update(datetime(2026, 10, 1, 0, 30), current_total=202.0)
        self.assertAlmostEqual(tracker.value("monthly"), 0.0)
        self.assertAlmostEqual(tracker.value("yearly"), 2.0)

    def test_yearly_rollover_resets_everything(self) -> None:
        # ISO weeks don't always align to the calendar year boundary (e.g.
        # 2026-12-31 -> 2027-01-01 both fall in ISO week 53 of 2026) - pick a
        # boundary where the ISO week also turns over, so this genuinely
        # exercises "every period resets," not just three of the four.
        tracker = PeriodTracker()
        tracker.update(datetime(2023, 12, 31, 23, 59), current_total=500.0)
        tracker.update(datetime(2024, 1, 1, 0, 1), current_total=503.0)
        for period in ("daily", "weekly", "monthly", "yearly"):
            self.assertAlmostEqual(tracker.value(period), 0.0)

    def test_rollover_baseline_is_the_value_at_the_moment_of_rollover(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 6, 23, 59), current_total=100.0)
        tracker.update(datetime(2026, 9, 7, 0, 1), current_total=101.0)
        tracker.update(datetime(2026, 9, 7, 8, 0), current_total=104.0)
        self.assertAlmostEqual(tracker.value("daily"), 3.0)


class NegativeDeltaTests(unittest.TestCase):
    def test_a_losing_period_is_not_clamped_to_zero(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 6, 8, 0), current_total=20.0)
        tracker.update(datetime(2026, 9, 6, 18, 0), current_total=15.0)
        self.assertAlmostEqual(tracker.value("daily"), -5.0)


class PersistenceTests(unittest.TestCase):
    def test_round_trips_through_dict(self) -> None:
        tracker = PeriodTracker()
        tracker.update(datetime(2026, 9, 6, 10, 0), current_total=10.0)
        tracker.update(datetime(2026, 9, 6, 16, 0), current_total=17.0)

        restored = PeriodTracker.from_dict(tracker.to_dict())
        restored.update(datetime(2026, 9, 6, 20, 0), current_total=19.0)
        tracker.update(datetime(2026, 9, 6, 20, 0), current_total=19.0)

        for period in ("daily", "weekly", "monthly", "yearly"):
            self.assertAlmostEqual(restored.value(period), tracker.value(period))

    def test_fresh_tracker_from_empty_dict_behaves_like_a_new_one(self) -> None:
        restored = PeriodTracker.from_dict({})
        restored.update(datetime(2026, 9, 6, 10, 0), current_total=7.0)
        for period in ("daily", "weekly", "monthly", "yearly"):
            self.assertAlmostEqual(restored.value(period), 0.0)


if __name__ == "__main__":
    unittest.main()
