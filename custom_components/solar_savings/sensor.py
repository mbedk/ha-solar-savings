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
from .ledger import SolarSavingsLedger


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine: SolarSavingsEngine = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            _MoneySensor(
                engine, entry, "solar_direct_savings", "Solar Direct Savings",
                lambda ledger: ledger.solar_direct_savings,
            ),
            _MoneySensor(
                engine, entry, "solar_via_battery_savings", "Solar Via Battery Savings",
                lambda ledger: ledger.solar_via_battery_savings,
            ),
            _MoneySensor(
                engine, entry, "total_solar_savings", "Total Solar Savings",
                lambda ledger: ledger.total_solar_savings,
            ),
            _MoneySensor(
                engine, entry, "battery_arbitrage_savings", "Battery Arbitrage Savings",
                lambda ledger: ledger.battery_arbitrage_savings,
            ),
            _MoneySensor(
                engine, entry, "total_system_savings", "Total System Savings",
                lambda ledger: ledger.total_system_savings,
            ),
            _MoneySensor(
                engine, entry, "solar_export_revenue", "Solar Export Revenue",
                lambda ledger: ledger.solar_export_revenue,
            ),
            _RatioSensor(
                engine, entry, "battery_solar_fraction", "Battery Solar Fraction",
                lambda ledger: ledger.battery_solar_fraction,
            ),
            _CostBasisSensor(
                engine, entry, "battery_grid_charge_cost_basis", "Battery Grid Charge Cost Basis",
                lambda ledger: ledger.battery_grid_charge_cost_basis,
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
        getter: Callable[[SolarSavingsLedger], float],
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
        return round(self._getter(self._engine.ledger), 4)


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


class _RatioSensor(_SolarSavingsSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:battery-sync"


class _CostBasisSensor(_SolarSavingsSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "DKK/kWh"
    _attr_icon = "mdi:currency-usd"
