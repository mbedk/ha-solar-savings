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

    # Deliberately NOT has_entity_name=True: that would prefix every entity
    # with the device name ("Solar Savings" + "Solar Direct Savings"), and
    # these names are already complete, standalone names chosen to match a
    # specific entity_id (e.g. sensor.solar_direct_savings).
    _attr_should_poll = False

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
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
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
