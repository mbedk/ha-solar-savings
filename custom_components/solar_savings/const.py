"""Constants for the Solar Savings integration."""
from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "solar_savings"

CONF_SOLAR_POWER_ENTITY = "solar_power_entity"
CONF_BATTERY_CHARGE_POWER_ENTITY = "battery_charge_power_entity"
CONF_BATTERY_DISCHARGE_POWER_ENTITY = "battery_discharge_power_entity"
CONF_FEED_IN_POWER_ENTITY = "feed_in_power_entity"
CONF_GRID_PRICE_ENTITY = "grid_price_entity"
CONF_EXPORT_PRICE_ENTITY = "export_price_entity"
CONF_BATTERY_GRID_CHARGE_ENTITY = "battery_grid_charge_entity"


@dataclass(frozen=True)
class InputField:
    """One configurable source entity.

    `key` is the config-entry key engine.py reads the entity id back out of,
    `domain` restricts the config-flow picker, and `default` matches this
    instance's current FoxESS / evcc / Energi Data Service setup.
    """

    key: str
    domain: str
    default: str


# Order here is the order the fields appear in the config flow form.
INPUT_FIELDS: tuple[InputField, ...] = (
    InputField(CONF_SOLAR_POWER_ENTITY, "sensor", "sensor.pv_power"),
    InputField(CONF_BATTERY_CHARGE_POWER_ENTITY, "sensor", "sensor.battery_charge"),
    InputField(CONF_BATTERY_DISCHARGE_POWER_ENTITY, "sensor", "sensor.battery_discharge"),
    InputField(CONF_FEED_IN_POWER_ENTITY, "sensor", "sensor.feed_in"),
    InputField(CONF_GRID_PRICE_ENTITY, "sensor", "sensor.energi_data_service"),
    InputField(CONF_EXPORT_PRICE_ENTITY, "sensor", "sensor.energi_data_service_raw"),
    InputField(
        CONF_BATTERY_GRID_CHARGE_ENTITY,
        "binary_sensor",
        "binary_sensor.evcc_battery_grid_charge_active",
    ),
)

# Matches evcc_intg's own ~30s poll cadence (confirmed empirically) - ticking
# faster wouldn't see fresher data, ticking slower would add avoidable lag on
# top of evcc's own delay.
TICK_INTERVAL_SECONDS = 30

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_ledger"

SIGNAL_UPDATE = f"{DOMAIN}_update"
