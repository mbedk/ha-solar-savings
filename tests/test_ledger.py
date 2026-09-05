"""Unit tests for the FIFO solar/battery savings ledger.

Deliberately imports ledger.py directly (bypassing the
custom_components.solar_savings package __init__), since the package
__init__ pulls in Home Assistant, which this test environment doesn't have
installed. ledger.py itself has no such dependency.

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "solar_savings")
)

from ledger import GRID, SOLAR, SolarSavingsLedger  # noqa: E402


class SolarOnlyTests(unittest.TestCase):
    def test_direct_solar_valued_at_grid_price(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.add_direct_solar(2.0, grid_price=1.5)
        self.assertAlmostEqual(ledger.solar_direct_savings, 3.0)
        self.assertAlmostEqual(ledger.total_solar_savings, 3.0)
        self.assertAlmostEqual(ledger.total_system_savings, 3.0)

    def test_solar_charge_then_discharge_credits_via_battery_savings(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(5.0, SOLAR, unit_cost=0.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 5.0)
        self.assertAlmostEqual(ledger.battery_solar_fraction, 1.0)

        ledger.discharge_battery(5.0, current_grid_price=2.0)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 10.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 0.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 0.0)


class GridArbitrageTests(unittest.TestCase):
    def test_grid_charge_then_discharge_credits_arbitrage_savings(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(4.0, GRID, unit_cost=0.5)
        self.assertAlmostEqual(ledger.battery_grid_charge_cost_basis, 0.5)
        self.assertAlmostEqual(ledger.battery_solar_fraction, 0.0)

        ledger.discharge_battery(4.0, current_grid_price=2.0)
        # (2.0 - 0.5) * 4.0 kWh
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 6.0)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 0.0)

    def test_arbitrage_savings_can_be_negative_if_price_dropped(self) -> None:
        """A grid-charge that turns out not to have been worth it isn't hidden."""
        ledger = SolarSavingsLedger()
        ledger.charge_battery(1.0, GRID, unit_cost=2.0)
        ledger.discharge_battery(1.0, current_grid_price=0.5)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, -1.5)


class MixedFifoOrderTests(unittest.TestCase):
    def test_discharge_consumes_parcels_in_fifo_order(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(2.0, SOLAR, unit_cost=0.0)
        ledger.charge_battery(3.0, GRID, unit_cost=1.0)

        # Partial discharge consumes only the front (solar) parcel first.
        ledger.discharge_battery(1.0, current_grid_price=2.0)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 2.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 0.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 4.0)

        # Next discharge finishes the solar parcel (1 kWh left) then spills
        # into the grid parcel (1 kWh of the 3 kWh grid parcel).
        ledger.discharge_battery(2.0, current_grid_price=2.0)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 2.0 + 1.0 * 2.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 1.0 * (2.0 - 1.0))
        self.assertAlmostEqual(ledger.queued_energy_kwh, 2.0)

    def test_same_source_same_cost_parcels_merge(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(1.0, GRID, unit_cost=1.0)
        ledger.charge_battery(1.0, GRID, unit_cost=1.0)
        self.assertEqual(len(ledger._parcels), 1)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 2.0)

    def test_different_cost_parcels_do_not_merge(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(1.0, GRID, unit_cost=1.0)
        ledger.charge_battery(1.0, GRID, unit_cost=1.5)
        self.assertEqual(len(ledger._parcels), 2)


class ColdStartAndEdgeCaseTests(unittest.TestCase):
    def test_discharge_with_empty_queue_defaults_to_solar(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.discharge_battery(1.0, current_grid_price=3.0)
        self.assertAlmostEqual(ledger.solar_via_battery_savings, 3.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 0.0)

    def test_discharge_with_unknown_price_still_drains_queue_without_crediting(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(2.0, GRID, unit_cost=1.0)
        ledger.discharge_battery(2.0, current_grid_price=None)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 0.0)
        self.assertAlmostEqual(ledger.battery_arbitrage_savings, 0.0)

    def test_zero_or_negative_energy_is_a_no_op(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(0.0, SOLAR, 0.0)
        ledger.charge_battery(-1.0, SOLAR, 0.0)
        ledger.add_direct_solar(0.0, 1.0)
        ledger.add_export(-1.0, 1.0)
        self.assertAlmostEqual(ledger.queued_energy_kwh, 0.0)
        self.assertAlmostEqual(ledger.solar_direct_savings, 0.0)
        self.assertAlmostEqual(ledger.solar_export_revenue, 0.0)

    def test_battery_solar_fraction_defaults_to_one_when_empty(self) -> None:
        ledger = SolarSavingsLedger()
        self.assertAlmostEqual(ledger.battery_solar_fraction, 1.0)

    def test_invalid_source_rejected(self) -> None:
        ledger = SolarSavingsLedger()
        with self.assertRaises(ValueError):
            ledger.charge_battery(1.0, "wind", 0.0)


class PersistenceTests(unittest.TestCase):
    def test_round_trips_through_dict(self) -> None:
        ledger = SolarSavingsLedger()
        ledger.charge_battery(2.0, SOLAR, 0.0)
        ledger.charge_battery(3.0, GRID, 1.2)
        ledger.discharge_battery(1.0, current_grid_price=2.0)
        ledger.add_direct_solar(4.0, grid_price=1.5)
        ledger.add_export(1.0, export_price=0.5)

        restored = SolarSavingsLedger.from_dict(ledger.to_dict())

        self.assertAlmostEqual(restored.queued_energy_kwh, ledger.queued_energy_kwh)
        self.assertAlmostEqual(restored.solar_direct_savings, ledger.solar_direct_savings)
        self.assertAlmostEqual(
            restored.solar_via_battery_savings, ledger.solar_via_battery_savings
        )
        self.assertAlmostEqual(
            restored.battery_arbitrage_savings, ledger.battery_arbitrage_savings
        )
        self.assertAlmostEqual(restored.solar_export_revenue, ledger.solar_export_revenue)
        self.assertAlmostEqual(
            restored.battery_grid_charge_cost_basis, ledger.battery_grid_charge_cost_basis
        )


if __name__ == "__main__":
    unittest.main()
