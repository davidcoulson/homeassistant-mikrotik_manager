"""Config flow: manager URL, read-scope API token, TLS verification."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ManagerAuthError, ManagerClient
from .const import CONF_VERIFY_SSL, DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
