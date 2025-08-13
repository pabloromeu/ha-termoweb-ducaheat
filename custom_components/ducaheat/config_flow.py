from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_USERNAME, CONF_PASSWORD, CONF_BASE_URL, CONF_BASIC_B64, CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL, DEFAULT_BASE_URL, DUCAHEAT_BASIC_AUTH_B64,
    MIN_POLL_INTERVAL, MAX_POLL_INTERVAL,
)
from .api import DucaheatApi

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Required(CONF_BASIC_B64, default=defaults.get(CONF_BASIC_B64, DUCAHEAT_BASIC_AUTH_B64)): str,
            vol.Required(CONF_POLL_INTERVAL, default=defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)): vol.All(
                int, vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
            ),
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        _LOGGER.info("Ducaheat config flow start")
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_schema({}))

        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]
        base_url = user_input[CONF_BASE_URL].rstrip("/")
        basic_b64 = user_input[CONF_BASIC_B64].strip()
        poll = int(user_input[CONF_POLL_INTERVAL])

        # Validate: token + a lightweight probe (devices)
        errors: dict[str, str] = {}
        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            api = DucaheatApi(session, base_url=base_url, basic_b64=basic_b64)
            await api.login(username, password)
            try:
                # probe only; don't fail if empty
                await api.list_devices()
            except Exception:
                pass
        except Exception:
            _LOGGER.exception("Validation failed")
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

        return self.async_create_entry(
            title=f"Ducaheat ({username})",
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_BASE_URL: base_url,
                CONF_BASIC_B64: basic_b64,
                CONF_POLL_INTERVAL: poll,
            },
        )