"""MikroTik Manager: read fleet data from the manager instead of each device."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ManagerAuthError, ManagerClient
from .const import CONF_VERIFY_SSL, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ManagerClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True),
    )

    async def _update() -> dict:
        try:
            return {"summary": await client.summary(), "devices": await client.devices()}
        except ManagerAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name=DOMAIN, update_method=_update,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
