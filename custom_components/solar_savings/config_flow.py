"""Config flow for Solar Savings."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN, INPUT_FIELDS

_DEFAULTS = {field.key: field.default for field in INPUT_FIELDS}


def _schema(defaults: dict[str, str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                field.key, default=defaults.get(field.key, field.default)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=field.domain)
            )
            for field in INPUT_FIELDS
        }
    )


class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Solar Savings", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(_DEFAULTS))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Repoint the integration at different source entities.

        Updates the entry in place so the entry_id - and with it the stored
        ledger - survives. Removing and re-adding the integration would not:
        the store is keyed by entry_id, so a new entry starts from zero.
        """
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reconfigure", data_schema=_schema(dict(entry.data))
        )
