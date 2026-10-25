"""Config flow: manager URL, read-scope API token, TLS verification."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.components import webhook
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ManagerAuthError, ManagerClient
from .const import (
    CONF_ALL_PORTS, CONF_SITE_ID, CONF_THROUGHPUT_PORTS, CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET, DOMAIN, SITE_ALL,
)

_SECRET_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


def site_choices(sites: list[dict]) -> dict[str, str]:
    """value -> label for the site selector, with the whole fleet first."""
    out = {SITE_ALL: "All sites"}
    for s in sites:
        if isinstance(s, dict) and s.get("id") is not None:
            out[str(s["id"])] = s.get("name") or f"Site {s['id']}"
    return out


def _webhook_url(hass, entry_id: str) -> str:
    wid = f"{DOMAIN}_{entry_id}"
    try:
        return webhook.async_generate_url(hass, wid)
    except Exception:  # noqa: BLE001 - no URL configured in HA
        return f"<your Home Assistant URL>/api/webhook/{wid}"


class OptionsFlow(config_entries.OptionsFlow):
    """Choose which physical ports get rx/tx throughput sensors (default: none)."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        choices: dict[str, str] = {}
        sites: dict[str, str] = {}
        if coordinator is not None:
            try:
                sites = site_choices(await coordinator.client.sites())
            except Exception:  # noqa: BLE001 - sites are optional
                sites = {}
            names = {d["id"]: d.get("name") or str(d["id"]) for d in coordinator.data["devices"]}
            for did, det in coordinator.data["detail"].items():
                for p in det["ports"]:
                    choices[f"{did}/{p['name']}"] = f"{names.get(did, did)}: {p['name']}"
        current = self.config_entry.options
        selected = [k for k in current.get(CONF_THROUGHPUT_PORTS, []) if k in choices]
        schema: dict = {}
        if len(sites) > 2:  # "All sites" plus at least two real ones
            chosen = current.get(CONF_SITE_ID, self.config_entry.data.get(CONF_SITE_ID)) or SITE_ALL
            schema[vol.Optional(CONF_SITE_ID, default=chosen if chosen in sites else SITE_ALL)] = (
                vol.In(sites)
            )
        schema[vol.Optional(
            CONF_WEBHOOK_SECRET, description={"suggested_value": current.get(CONF_WEBHOOK_SECRET)}
        )] = _SECRET_SELECTOR
        schema[vol.Optional(CONF_ALL_PORTS, default=current.get(CONF_ALL_PORTS, False))] = bool
        schema[vol.Optional(CONF_THROUGHPUT_PORTS, default=selected)] = cv.multi_select(choices)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "webhook_url": _webhook_url(self.hass, self.config_entry.entry_id)
            },
        )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

    async def async_step_site(self, user_input=None):
        if user_input is not None:
            data = {**self._data}
            if user_input[CONF_SITE_ID] != SITE_ALL:
                data[CONF_SITE_ID] = user_input[CONF_SITE_ID]
            return self.async_create_entry(title="MikroTik Manager", data=data)
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema({vol.Required(CONF_SITE_ID, default=SITE_ALL): vol.In(self._sites)}),
        )

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = ManagerClient(
                async_get_clientsession(self.hass), user_input[CONF_URL],
                user_input[CONF_TOKEN], user_input[CONF_VERIFY_SSL],
            )
            try:
                await client.summary()
            except ManagerAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
                self._abort_if_unique_id_configured()
                self._data = user_input
                try:  # the site step is skipped when sites cannot be listed or there is only one
                    self._sites = site_choices(await client.sites())
                except Exception:  # noqa: BLE001
                    self._sites = {}
                if len(self._sites) > 2:
                    return await self.async_step_site()
                return self.async_create_entry(title="MikroTik Manager", data=user_input)
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_VERIFY_SSL, default=True): bool,
            }),
        )
