"""DoHome Home Assistant integration config flow."""

from __future__ import annotations

import asyncio
from logging import getLogger
from typing import override

import voluptuous as vol
from dohome.api import APIClient
from dohome.exc.base import DoHomeException
from dohome.transport import TCPStream
from dohome.types.device import DeviceInfo as APIDeviceInfo
from dohome.types.device import encode_device_id
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .constants import CONF_HOST, CONF_INFO, DOMAIN

_LOGGER = getLogger(__name__)

# Connection failures raised while probing the device. Narrowed from a bare
# `except Exception` so real programming errors are not swallowed:
#   - asyncio.TimeoutError / OSError: socket problems while connecting
#   - DoHomeException: protocol-level errors from the library
#   - ValueError: device id / state parsing failed
_CONNECT_ERRORS = (asyncio.TimeoutError, DoHomeException, OSError, ValueError)


class DoHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DoHome bulbs."""

    VERSION: int = 2

    async def _async_read_device(self, hostname: str) -> tuple[str, APIDeviceInfo]:
        """Connect to the device and return its unique id and info."""
        client = APIClient(TCPStream(hostname))
        info = await client.get_device_info()
        return encode_device_id(info["hardware"]), info

    @override
    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the device address is entered."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # CONF_HOST is vol.Required, so it is always present here.
            hostname = user_input[CONF_HOST]
            try:
                unique_id, info = await self._async_read_device(hostname)
            except _CONNECT_ERRORS as exc:
                errors["base"] = "cannot_connect"
                _LOGGER.exception("Error connecting to device: %s", exc)
            else:
                _ = await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=hostname,
                    data={CONF_HOST: hostname, CONF_INFO: info},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Change the host of an already configured device.

        Replaces the previous OptionsFlow, which stored the new host in
        entry.options while async_setup_entry only ever reads entry.data —
        so changing the host there was silently ignored.
        """
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            hostname = user_input[CONF_HOST]
            try:
                unique_id, info = await self._async_read_device(hostname)
            except _CONNECT_ERRORS as exc:
                errors["base"] = "cannot_connect"
                _LOGGER.exception("Error connecting to device: %s", exc)
            else:
                # Guard against pointing the entry at a different bulb.
                if unique_id != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                # Persist into entry.data (the source setup reads from) and
                # reload so the new host takes effect immediately.
                _ = self.hass.config_entries.async_update_entry(
                    entry, data={CONF_HOST: hostname, CONF_INFO: info}
                )
                _ = await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
            errors=errors,
        )
