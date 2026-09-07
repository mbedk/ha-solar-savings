"""Sensor platform for Solar Savings."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .engine import SolarSavingsEngine


@dataclass(frozen=True)
class SensorSpec:
    """Everything that varies between the integration's sensors.

    Deliberately a local dataclass rather than a SensorEntityDescription
    subclass: setting `entity_description` also feeds Home Assistant's entity
    naming machinery, which is exactly what the explicit entity_id and
    has_entity_name=False below exist to keep out of the picture.
    """

    key: str
    name: str
    value_fn: Callable[[SolarSavingsEngine], float]
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    # Set on the period rollup sensors: which PeriodTracker period's closed-out
    # history to expose as an attribute.
    history_period: str | None = None


def _money(
    key: str,
    name: str,
    value_fn: Callable[[SolarSavingsEngine], float],
    history_period: str | None = None,
) -> SensorSpec:
    # device_class MONETARY only permits state_class TOTAL (or None), never
    # TOTAL_INCREASING - HA enforces this because money can decrease (refunds,
    # corrections), and it's also correct here: battery_arbitrage_savings (and
    # anything summing it) can legitimately go down after a losing arbitrage
    # trade, i.e. discharging grid-charged energy when the price has since
    # dropped below what was paid for it.
    return SensorSpec(
        key=key,
        name=name,
        value_fn=value_fn,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit="DKK",
        history_period=history_period,
    )


def _period_money(period: str) -> SensorSpec:
    return _money(
        f"total_system_savings_{period}",
        f"Total System Savings {period.title()}",
        lambda engine: engine.period_tracker.value(period),
        history_period=period,
    )


SENSORS: tuple[SensorSpec, ...] = (
    _money(
        "solar_direct_savings", "Solar Direct Savings",
        lambda engine: engine.ledger.solar_direct_savings,
    ),
    _money(
        "solar_via_battery_savings", "Solar Via Battery Savings",
        lambda engine: engine.ledger.solar_via_battery_savings,
    ),
    _money(
        "total_solar_savings", "Total Solar Savings",
        lambda engine: engine.ledger.total_solar_savings,
    ),
    _money(
        "battery_arbitrage_savings", "Battery Arbitrage Savings",
        lambda engine: engine.ledger.battery_arbitrage_savings,
    ),
    _money(
        "total_system_savings", "Total System Savings",
        lambda engine: engine.ledger.total_system_savings,
    ),
    _money(
        "solar_export_revenue", "Solar Export Revenue",
        lambda engine: engine.ledger.solar_export_revenue,
    ),
    _period_money("daily"),
    _period_money("weekly"),
    _period_money("monthly"),
    _period_money("yearly"),
    SensorSpec(
        key="battery_solar_fraction",
        name="Battery Solar Fraction",
        value_fn=lambda engine: engine.ledger.battery_solar_fraction,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-sync",
    ),
    SensorSpec(
        key="battery_grid_charge_cost_basis",
        name="Battery Grid Charge Cost Basis",
        value_fn=lambda engine: engine.ledger.battery_grid_charge_cost_basis,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        unit="DKK/kWh",
        icon="mdi:currency-usd",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    engine: SolarSavingsEngine = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(SolarSavingsSensor(engine, entry, spec) for spec in SENSORS)


class SolarSavingsSensor(SensorEntity):
    """Reads one value off the engine, refreshes on the engine's dispatcher
    signal. The engine's Store already restored any prior ledger state before
    entities are created, so there's no separate RestoreEntity fallback needed
    here.
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
        self, engine: SolarSavingsEngine, entry: ConfigEntry, spec: SensorSpec
    ) -> None:
        self._engine = engine
        self._spec = spec
        self._attr_name = spec.name
        self._attr_unique_id = f"{entry.entry_id}_{spec.key}"
        self.entity_id = f"sensor.{spec.key}"
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_entity_category = spec.entity_category
        self._attr_icon = spec.icon
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
        return round(self._spec.value_fn(self._engine), 4)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Closed-out totals for previous periods (period sensors only), so
        e.g. previous years' totals are visible without digging through the
        recorder's history graph. Comes straight from PeriodTracker.history(),
        which only ever records a period's real final value at the moment it
        actually rolled over - never interpolated or estimated.
        """
        if self._spec.history_period is None:
            return None
        return {"history": self._engine.period_tracker.history(self._spec.history_period)}
