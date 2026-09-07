"""Unit tests for apply_interval - the power-readings-to-ledger-postings step.

Same import trick as test_ledger.py: reach ledger.py directly, bypassing the
custom_components.solar_savings package __init__ (which pulls in Home
Assistant, not available in this test environment).

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "solar_savings")
)

from ledger import Inputs, SolarSavingsLedger, apply_interval  # noqa: E402

HALF_HOUR = 0.5


def _inputs(**overrides) -> Inputs:
    """An all-idle snapshot, with only the fields a test cares about set."""
    defaults = dict(
        solar_power=0.0,
        battery_charge_power=0.0,
        battery_discharge_power=0.0,
        feed_in_power=0.0,
        grid_price=2.0,
        export_price=0.5,
        grid_charging=False,
    )
    return Inputs(**{**defaults, **overrides})


class DirectSolarTests(unittest.TestCase):
    def test_solar_not_stored_or_exported_is_credited_at_grid_price(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(ledger, _inputs(solar_power=3.0, grid_price=2.0), HALF_HOUR)
        # 3 kW * 0.5 h = 1.5 kWh at 2.00 DKK/kWh
        self.assertAlmostEqual(ledger.solar_direct_savings, 3.0)

    def test_solar_charging_the_battery_is_not_also_counted_as_direct(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger, _inputs(solar_power=3.0, battery_charge_power=2.0, grid_price=2.0), HALF_HOUR
        )
        # Only the 1 kW not going into the battery is direct.
        self.assertAlmostEqual(ledger.solar_direct_savings, 1.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 1.0)

    def test_exported_solar_is_not_also_counted_as_direct(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger, _inputs(solar_power=3.0, feed_in_power=2.0, grid_price=2.0), HALF_HOUR
        )
        self.assertAlmostEqual(ledger.solar_direct_savings, 1.0)

    def test_grid_charging_does_not_reduce_direct_solar(self) -> None:
        """Grid charging draws AC from the grid, not from PV output."""
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger,
            _inputs(solar_power=3.0, battery_charge_power=2.0, grid_charging=True, grid_price=2.0),
            HALF_HOUR,
        )
        self.assertAlmostEqual(ledger.solar_direct_savings, 3.0)

    def test_house_load_exceeding_solar_never_goes_negative(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(ledger, _inputs(solar_power=1.0, feed_in_power=3.0), HALF_HOUR)
        self.assertAlmostEqual(ledger.solar_direct_savings, 0.0)

    def test_no_credit_when_the_grid_price_is_unavailable(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(ledger, _inputs(solar_power=3.0, grid_price=None), HALF_HOUR)
        self.assertAlmostEqual(ledger.solar_direct_savings, 0.0)


class BatteryChargeTests(unittest.TestCase):
    def test_solar_charging_queues_a_zero_cost_parcel(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(ledger, _inputs(solar_power=2.0, battery_charge_power=2.0), HALF_HOUR)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 1.0)
        self.assertAlmostEqual(ledger.battery_solar_fraction, 1.0)
        self.assertAlmostEqual(ledger.battery_grid_charge_cost_basis, 0.0)

    def test_grid_charging_queues_a_parcel_at_the_price_paid(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger,
            _inputs(battery_charge_power=2.0, grid_charging=True, grid_price=0.8),
            HALF_HOUR,
        )
        self.assertAlmostEqual(ledger.queued_energy_kwh, 1.0)
        self.assertAlmostEqual(ledger.battery_solar_fraction, 0.0)
        self.assertAlmostEqual(ledger.battery_grid_charge_cost_basis, 0.8)

    def test_grid_charging_without_a_price_records_nothing(self) -> None:
        """Recording a zero-cost grid parcel would fabricate arbitrage profit
        on the eventual discharge, so the slice is dropped instead."""
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger,
            _inputs(battery_charge_power=2.0, grid_charging=True, grid_price=None),
            HALF_HOUR,
        )
        self.assertAlmostEqual(ledger.queued_energy_kwh, 0.0)


class BatteryDischargeTests(unittest.TestCase):
    def test_stored_solar_discharges_into_solar_via_battery(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(ledger, _inputs(solar_power=2.0, battery_charge_power=2.0), HALF_HOUR)
        apply_interval(ledger, _inputs(battery_discharge_power=2.0, grid_price=3.0), HALF_HOUR)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 3.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 0.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 0.0)

    def test_grid_charged_energy_discharges_into_arbitrage_at_the_spread(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger,
            _inputs(battery_charge_power=2.0, grid_charging=True, grid_price=0.8),
            HALF_HOUR,
        )
        apply_interval(ledger, _inputs(battery_discharge_power=2.0, grid_price=3.0), HALF_HOUR)
        # 1 kWh bought at 0.80, discharged at 3.00.
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 2.2)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 0.0)


class ExportTests(unittest.TestCase):
    def test_feed_in_is_credited_at_the_export_price(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger, _inputs(solar_power=4.0, feed_in_power=4.0, export_price=0.5), HALF_HOUR
        )
        self.assertAlmostEqual(ledger.solar_export_revenue, 1.0)

    def test_no_revenue_when_the_export_price_is_unavailable(self) -> None:
        ledger = SolarSavingsLedger()
        apply_interval(
            ledger, _inputs(solar_power=4.0, feed_in_power=4.0, export_price=None), HALF_HOUR
        )
        self.assertAlmostEqual(ledger.solar_export_revenue, 0.0)


class IntervalLengthTests(unittest.TestCase):
    def test_energy_scales_with_the_interval(self) -> None:
        short, long = SolarSavingsLedger(), SolarSavingsLedger()
        apply_interval(short, _inputs(solar_power=3.0, grid_price=2.0), 1 / 3600)
        apply_interval(long, _inputs(solar_power=3.0, grid_price=2.0), 10 / 3600)
        self.assertAlmostEqual(long.solar_direct_savings, 10 * short.solar_direct_savings)


if __name__ == "__main__":
    unittest.main()
