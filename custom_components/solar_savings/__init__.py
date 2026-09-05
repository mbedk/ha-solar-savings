"""The Solar Savings integration.

Tracks money saved by a solar+battery system at grid pricing: direct solar
self-consumption, solar routed through the battery, and battery
price-arbitrage (grid energy bought cheap, discharged when the price is
higher) - each valued at the grid price in effect when the energy is
actually used, plus solar export revenue tracked separately. See
engine.py/ledger.py for the accounting model.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .engine import SolarSavingsEngine

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    engine = SolarSavingsEngine(hass, entry.entry_id, dict(entry.data))
    await engine.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = engine

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        engine: SolarSavingsEngine = hass.data[DOMAIN].pop(entry.entry_id)
        await engine.async_unload()
    return unload_ok
