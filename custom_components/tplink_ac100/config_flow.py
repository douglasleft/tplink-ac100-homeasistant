"""Config flow for TP-Link TL-AC100."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TLAC100ApiClient, TLAC100AuthError, TLAC100ConnectionError
from .const import (
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_CONSIDER_HOME,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=300)
        ),
        vol.Optional(CONF_CONSIDER_HOME, default=DEFAULT_CONSIDER_HOME): vol.All(
            int, vol.Range(min=0, max=600)
        ),
    }
)


class TLAC100ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TP-Link TL-AC100."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = TLAC100ApiClient(
                host=host,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=session,
            )

            try:
                await client.async_login()
            except TLAC100ConnectionError:
                errors["base"] = "cannot_connect"
            except TLAC100AuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"AC100 ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TLAC100OptionsFlow:
        return TLAC100OptionsFlow(config_entry)


class TLAC100OptionsFlow(config_entries.OptionsFlow):
    """Handle options for TP-Link TL-AC100."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            new_username = user_input.pop(CONF_USERNAME)
            new_password = user_input.pop(CONF_PASSWORD)

            old_username = self._config_entry.data[CONF_USERNAME]
            old_password = self._config_entry.data[CONF_PASSWORD]

            # If credentials changed, verify them before saving
            if new_username != old_username or new_password != old_password:
                session = async_get_clientsession(self.hass)
                client = TLAC100ApiClient(
                    host=self._config_entry.data[CONF_HOST],
                    username=new_username,
                    password=new_password,
                    session=session,
                )
                try:
                    await client.async_login()
                except TLAC100ConnectionError:
                    errors["base"] = "cannot_connect"
                except TLAC100AuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception during credential update")
                    errors["base"] = "unknown"

            if not errors:
                # Update config entry data with new credentials
                new_data = {**self._config_entry.data}
                new_data[CONF_USERNAME] = new_username
                new_data[CONF_PASSWORD] = new_password
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data=user_input)

        current_scan = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_home = self._config_entry.options.get(
            CONF_CONSIDER_HOME,
            self._config_entry.data.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
        )
        current_username = self._config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME)
        current_password = self._config_entry.data.get(CONF_PASSWORD, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=current_username): str,
                    vol.Required(CONF_PASSWORD, default=current_password): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                        int, vol.Range(min=10, max=300)
                    ),
                    vol.Optional(CONF_CONSIDER_HOME, default=current_home): vol.All(
                        int, vol.Range(min=0, max=600)
                    ),
                }
            ),
            errors=errors,
        )
