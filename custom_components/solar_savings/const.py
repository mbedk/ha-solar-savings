"""Constants for the Solar Savings integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.helpers import selector
from homeassistant.util.unit_conversion import PowerConverter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

DOMAIN = "solar_savings"

CURRENCY = "DKK"

CONF_SOLAR_POWER_ENTITY = "solar_power_entity"
CONF_BATTERY_CHARGE_POWER_ENTITY = "battery_charge_power_entity"
CONF_BATTERY_DISCHARGE_POWER_ENTITY = "battery_discharge_power_entity"
CONF_FEED_IN_POWER_ENTITY = "feed_in_power_entity"
CONF_GRID_PRICE_ENTITY = "grid_price_entity"
CONF_EXPORT_PRICE_ENTITY = "export_price_entity"
CONF_BATTERY_GRID_CHARGE_ENTITY = "battery_grid_charge_entity"
CONF_SYSTEM_COST = "system_cost"

# Error keys the config flow can put against a field. Each needs a matching
# entry under config.error in strings.json (and every translation).
ERROR_NOT_FOUND = "entity_not_found"
ERROR_NOT_NUMERIC = "not_numeric"
ERROR_NOT_POWER = "not_power_unit"
ERROR_NOT_PER_KWH = "not_price_per_kwh"
ERROR_NOT_BINARY = "not_on_off"
ERROR_DUPLICATE = "duplicate_power_entity"

# A sensor that is merely unavailable right now is not a bad choice - HA
# restarts, integrations reload, inverters go offline overnight. Only judge
# the state when there is a real one to judge.
UNKNOWN_STATES = ("unknown", "unavailable")


@dataclass(frozen=True)
class FormField:
    """One field on the config and reconfigure forms.

    `key` is the config-entry key the rest of the integration reads the value
    back out of, and `default` seeds the form. Subclasses say how the field is
    rendered and what counts as a usable answer.
    """

    key: str
    default: Any

    def selector(self) -> Any:
        raise NotImplementedError

    def check(self, hass: HomeAssistant, value: Any) -> str | None:
        """An error key for what the user picked, or None if it's usable."""
        return None


@dataclass(frozen=True)
class EntityField(FormField):
    """A source entity, restricted to one domain in the picker."""

    domain: str = "sensor"

    def selector(self) -> Any:
        return selector.EntitySelector(
            selector.EntitySelectorConfig(domain=self.domain)
        )

    def check(self, hass: HomeAssistant, value: Any) -> str | None:
        return None if hass.states.get(value) else ERROR_NOT_FOUND


@dataclass(frozen=True)
class NumericEntityField(EntityField):
    """An entity whose state has to parse as a number, in a unit the engine
    can make sense of.

    An entity carrying no unit at all is accepted: plenty of template sensors
    omit it, and refusing those would be stricter than the engine needs.
    """

    wrong_unit_error: str = ERROR_NOT_NUMERIC

    def check(self, hass: HomeAssistant, value: Any) -> str | None:
        state = hass.states.get(value)
        if state is None:
            return ERROR_NOT_FOUND
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit is not None and not self._unit_ok(unit):
            return self.wrong_unit_error
        if state.state in UNKNOWN_STATES:
            return None
        try:
            float(state.state)
        except (TypeError, ValueError):
            return ERROR_NOT_NUMERIC
        return None

    def _unit_ok(self, unit: str) -> bool:
        return True


@dataclass(frozen=True)
class PowerField(NumericEntityField):
    """An instantaneous power reading, in any real power unit.

    The ledger works in kW throughout; engine.py converts W (or MW) on the
    way in, so the user does not have to build a template sensor just to
    scale one. What is rejected is a unit that is not power at all - a kWh
    energy total being the likely mis-pick - because apply_interval would
    multiply it by elapsed hours and produce something meaningless.
    """

    wrong_unit_error: str = ERROR_NOT_POWER

    def _unit_ok(self, unit: str) -> bool:
        return unit in PowerConverter.VALID_UNITS


@dataclass(frozen=True)
class PriceField(NumericEntityField):
    """A price per kWh. The currency is whatever the user's tariff is quoted
    in - only the "per kWh" part is checked, since that's the part the
    accounting depends on.
    """

    wrong_unit_error: str = ERROR_NOT_PER_KWH

    def _unit_ok(self, unit: str) -> bool:
        return unit.endswith("/kWh")


@dataclass(frozen=True)
class BinaryField(EntityField):
    """A flag entity, on/off."""

    domain: str = "binary_sensor"

    def check(self, hass: HomeAssistant, value: Any) -> str | None:
        state = hass.states.get(value)
        if state is None:
            return ERROR_NOT_FOUND
        if state.state in (*UNKNOWN_STATES, "on", "off"):
            return None
        return ERROR_NOT_BINARY


@dataclass(frozen=True)
class MoneyField(FormField):
    """An amount of money typed in by hand, not read off an entity."""

    def selector(self) -> Any:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step="any",
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=CURRENCY,
            )
        )

    def check(self, hass: HomeAssistant, value: Any) -> str | None:
        try:
            return None if float(value) >= 0 else ERROR_NOT_NUMERIC
        except (TypeError, ValueError):
            return ERROR_NOT_NUMERIC


# Order here is the order the fields appear on the form. Defaults match this
# instance's own FoxESS / evcc / Energi Data Service setup.
INPUT_FIELDS: tuple[FormField, ...] = (
    PowerField(CONF_SOLAR_POWER_ENTITY, "sensor.pv_power"),
    PowerField(CONF_BATTERY_CHARGE_POWER_ENTITY, "sensor.battery_charge"),
    PowerField(CONF_BATTERY_DISCHARGE_POWER_ENTITY, "sensor.battery_discharge"),
    PowerField(CONF_FEED_IN_POWER_ENTITY, "sensor.power_produced"),
    PriceField(CONF_GRID_PRICE_ENTITY, "sensor.energi_data_service"),
    PriceField(CONF_EXPORT_PRICE_ENTITY, "sensor.energi_data_service_raw"),
    BinaryField(
        CONF_BATTERY_GRID_CHARGE_ENTITY,
        "binary_sensor.evcc_battery_grid_charge_active",
    ),
    MoneyField(CONF_SYSTEM_COST, 0),
)

# Matches evcc_intg's own ~30s poll cadence (confirmed empirically) - ticking
# faster wouldn't see fresher data, ticking slower would add avoidable lag on
# top of evcc's own delay.
TICK_INTERVAL_SECONDS = 30

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_ledger"

SIGNAL_UPDATE = f"{DOMAIN}_update"
