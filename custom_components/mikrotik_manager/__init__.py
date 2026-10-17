"""MikroTik Manager: read fleet data from the manager instead of each device."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from aiohttp import ClientResponseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ManagerAuthError, ManagerClient
from .const import CONF_VERIFY_SSL, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .rates import RateTracker
from .repairs import clear_issues, sync_issues

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ManagerClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True),
    )

    async def _per_device(device: dict) -> tuple[int, dict]:
        """Ports and PoE for one online device; a failure only blanks that device."""
        out: dict = {"ports": [], "poe": {}}
        try:
            out["ports"] = [
                p for p in await client.ports(device["id"])
                if str(p.get("type", "")).lower().startswith(("ether", "sfp", "combo"))
                or str(p.get("name", "")).lower().startswith(("ether", "sfp", "combo"))
            ]
            out["poe"] = {p["port"]: p for p in await client.poe(device["id"])}
        except ManagerAuthError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("ports/poe for device %s failed: %s", device["id"], err)
        return device["id"], out

    tracker = RateTracker()
    issues: set[str] = set()
    throughput_ok = True  # flips off (logged once) when the manager lacks the endpoint

    async def _throughput() -> None:
        nonlocal throughput_ok
        if not throughput_ok:
            return
        try:
            tracker.update(await client.interfaces_latest())
        except ManagerAuthError:
            raise
        except ClientResponseError as err:
            if err.status == 404:
                throughput_ok = False
                _LOGGER.debug("Manager has no /api/metrics/interfaces/latest; throughput sensors disabled")
            else:
                _LOGGER.debug("interfaces/latest failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("interfaces/latest failed: %s", err)

    resources_ok = True  # flips off (logged once) when the manager lacks the endpoint

    async def _resources() -> dict:
        nonlocal resources_ok
        if not resources_ok:
            return {}
        try:
            return await client.resources_latest()
        except ManagerAuthError:
            raise
        except ClientResponseError as err:
            if err.status == 404:
                resources_ok = False
                _LOGGER.debug("Manager has no /api/metrics/resources/latest; CPU/memory sensors disabled")
            else:
                _LOGGER.debug("resources/latest failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("resources/latest failed: %s", err)
        return {}

    async def _update() -> dict:
        try:
            devices = await client.devices()
            detail = dict(await asyncio.gather(
                *(_per_device(d) for d in devices if d.get("status") == "online")
            ))
            await _throughput()
            resources = await _resources()
            data = {
                "summary": await client.summary(), "devices": devices, "detail": detail,
                "rates": tracker.rates, "resources": resources,
            }
            sync_issues(hass, entry.entry_id, data, issues)
            return data
        except ManagerAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name=DOMAIN, update_method=_update,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.issue_ids = issues
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        clear_issues(hass, hass.data[DOMAIN].pop(entry.entry_id).issue_ids)
    return ok


async def _reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
