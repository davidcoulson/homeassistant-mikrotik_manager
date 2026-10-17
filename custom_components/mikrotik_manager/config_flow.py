"""Config flow: manager URL, read-scope API token, TLS verification."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ManagerAuthError, ManagerClient
from .const import CONF_ALL_PORTS, CONF_THROUGHPUT_PORTS, CONF_VERIFY_SSL, DOMAIN


class OptionsFlow(config_entries.OptionsFlow):
    """Choose which physical ports get rx/tx throughput sensors (default: none)."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        choices: dict[str, str] = {}
        if coordinator is not None:
            names = {d["id"]: d.get("name") or str(d["id"]) for d in coordinator.data["devices"]}
            for did, det in coordinator.data["detail"].items():
                for p in det["ports"]:
                    choices[f"{did}/{p['name']}"] = f"{names.get(did, did)}: {p['name']}"
        current = self.config_entry.options
        selected = [k for k in current.get(CONF_THROUGHPUT_PORTS, []) if k in choices]
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_ALL_PORTS, default=current.get(CONF_ALL_PORTS, False)): bool,
                vol.Optional(CONF_THROUGHPUT_PORTS, default=selected): cv.multi_select(choices),
            }),
        )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

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
