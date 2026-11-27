"""MikroTik Manager: read fleet data from the manager instead of each device."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import importlib
import importlib.util
import logging
import sys

from aiohttp import ClientResponseError, web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import BASE_PRELOAD_PLATFORMS

from .api import ManagerAuthError, ManagerClient, ManagerForbiddenError
from .const import (
    CONF_SITE_ID, CONF_VERIFY_SSL, CONF_WEBHOOK_ID, CONF_WEBHOOK_SECRET, CONFIG_HEALTH_EVERY,
    DEFAULT_SCAN_INTERVAL, DOMAIN, EVENT_NAME, PLATFORMS, SITE_ALL, legacy_webhook_id,
)
from .logic import REFRESH_EVENTS, parse_config_health, parse_insights, parse_webhook, verify_signature
from .rates import RateTracker
from .repairs import clear_issues, sync_issues

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if CONF_WEBHOOK_ID not in entry.data:  # existing install: pin the old URL so nothing changes
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: legacy_webhook_id(entry.entry_id)})
    if webhook_id(entry) == legacy_webhook_id(entry.entry_id):
        ir.async_create_issue(
            hass, DOMAIN, f"webhook_guessable_{entry.entry_id}", is_fixable=False,
            severity=ir.IssueSeverity.WARNING, translation_key="webhook_guessable")
    else:
        ir.async_delete_issue(hass, DOMAIN, f"webhook_guessable_{entry.entry_id}")
    client = ManagerClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True),
        site_id(entry),
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
            return
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
        tracker.rates = {}  # do not republish old rates as current

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

    health_ok = True  # flips off when the token/manager cannot read config-health
    health_cache: dict[int, dict] = {}
    cycle = 0

    async def _health(devices: list[dict]) -> dict[int, dict]:
        """Config-health per online device, refreshed every Nth cycle (the manager caches it)."""
        nonlocal health_ok, cycle
        online = [d["id"] for d in devices if d.get("status") == "online"]
        for gone in set(health_cache) - set(online):
            health_cache.pop(gone)
        due = cycle % CONFIG_HEALTH_EVERY == 0
        cycle += 1
        if not health_ok:
            return {}

        async def one(did: int) -> None:
            nonlocal health_ok
            try:
                health_cache[did] = parse_config_health(await client.config_health(did))
            except ManagerForbiddenError:
                health_ok = False
                _LOGGER.debug("Token cannot read config-health; config-health sensors disabled")
            except ManagerAuthError:
                raise
            except Exception as err:  # noqa: BLE001
                health_cache.pop(did, None)  # unknown beats stale; retried next cycle
                _LOGGER.debug("config-health for device %s failed: %s", did, err)

        await asyncio.gather(*(one(d) for d in online if due or d not in health_cache))
        return dict(health_cache) if health_ok else {}

    insights_ok = True  # flips off (logged once) on 403/404

    async def _insights() -> dict | None:
        nonlocal insights_ok
        if not insights_ok:
            return None
        try:
            return parse_insights(await client.insights())
        except ManagerForbiddenError:
            insights_ok = False
            _LOGGER.debug("Token cannot read /api/operations/insights; needs-attention sensor disabled")
        except ManagerAuthError:
            raise
        except ClientResponseError as err:
            if err.status == 404:
                insights_ok = False
                _LOGGER.debug("Manager has no /api/operations/insights; needs-attention sensor disabled")
            else:
                _LOGGER.debug("insights failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("insights failed: %s", err)
        return None

    async def _update() -> dict:
        try:
            devices = await client.devices()
            detail = dict(await asyncio.gather(
                *(_per_device(d) for d in devices if d.get("status") == "online")
            ))
            config_health = await _health(devices)
            insights = await _insights()
            await _throughput()
            resources = await _resources()
            data = {
                "summary": await client.summary(), "devices": devices, "detail": detail,
                "rates": tracker.rates, "resources": resources,
                "config_health": config_health, "insights": insights,
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
    coordinator.client = client
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    _register_webhook(hass, entry, coordinator)
    _register_reload_code(hass)
    return True


def site_id(entry: ConfigEntry) -> str | None:
    """Chosen site (options win over the config-flow choice); None means the whole fleet."""
    value = entry.options.get(CONF_SITE_ID, entry.data.get(CONF_SITE_ID))
    return None if value in (None, "", SITE_ALL) else str(value)


def webhook_id(entry: ConfigEntry) -> str:
    return entry.data.get(CONF_WEBHOOK_ID) or legacy_webhook_id(entry.entry_id)


def _register_webhook(hass: HomeAssistant, entry: ConfigEntry, coordinator) -> None:
    async def _handle(hass: HomeAssistant, wid: str, request):
        # The secret is read per request and never logged.
        secret = entry.options.get(CONF_WEBHOOK_SECRET)
        body = await request.read()
        if not verify_signature(secret, body, request.headers.get("X-MTM-Signature")):
            _LOGGER.warning("Rejected MikroTik Manager webhook with a missing or invalid signature")
            return web.Response(status=401)
        payload = parse_webhook(body)
        if payload is None:
            return web.Response(status=400)
        hass.bus.async_fire(EVENT_NAME, {**payload, "entry_id": entry.entry_id})
        if payload["event"] in REFRESH_EVENTS:
            hass.async_create_task(coordinator.async_request_refresh())
        return web.Response(status=200)

    webhook.async_register(hass, DOMAIN, "MikroTik Manager", webhook_id(entry), _handle,
                           allowed_methods=["POST"])
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id(entry)))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        clear_issues(hass, hass.data[DOMAIN].pop(entry.entry_id).issue_ids)
    return ok


async def _reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _import_code(package: str) -> None:
    """Import the new code in the import executor, not the event loop.

    After an unload HA still lists "<domain>.<platform>" as loaded, so it
    would import the new modules in the event loop (and warn about it);
    once they are in sys.modules its own import is a cache hit.
    """
    module = importlib.import_module(package)
    # The new module's list, plus what HA preloads with a package (diagnostics, ...).
    for name in (*module.PLATFORMS, *BASE_PRELOAD_PLATFORMS):
        if importlib.util.find_spec(f"{package}.{name}") is not None:
            importlib.import_module(f"{package}.{name}")


def _forget_code(hass: HomeAssistant, package: str, domain: str) -> None:
    """Drop a package's modules so the next setup imports them from disk again.

    Home Assistant keeps its own copy of each imported integration module
    (hass.data["components"], keyed "<domain>" and "<domain>.<platform>") next to
    sys.modules; both have to go.
    """
    for cache, root in ((sys.modules, package), (hass.data.get("components", {}), domain),
                        (hass.data.get("missing_platforms", {}), domain)):
        for key in [n for n in cache if n == root or n.startswith(root + ".")]:
            del cache[key]
    importlib.invalidate_caches()  # or a file added since the last import may not be found


def _register_reload_code(hass: HomeAssistant) -> None:
    """Dev: mikrotik_manager.reload_code loads the Python files from disk without a restart."""

    async def _reload_code(call: ServiceCall) -> None:
        # Disabled and ignored entries are never set up, so they are not ours to reload.
        entries = hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=False
        )
        for entry in entries:
            if not await hass.config_entries.async_unload(entry.entry_id):
                raise HomeAssistantError(f"{DOMAIN} did not unload; restart Home Assistant instead")
        _forget_code(hass, __name__, DOMAIN)
        try:
            await hass.async_add_import_executor_job(_import_code, __name__)
        except Exception as err:
            # This handler stays registered, so the action works again once the code is fixed.
            raise HomeAssistantError(f"{DOMAIN} is unloaded: the new code did not load ({err}). "
                                     f"Fix it and call {DOMAIN}.reload_code again") from err
        failed = [e.title for e in entries if not await hass.config_entries.async_setup(e.entry_id)]
        if failed:
            raise HomeAssistantError(f"{DOMAIN} did not set up again for {failed}; see the log")

        _clear_marketplace_restart(hass)

    async_register_admin_service(hass, DOMAIN, "reload_code", _reload_code)


def _clear_marketplace_restart(hass: HomeAssistant) -> None:
    """Drop Marketplace's "restart to finish the update" repairs for Mikrotik Manager.

    Marketplace cannot see reload_code, so they would stay until a restart.
    """
    for (domain, issue_id), issue in list(ir.async_get(hass).issues.items()):
        if domain == "marketplace" and issue_id.startswith("restart_required_") and issue.issue_domain == DOMAIN:
            ir.async_delete_issue(hass, domain, issue_id)
