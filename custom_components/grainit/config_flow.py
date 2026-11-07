"""Config flow for Grainit."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import dt as dt_util

from .api import GrainitAuthError, GrainitClient, GrainitConnectionError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class GrainitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _test(self, email: str, password: str) -> str | None:
        session = async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar())
        client = GrainitClient(session, email, password)
        try:
            await client.login()
            today = dt_util.now().date()
            await client.get_loads(today - timedelta(days=1), today)
        except GrainitAuthError:
            return "invalid_auth"
        except GrainitConnectionError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()
            error = await self._test(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await self._test(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GrainitOptionsFlow()


class GrainitOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(int, vol.Range(min=5, max=1440))}
            ),
        )
