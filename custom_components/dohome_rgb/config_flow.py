"""DoHome Home Assistant integration config flow."""

from __future__ import annotations

import asyncio
from logging import getLogger
from typing import override

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from dohome.api import APIClient
from dohome.exc.base import DoHomeException
from dohome.transport import TCPStream
from dohome.types.device import DeviceInfo as APIDeviceInfo
from dohome.types.device import encode_device_id
from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.typing import DiscoveryInfoType

from .constants import (
    CONF_DEVICES,
    CONF_HOST,
    CONF_INFO,
    CONF_NAME,
    CONF_UNIQUE_ID,
    DOMAIN,
)
from .discovery import DiscoveredDevice, async_discover_devices

_LOGGER = getLogger(__name__)

# Marks a discovery flow whose device the user already picked, so it is added
# without an extra confirmation card.
_CONF_CONFIRMED = "confirmed"

# Connection failures raised while probing the device. Narrowed from a bare
# `except Exception` so real programming errors are not swallowed:
#   - asyncio.TimeoutError / OSError: socket problems while connecting
#   - DoHomeException: protocol-level errors from the library
#   - ValueError: device id / state parsing failed
_CONNECT_ERRORS = (asyncio.TimeoutError, DoHomeException, OSError, ValueError)


class DoHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DoHome bulbs."""

    VERSION: int = 2

    def __init__(self) -> None:
        # Devices found by the empty-host scan, keyed by unique id.
        self._discovered: dict[str, DiscoveredDevice] = {}
        # Device being confirmed from a background discovery card.
        self._discovery: DiscoveredDevice | None = None

    async def _async_read_device(self, hostname: str) -> tuple[str, APIDeviceInfo]:
        """Connect to the device and return its unique id and info."""
        client = APIClient(TCPStream(hostname))
        info = await client.get_device_info()
        return encode_device_id(info["hardware"]), info

    async def _async_available_devices(self) -> dict[str, DiscoveredDevice]:
        """Scan the LAN and drop devices that are already configured."""
        devices = await async_discover_devices()
        configured = self._async_current_ids()
        return {
            uid: device
            for uid, device in devices.items()
            if uid not in configured
        }

    @override
    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Initial step: a single optional host field.

        With a host given, the device is added directly. Left empty, the local
        network is scanned and the found devices are offered for selection.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            hostname = (user_input.get(CONF_HOST) or "").strip()
            if hostname:
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
            else:
                self._discovered = await self._async_available_devices()
                if self._discovered:
                    return await self.async_step_pick()
                errors["base"] = "no_devices_found"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_HOST, default=""): str}),
            errors=errors,
        )

    async def async_step_pick(
        self, user_input: dict[str, list[str]] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose which discovered devices to add."""
        if user_input is not None:
            selected = user_input[CONF_DEVICES]
            if selected:
                first = self._discovered[selected[0]]
                try:
                    unique_id, info = await self._async_read_device(first.host)
                except _CONNECT_ERRORS:
                    return self.async_abort(reason="cannot_connect")
                _ = await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                # A flow can only create one entry, so the remaining picks are
                # added through auto-confirmed discovery flows.
                for uid in selected[1:]:
                    device = self._discovered[uid]
                    discovery_flow.async_create_flow(
                        self.hass,
                        DOMAIN,
                        context={"source": SOURCE_INTEGRATION_DISCOVERY},
                        data={
                            CONF_HOST: device.host,
                            CONF_UNIQUE_ID: device.unique_id,
                            CONF_NAME: device.name,
                            _CONF_CONFIRMED: True,
                        },
                    )
                return self.async_create_entry(
                    title=first.name,
                    data={CONF_HOST: first.host, CONF_INFO: info},
                )

        options = {
            uid: f"{device.name} ({device.host})"
            for uid, device in self._discovered.items()
        }
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema({vol.Required(CONF_DEVICES): cv.multi_select(options)}),
        )

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle a device surfaced by the background network scan."""
        host = discovery_info[CONF_HOST]
        unique_id = discovery_info[CONF_UNIQUE_ID]
        name = discovery_info.get(CONF_NAME) or host

        _ = await self.async_set_unique_id(unique_id)
        # Abort if already set up; if the IP changed, refresh and reload it.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovery = DiscoveredDevice(unique_id=unique_id, host=host, name=name)
        self.context["title_placeholders"] = {CONF_NAME: name}

        if discovery_info.get(_CONF_CONFIRMED):
            return await self._async_create_discovered()
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding a discovered device."""
        assert self._discovery is not None
        if user_input is not None:
            return await self._async_create_discovered()

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                CONF_NAME: self._discovery.name,
                CONF_HOST: self._discovery.host,
            },
        )

    async def _async_create_discovered(self) -> ConfigFlowResult:
        """Read full device info and create the entry for a discovered device."""
        assert self._discovery is not None
        try:
            _, info = await self._async_read_device(self._discovery.host)
        except _CONNECT_ERRORS:
            return self.async_abort(reason="cannot_connect")
        return self.async_create_entry(
            title=self._discovery.name,
            data={CONF_HOST: self._discovery.host, CONF_INFO: info},
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
