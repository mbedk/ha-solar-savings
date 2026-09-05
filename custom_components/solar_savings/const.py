"""Constants for the Solar Savings integration."""

DOMAIN = "solar_savings"

CONF_SOLAR_POWER_ENTITY = "solar_power_entity"
CONF_BATTERY_CHARGE_POWER_ENTITY = "battery_charge_power_entity"
CONF_BATTERY_DISCHARGE_POWER_ENTITY = "battery_discharge_power_entity"
CONF_FEED_IN_POWER_ENTITY = "feed_in_power_entity"
CONF_GRID_PRICE_ENTITY = "grid_price_entity"
CONF_EXPORT_PRICE_ENTITY = "export_price_entity"
CONF_BATTERY_GRID_CHARGE_ENTITY = "battery_grid_charge_entity"

# Defaults match this instance's current FoxESS / evcc / Energi Data Service setup.
DEFAULT_SOLAR_POWER_ENTITY = "sensor.pv_power"
DEFAULT_BATTERY_CHARGE_POWER_ENTITY = "sensor.battery_charge"
DEFAULT_BATTERY_DISCHARGE_POWER_ENTITY = "sensor.battery_discharge"
DEFAULT_FEED_IN_POWER_ENTITY = "sensor.feed_in"
DEFAULT_GRID_PRICE_ENTITY = "sensor.energi_data_service"
DEFAULT_EXPORT_PRICE_ENTITY = "sensor.energi_data_service_raw"
DEFAULT_BATTERY_GRID_CHARGE_ENTITY = "binary_sensor.evcc_battery_grid_charge_active"

# Matches evcc_intg's own ~30s poll cadence (confirmed empirically) - ticking
# faster wouldn't see fresher data, ticking slower would add avoidable lag on
# top of evcc's own delay.
TICK_INTERVAL_SECONDS = 30

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_ledger"

SIGNAL_UPDATE = f"{DOMAIN}_update"
