"""Support for DoHome RGB Lights"""

import asyncio
from datetime import timedelta
from typing import Any, override

from dohome.api import APIClient
from dohome.exc.base import DoHomeException
from dohome.types.constants import Effect, KELVIN_MAX, KELVIN_MIN
from dohome.types.device import DeviceInfo as APIDeviceInfo
from dohome.types.device import DeviceType, encode_device_id
from dohome.types.light import LightMode
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DoHomeConfigEntry
from .constants import DOMAIN

SCAN_INTERVAL = timedelta(seconds=10)

# Built-in hardware effects exposed as Home Assistant light effects. The device
# cannot report which effect is running, so the selection is tracked locally.
_COLOR_TOKENS = frozenset({"RG", "RB", "GB", "RGB"})


def _effect_name(name: str) -> str:
    """Turn an Effect enum name (RGB_STROBE) into a label (RGB Strobe)."""
    return " ".join(
        word if word in _COLOR_TOKENS else word.capitalize()
        for word in name.split("_")
    )


EFFECTS: dict[str, Effect] = {_effect_name(effect.name): effect for effect in Effect}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DoHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the light from a config entry."""
    # Client and parsed device info are created once in __init__ and shared
    # via runtime_data, so the platform no longer rebuilds the TCP client.
    data = config_entry.runtime_data
    async_add_entities([DoHomeLightEntity(data.client, data.info)])


class DoHomeLightEntity(LightEntity):
    """DoHome light entity"""

    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(EFFECTS)
    _attr_min_color_temp_kelvin = KELVIN_MIN
    _attr_max_color_temp_kelvin = KELVIN_MAX

    _attr_color_mode = ColorMode.COLOR_TEMP

    _client: APIClient
    _info: APIDeviceInfo
    _state_known = False

    def __init__(self, client: APIClient, info: APIDeviceInfo):
        self._client = client
        self._info = info

        hw_info = info["hardware"]
        unique_id = encode_device_id(info["hardware"])
        device_type = DeviceType(hw_info["type"])

        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer="DoHome",
            model=device_type.name,
            sw_version=info["version"],
            hw_version=hw_info["chip"],
            serial_number=hw_info["sid"],
        )

    async def _update_state(self) -> None:
        try:
            state = await self._client.get_state()
        except (asyncio.TimeoutError, DoHomeException, OSError):
            self._attr_available = False
            return
        self._attr_available = True
        self._attr_is_on = state["is_on"]
        if not state["is_on"]:
            return

        # The device only reports a lossy state (in RGB mode brightness is
        # always 255 and temperature 0), so trust the hardware once to seed
        # the initial values and keep them locally afterwards.
        if not self._state_known:
            if state["mode"] == LightMode.WHITE:
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._attr_color_temp_kelvin = state["temperature"]
                self._attr_brightness = state["brightness"]
            else:
                self._attr_color_mode = ColorMode.RGB
                self._attr_rgb_color = state["color"]
                self._attr_brightness = state["brightness"]
            self._state_known = True

    async def async_update(self) -> None:
        """Reads state from the device"""
        await self._update_state()
        self.async_write_ha_state()

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            try:
                await self._client.set_effect(EFFECTS[effect])
            except (asyncio.TimeoutError, DoHomeException, OSError):
                self._attr_available = False
                return
            self._state_known = True
            self._attr_effect = effect
            self._attr_is_on = True
            return

        has_explicit_state = (
            ATTR_BRIGHTNESS in kwargs
            or ATTR_RGB_COLOR in kwargs
            or ATTR_COLOR_TEMP_KELVIN in kwargs
        )

        if has_explicit_state:
            self._state_known = True
            # A manual colour/brightness change exits effect mode.
            self._attr_effect = None
            if ATTR_BRIGHTNESS in kwargs:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            if ATTR_RGB_COLOR in kwargs:
                self._attr_color_mode = ColorMode.RGB
                self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
            elif ATTR_COLOR_TEMP_KELVIN in kwargs:
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]

        try:
            if not self._state_known:
                await self._client.set_power(True)
            elif self._attr_color_mode == ColorMode.COLOR_TEMP:
                temp = self._attr_color_temp_kelvin or KELVIN_MIN
                brightness = self._attr_brightness or 255
                await self._client.set_white(temp, brightness)
            else:
                color = self._attr_rgb_color or (255, 255, 255)
                brightness = self._attr_brightness or 255
                await self._client.set_color(color, brightness)
        except (asyncio.TimeoutError, DoHomeException, OSError):
            self._attr_available = False
            return
        self._attr_is_on = True

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self._client.set_power(False)
            self._attr_is_on = False
        except (asyncio.TimeoutError, DoHomeException, OSError):
            self._attr_available = False
