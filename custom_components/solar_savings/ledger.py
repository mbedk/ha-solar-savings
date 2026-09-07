"""Pure-Python FIFO ledger for solar/battery savings accounting.

This module has no Home Assistant imports so it can be unit tested in
isolation (see tests/test_ledger.py and tests/test_accounting.py). All the
"what does a kWh of battery discharge actually represent" logic lives here -
the FIFO ledger itself, plus apply_interval(), which turns one snapshot of
live power readings into ledger postings. engine.py is only the thin Home
Assistant glue (state listeners, persistence, entity updates) that reads
those numbers off Home Assistant state and hands them here.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

SOLAR = "solar"
GRID = "grid"

_EPSILON = 1e-9
_COST_TOLERANCE = 1e-6


@dataclass
class Parcel:
    """A slice of energy sitting in the battery, tagged by where it came from."""

    source: str  # SOLAR or GRID
    energy_kwh: float
    unit_cost: float  # DKK/kWh paid at charge time; 0 for solar


class SolarSavingsLedger:
    """Tracks the battery's contents as a FIFO queue of energy parcels and
    accumulates the resulting savings/revenue streams.

    Four accumulators, each DKK, each monotonically increasing:
      - solar_direct_savings: solar used immediately by the house, valued at
        grid price at the time of use.
      - solar_via_battery_savings: solar stored then later discharged to the
        house, valued at grid price at the time of discharge.
      - battery_arbitrage_savings: grid energy bought cheap, stored, and
        discharged later when the price is higher.
      - solar_export_revenue: energy fed back to the grid, valued at the
        export/compensation price. Revenue, not a saving — kept separate.
    """

    def __init__(self) -> None:
        self._parcels: deque[Parcel] = deque()
        self.solar_direct_savings: float = 0.0
        self.solar_via_battery_savings: float = 0.0
        self.battery_arbitrage_savings: float = 0.0
        self.solar_export_revenue: float = 0.0

    # ---- battery charge / discharge ---------------------------------------

    def charge_battery(self, energy_kwh: float, source: str, unit_cost: float) -> None:
        """Add a parcel of energy_kwh charged into the battery from `source`.

        `unit_cost` is the grid price paid at charge time (ignored/0 for
        solar). Merges into the previous parcel when source and cost match,
        so the queue doesn't grow without bound during a steady charge.
        """
        if energy_kwh <= 0:
            return
        if source not in (SOLAR, GRID):
            raise ValueError(f"unknown parcel source: {source!r}")
        if self._parcels and self._parcels[-1].source == source and _cost_equal(
            self._parcels[-1].unit_cost, unit_cost
        ):
            self._parcels[-1].energy_kwh += energy_kwh
        else:
            self._parcels.append(Parcel(source=source, energy_kwh=energy_kwh, unit_cost=unit_cost))

    def discharge_battery(self, energy_kwh: float, current_grid_price: float | None) -> None:
        """Remove energy_kwh from the front of the queue, crediting savings.

        `current_grid_price` may be None if the price entity is momentarily
        unavailable — the energy still physically leaves the battery (the
        queue is still consumed), it just isn't credited to any accumulator
        for this slice, since there is nothing sound to value it at.
        """
        remaining = energy_kwh
        while remaining > _EPSILON:
            if not self._parcels:
                # Cold start / no charge history yet: assume solar-origin,
                # matching the common case for a solar+battery system.
                if current_grid_price is not None:
                    self.solar_via_battery_savings += remaining * current_grid_price
                remaining = 0.0
                break

            parcel = self._parcels[0]
            take = min(parcel.energy_kwh, remaining)
            if current_grid_price is not None:
                if parcel.source == SOLAR:
                    self.solar_via_battery_savings += take * current_grid_price
                else:
                    self.battery_arbitrage_savings += take * (current_grid_price - parcel.unit_cost)
            parcel.energy_kwh -= take
            remaining -= take
            if parcel.energy_kwh <= _EPSILON:
                self._parcels.popleft()

    # ---- direct solar / export --------------------------------------------

    def add_direct_solar(self, energy_kwh: float, grid_price: float) -> None:
        if energy_kwh <= 0:
            return
        self.solar_direct_savings += energy_kwh * grid_price

    def add_export(self, energy_kwh: float, export_price: float) -> None:
        if energy_kwh <= 0:
            return
        self.solar_export_revenue += energy_kwh * export_price

    # ---- derived / diagnostic properties -----------------------------------

    @property
    def total_solar_savings(self) -> float:
        return self.solar_direct_savings + self.solar_via_battery_savings

    @property
    def total_system_savings(self) -> float:
        return self.total_solar_savings + self.battery_arbitrage_savings

    @property
    def battery_solar_fraction(self) -> float:
        """Share of the energy currently queued in the battery that is solar-origin.

        Defaults to 1.0 when nothing is queued (nothing to disagree about).
        """
        solar_kwh = sum(p.energy_kwh for p in self._parcels if p.source == SOLAR)
        grid_kwh = sum(p.energy_kwh for p in self._parcels if p.source == GRID)
        total = solar_kwh + grid_kwh
        if total <= _EPSILON:
            return 1.0
        return max(0.0, min(1.0, solar_kwh / total))

    @property
    def battery_grid_charge_cost_basis(self) -> float:
        """Weighted-average DKK/kWh paid for the grid-origin energy currently queued."""
        grid_parcels = [p for p in self._parcels if p.source == GRID]
        grid_kwh = sum(p.energy_kwh for p in grid_parcels)
        if grid_kwh <= _EPSILON:
            return 0.0
        return sum(p.energy_kwh * p.unit_cost for p in grid_parcels) / grid_kwh

    @property
    def queued_energy_kwh(self) -> float:
        return sum(p.energy_kwh for p in self._parcels)

    # ---- persistence ---------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "parcels": [
                {"source": p.source, "energy_kwh": p.energy_kwh, "unit_cost": p.unit_cost}
                for p in self._parcels
            ],
            "solar_direct_savings": self.solar_direct_savings,
            "solar_via_battery_savings": self.solar_via_battery_savings,
            "battery_arbitrage_savings": self.battery_arbitrage_savings,
            "solar_export_revenue": self.solar_export_revenue,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SolarSavingsLedger":
        ledger = cls()
        for item in data.get("parcels", []):
            ledger._parcels.append(
                Parcel(
                    source=item["source"],
                    energy_kwh=item["energy_kwh"],
                    unit_cost=item["unit_cost"],
                )
            )
        ledger.solar_direct_savings = data.get("solar_direct_savings", 0.0)
        ledger.solar_via_battery_savings = data.get("solar_via_battery_savings", 0.0)
        ledger.battery_arbitrage_savings = data.get("battery_arbitrage_savings", 0.0)
        ledger.solar_export_revenue = data.get("solar_export_revenue", 0.0)
        return ledger


def _cost_equal(a: float, b: float, tol: float = _COST_TOLERANCE) -> bool:
    return abs(a - b) <= tol


@dataclass(frozen=True)
class Inputs:
    """One snapshot of the configured source entities.

    Powers are kW; prices are DKK/kWh and may be None when the price entity
    is momentarily unavailable.
    """

    solar_power: float
    battery_charge_power: float
    battery_discharge_power: float
    feed_in_power: float
    grid_price: float | None
    export_price: float | None
    grid_charging: bool


def apply_interval(ledger: SolarSavingsLedger, inputs: Inputs, dt_hours: float) -> None:
    """Integrate `inputs` over `dt_hours` and post the result to `ledger`."""
    battery_charge_energy = inputs.battery_charge_power * dt_hours
    battery_discharge_energy = inputs.battery_discharge_power * dt_hours

    if battery_charge_energy > 0:
        if inputs.grid_charging and inputs.grid_price is not None:
            ledger.charge_battery(battery_charge_energy, GRID, inputs.grid_price)
        elif not inputs.grid_charging:
            ledger.charge_battery(battery_charge_energy, SOLAR, 0.0)
        # else: grid-charging with an unavailable price - skip recording this
        # slice rather than record a false zero-cost grid parcel, which would
        # fabricate arbitrage profit later. Rare (price sensor virtually
        # always available), and conservative when it does happen.

    if battery_discharge_energy > 0:
        ledger.discharge_battery(battery_discharge_energy, inputs.grid_price)

    # Direct solar = solar power not currently going into the battery from
    # solar, and not exported. (Grid-sourced battery charging draws AC from
    # the grid, not from PV output, so it never reduces this.)
    battery_charge_power_from_solar = 0.0 if inputs.grid_charging else inputs.battery_charge_power
    solar_direct_power = max(
        0.0, inputs.solar_power - battery_charge_power_from_solar - inputs.feed_in_power
    )
    solar_direct_energy = solar_direct_power * dt_hours
    if solar_direct_energy > 0 and inputs.grid_price is not None:
        ledger.add_direct_solar(solar_direct_energy, inputs.grid_price)

    export_energy = inputs.feed_in_power * dt_hours
    if export_energy > 0 and inputs.export_price is not None:
        ledger.add_export(export_energy, inputs.export_price)
