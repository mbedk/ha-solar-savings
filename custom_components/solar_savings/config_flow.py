"""Config flow for Solar Savings."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import DOMAIN, ERROR_DUPLICATE, INPUT_FIELDS, PowerField

_DEFAULTS = {field.key: field.default for field in INPUT_FIELDS}


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                field.key, default=defaults.get(field.key, field.default)
            ): field.selector()
            for field in INPUT_FIELDS
        }
    )


def _validate(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Check what the user picked, per field.

    Everything here is a mistake the engine cannot detect at runtime: a
    missing entity reads as 0.0 forever, and a power sensor in W reads as a
    plausible-looking number that is 1000x too big. Both produce totals that
    look fine on the day and are badly wrong a month later, so they're worth
    catching while the form is still open.
    """
    errors: dict[str, str] = {}
    for field in INPUT_FIELDS:
        error = field.check(hass, user_input.get(field.key))
        if error is not None:
            errors[field.key] = error

    # The four power fields measure four physically distinct flows. The same
    # entity in two of them is always a mis-pick, and one that would silently
    # double-count - e.g. solar power also given as feed-in power would credit
    # every kWh as both self-consumed and exported.
    seen: dict[str, str] = {}
    for field in INPUT_FIELDS:
        if not isinstance(field, PowerField):
            continue
        value = user_input.get(field.key)
        if value in seen:
            errors[field.key] = errors[seen[value]] = ERROR_DUPLICATE
        else:
            seen[value] = field.key

    return errors


class SolarSavingsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Savings."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Solar Savings", data=user_input)

        # Re-show the user's own answers on a failed submit, not the defaults,
        # so a single bad pick doesn't cost them the other seven.
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or _DEFAULTS),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Repoint the integration at different source entities, or correct
        the system cost.

        Updates the entry in place so the entry_id - and with it the stored
        ledger - survives. Removing and re-adding the integration would not:
        the store is keyed by entry_id, so a new entry starts from zero.
        """
        entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(self.hass, user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(entry.data)),
            errors=errors,
        )
