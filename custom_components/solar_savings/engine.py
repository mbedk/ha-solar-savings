"""Home Assistant glue for the solar savings ledger.

Owns the SolarSavingsLedger, keeps it fed from live entity state (event
driven, with a periodic backstop tick for sensors that hold steady and
never fire a state_changed event), persists it across restarts, and
notifies the sensor platform when there's a new value to show.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CHARGE_POWER_ENTITY,
    CONF_BATTERY_DISCHARGE_POWER_ENTITY,
    CONF_BATTERY_GRID_CHARGE_ENTITY,
    CONF_EXPORT_PRICE_ENTITY,
    CONF_FEED_IN_POWER_ENTITY,
    CONF_GRID_PRICE_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
    TICK_INTERVAL_SECONDS,
)
from .ledger import GRID, SOLAR, SolarSavingsLedger
from .periods import PeriodTracker

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = (None, "unknown", "unavailable")


def _read_float(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    if state is None or state.state in _UNAVAILABLE_STATES:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _read_bool(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    if state is None or state.state in _UNAVAILABLE_STATES:
        return False
    return state.state == "on"


class SolarSavingsEngine:
    """Owns the ledger and keeps it fed from live Home Assistant state."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.config = config
        self.ledger = SolarSavingsLedger()
        self.period_tracker = PeriodTracker()
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._last_ts: datetime | None = None
        self._unsub_state: list = []
        self._unsub_timer = None

    @property
    def signal(self) -> str:
        return f"{SIGNAL_UPDATE}_{self.entry_id}"

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            if "parcels" in stored:
                # Pre-period-tracking format: the whole blob was the ledger's
                # own to_dict(). Migrate by keeping the ledger and starting
                # the period tracker fresh - don't lose already-accumulated
                # savings just because this feature didn't exist yet.
                self.ledger = SolarSavingsLedger.from_dict(stored)
            else:
                self.ledger = SolarSavingsLedger.from_dict(stored.get("ledger", {}))
                self.period_tracker = PeriodTracker.from_dict(stored.get("periods", {}))
            _LOGGER.debug("Restored solar savings state for %s", self.entry_id)

        # Never backfill across a downtime gap - the next processed interval
        # starts measuring from "now", not from whenever HA last shut down.
        self._last_ts = dt_util.utcnow()

        tracked_entities = [
            self.config[CONF_SOLAR_POWER_ENTITY],
            self.config[CONF_BATTERY_CHARGE_POWER_ENTITY],
            self.config[CONF_BATTERY_DISCHARGE_POWER_ENTITY],
            self.config[CONF_FEED_IN_POWER_ENTITY],
            self.config[CONF_BATTERY_GRID_CHARGE_ENTITY],
        ]
        self._unsub_state.append(
            async_track_state_change_event(self.hass, tracked_entities, self._handle_event)
        )
        self._unsub_timer = async_track_time_interval(
            self.hass, self._handle_tick, timedelta(seconds=TICK_INTERVAL_SECONDS)
        )

    async def async_unload(self) -> None:
        for unsub in self._unsub_state:
            unsub()
        self._unsub_state.clear()
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _handle_event(self, event: Event) -> None:
        self.hass.async_create_task(self._process(dt_util.utcnow()))

    @callback
    def _handle_tick(self, now: datetime) -> None:
        self.hass.async_create_task(self._process(now))

    async def _process(self, now: datetime) -> None:
        if self._last_ts is None:
            self._last_ts = now
            return
        dt_hours = (now - self._last_ts).total_seconds() / 3600.0
        self._last_ts = now
        if dt_hours <= 0:
            return

        cfg = self.config
        solar_power = _read_float(self.hass, cfg[CONF_SOLAR_POWER_ENTITY]) or 0.0
        battery_charge_power = _read_float(self.hass, cfg[CONF_BATTERY_CHARGE_POWER_ENTITY]) or 0.0
        battery_discharge_power = (
            _read_float(self.hass, cfg[CONF_BATTERY_DISCHARGE_POWER_ENTITY]) or 0.0
        )
        feed_in_power = _read_float(self.hass, cfg[CONF_FEED_IN_POWER_ENTITY]) or 0.0
        grid_price = _read_float(self.hass, cfg[CONF_GRID_PRICE_ENTITY])
        export_price = _read_float(self.hass, cfg[CONF_EXPORT_PRICE_ENTITY])
        grid_charging = _read_bool(self.hass, cfg[CONF_BATTERY_GRID_CHARGE_ENTITY])

        battery_charge_energy = battery_charge_power * dt_hours
        battery_discharge_energy = battery_discharge_power * dt_hours

        if battery_charge_energy > 0:
            if grid_charging and grid_price is not None:
                self.ledger.charge_battery(battery_charge_energy, GRID, grid_price)
            elif not grid_charging:
                self.ledger.charge_battery(battery_charge_energy, SOLAR, 0.0)
            # else: grid-charging with an unavailable price - skip recording this
            # slice rather than record a false zero-cost grid parcel, which would
            # fabricate arbitrage profit later. Rare (price sensor virtually
            # always available), and conservative when it does happen.

        if battery_discharge_energy > 0:
            self.ledger.discharge_battery(battery_discharge_energy, grid_price)

        # Direct solar = solar power not currently going into the battery from
        # solar, and not exported. (Grid-sourced battery charging draws AC from
        # the grid, not from PV output, so it never reduces this.)
        battery_charge_power_from_solar = 0.0 if grid_charging else battery_charge_power
        solar_direct_power = max(0.0, solar_power - battery_charge_power_from_solar - feed_in_power)
        solar_direct_energy = solar_direct_power * dt_hours
        if solar_direct_energy > 0 and grid_price is not None:
            self.ledger.add_direct_solar(solar_direct_energy, grid_price)

        export_energy = feed_in_power * dt_hours
        if export_energy > 0 and export_price is not None:
            self.ledger.add_export(export_energy, export_price)

        # Calendar-period rollover uses local wall-clock time, not the UTC
        # timestamp this method receives for elapsed-time math - "daily"
        # means local midnight, not UTC midnight.
        self.period_tracker.update(dt_util.now(), self.ledger.total_system_savings)

        await self._store.async_save(
            {"ledger": self.ledger.to_dict(), "periods": self.period_tracker.to_dict()}
        )
        async_dispatcher_send(self.hass, self.signal)
