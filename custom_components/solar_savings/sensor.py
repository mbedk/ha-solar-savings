"""Sensor platform for Solar Savings."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .engine import SolarSavingsEngine


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine: SolarSavingsEngine = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            _MoneySensor(
                engine, entry, "solar_direct_savings", "Solar Direct Savings",
                lambda engine: engine.ledger.solar_direct_savings,
            ),
            _MoneySensor(
                engine, entry, "solar_via_battery_savings", "Solar Via Battery Savings",
                lambda engine: engine.ledger.solar_via_battery_savings,
            ),
            _MoneySensor(
                engine, entry, "total_solar_savings", "Total Solar Savings",
                lambda engine: engine.ledger.total_solar_savings,
            ),
            _MoneySensor(
                engine, entry, "battery_arbitrage_savings", "Battery Arbitrage Savings",
                lambda engine: engine.ledger.battery_arbitrage_savings,
            ),
            _MoneySensor(
                engine, entry, "total_system_savings", "Total System Savings",
                lambda engine: engine.ledger.total_system_savings,
            ),
            _MoneySensor(
                engine, entry, "solar_export_revenue", "Solar Export Revenue",
                lambda engine: engine.ledger.solar_export_revenue,
            ),
            _PeriodMoneySensor(
                engine, entry, "total_system_savings_daily", "Total System Savings Daily", "daily",
            ),
            _PeriodMoneySensor(
                engine, entry, "total_system_savings_weekly", "Total System Savings Weekly", "weekly",
            ),
            _PeriodMoneySensor(
                engine, entry, "total_system_savings_monthly", "Total System Savings Monthly", "monthly",
            ),
            _PeriodMoneySensor(
                engine, entry, "total_system_savings_yearly", "Total System Savings Yearly", "yearly",
            ),
            _RatioSensor(
                engine, entry, "battery_solar_fraction", "Battery Solar Fraction",
                lambda engine: engine.ledger.battery_solar_fraction,
            ),
            _CostBasisSensor(
                engine, entry, "battery_grid_charge_cost_basis", "Battery Grid Charge Cost Basis",
                lambda engine: engine.ledger.battery_grid_charge_cost_basis,
            ),
        ]
    )


class _SolarSavingsSensorBase(SensorEntity):
    """Common wiring: reads a value off the engine's ledger, refreshes on the
    engine's dispatcher signal. The engine's Store already restored any prior
    ledger state before entities are created, so there's no separate
    RestoreEntity fallback needed here.
    """

    # Explicitly False (not just "unset"): merely omitting has_entity_name
    # was NOT enough on this HA version - entities still came out with the
    # device name prefixed onto both entity_id and friendly_name
    # (sensor.solar_savings_total_solar_savings), which only happens when
    # has_entity_name resolves to True. Whatever the exact cause (a newer
    # default for device-linked entities, most likely), forcing it False
    # here plus pinning entity_id explicitly below makes the outcome
    # deterministic instead of depending on a base-class default.
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(
        self,
        engine: SolarSavingsEngine,
        entry: ConfigEntry,
        key: str,
        name: str,
        getter: Callable[[SolarSavingsEngine], float],
    ) -> None:
        self._engine = engine
        self._entry = entry
        self._getter = getter
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self.entity_id = f"sensor.{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Solar Savings",
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._engine.signal, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._getter(self._engine), 4)


class _MoneySensor(_SolarSavingsSensorBase):
    # device_class MONETARY only permits state_class TOTAL (or None), never
    # TOTAL_INCREASING - HA enforces this because money can decrease (refunds,
    # corrections), and it's also correct here: battery_arbitrage_savings (and
    # anything summing it) can legitimately go down after a losing arbitrage
    # trade, i.e. discharging grid-charged energy when the price has since
    # dropped below what was paid for it.
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "DKK"


class _PeriodMoneySensor(_MoneySensor):
    """A daily/weekly/monthly/yearly rollup sensor that also exposes past
    closed periods (e.g. previous years' totals) as an attribute, so they're
    visible without digging through the recorder's history graph.

    The history dict comes straight from PeriodTracker.history(), which only
    ever records a period's real final value at the moment it actually rolled
    over - never interpolated or estimated, so a period this tracker didn't
    live through simply has no entry.
    """

    def __init__(
        self, engine: SolarSavingsEngine, entry: ConfigEntry, key: str, name: str, period: str
    ) -> None:
        super().__init__(engine, entry, key, name, lambda engine: engine.period_tracker.value(period))
        self._period = period

    @property
    def extra_state_attributes(self) -> dict:
        return {"history": self._engine.period_tracker.history(self._period)}


class _RatioSensor(_SolarSavingsSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:battery-sync"


class _CostBasisSensor(_SolarSavingsSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "DKK/kWh"
    _attr_icon = "mdi:currency-usd"
