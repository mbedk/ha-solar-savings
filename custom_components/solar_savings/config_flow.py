"""Config flow for Solar Savings."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CHARGE_POWER_ENTITY,
    CONF_BATTERY_DISCHARGE_POWER_ENTITY,
    CONF_BATTERY_GRID_CHARGE_ENTITY,
    CONF_EXPORT_PRICE_ENTITY,
    CONF_FEED_IN_POWER_ENTITY,
    CONF_GRID_PRICE_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    DEFAULT_BATTERY_CHARGE_POWER_ENTITY,
    DEFAULT_BATTERY_DISCHARGE_POWER_ENTITY,
    DEFAULT_BATTERY_GRID_CHARGE_ENTITY,
    DEFAULT_EXPORT_PRICE_ENTITY,
    DEFAULT_FEED_IN_POWER_ENTITY,
    DEFAULT_GRID_PRICE_ENTITY,
    DEFAULT_SOLAR_POWER_ENTITY,
    DOMAIN,
)

_DEFAULTS = {
    CONF_SOLAR_POWER_ENTITY: DEFAULT_SOLAR_POWER_ENTITY,
    CONF_BATTERY_CHARGE_POWER_ENTITY: DEFAULT_BATTERY_CHARGE_POWER_ENTITY,
    CONF_BATTERY_DISCHARGE_POWER_ENTITY: DEFAULT_BATTERY_DISCHARGE_POWER_ENTITY,
    CONF_FEED_IN_POWER_ENTITY: DEFAULT_FEED_IN_POWER_ENTITY,
    CONF_GRID_PRICE_ENTITY: DEFAULT_GRID_PRICE_ENTITY,
    CONF_EXPORT_PRICE_ENTITY: DEFAULT_EXPORT_PRICE_ENTITY,
    CONF_BATTERY_GRID_CHARGE_ENTITY: DEFAULT_BATTERY_GRID_CHARGE_ENTITY,
}


def _entity_selector(domain: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SOLAR_POWER_ENTITY, default=defaults[CONF_SOLAR_POWER_ENTITY]
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_BATTERY_CHARGE_POWER_ENTITY,
                default=defaults[CONF_BATTERY_CHARGE_POWER_ENTITY],
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_BATTERY_DISCHARGE_POWER_ENTITY,
                default=defaults[CONF_BATTERY_DISCHARGE_POWER_ENTITY],
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_FEED_IN_POWER_ENTITY, default=defaults[CONF_FEED_IN_POWER_ENTITY]
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_GRID_PRICE_ENTITY, default=defaults[CONF_GRID_PRICE_ENTITY]
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_EXPORT_PRICE_ENTITY, default=defaults[CONF_EXPORT_PRICE_ENTITY]
            ): _entity_selector("sensor"),
            vol.Required(
                CONF_BATTERY_GRID_CHARGE_ENTITY,
                default=defaults[CONF_BATTERY_GRID_CHARGE_ENTITY],
            ): _entity_selector("binary_sensor"),
        }
    )


class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Solar Savings", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(_DEFAULTS))
