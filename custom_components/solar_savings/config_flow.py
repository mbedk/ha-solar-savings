"""Config flow for Solar Savings."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN, INPUT_FIELDS

_DEFAULTS = {field.key: field.default for field in INPUT_FIELDS}


def _schema(defaults: dict[str, str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(field.key, default=defaults[field.key]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=field.domain)
            )
            for field in INPUT_FIELDS
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
