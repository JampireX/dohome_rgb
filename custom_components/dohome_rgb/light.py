"""Support for DoHome RGB Lights"""

import asyncio
from collections.abc import Coroutine
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

# Synthetic "no effect" entry shown first in the effect list: selecting it stops
# a running hardware effect by re-applying the current static colour/temperature.
EFFECT_OFF = "None"
_EFFECT_LIST = [EFFECT_OFF, *EFFECTS]

# Errors raised while talking to the device. Besides connection problems
# (timeout / socket / protocol), the dohome-api parsing helpers raise plain
# ValueError/KeyError on a malformed or out-of-range response (json decode,
# parse_doit_light_state, kelvin_to_dowhite, apply_brightness, ...). The config
# flow already narrows to the same set; the entity must too, otherwise a single
# garbled poll bubbles an uncaught exception out of async_update every cycle.
_DEVICE_ERRORS = (asyncio.TimeoutError, DoHomeException, OSError, ValueError, KeyError)


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
    _attr_effect_list = _EFFECT_LIST
    _attr_effect = EFFECT_OFF
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
            # The device reports its real model code as the type value
            # (e.g. "DT-WYRGB"); prefer it over the generic enum name
            # ("RGBW_BULB").
            model=device_type.value,
            sw_version=info["version"],
            hw_version=hw_info["chip"],
            serial_number=hw_info["sid"],
        )

    async def _update_state(self) -> None:
        try:
            state = await self._client.get_state()
        except _DEVICE_ERRORS:
            self._attr_available = False
            return
        self._attr_available = True

        # While a hardware effect is running the device cannot report a
        # meaningful on/off state: effect frames pass through all-zero RGBW,
        # which the library decodes as is_on=False. Keep the optimistic state
        # instead of letting a poll flip the light "off" mid-effect.
        if self._state_known and self._attr_effect != EFFECT_OFF:
            self._attr_is_on = True
            return

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
        """Turn the light on.

        The new state is written to Home Assistant optimistically (before the
        network round-trip) so the UI reacts instantly; a failed send then
        marks the entity unavailable.
        """
        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            self._state_known = True
            self._attr_effect = effect
            self._attr_is_on = True
            self.async_write_ha_state()
            if effect == EFFECT_OFF:
                # Stop the running effect by re-applying a static state.
                await self._async_send(self._async_apply_color())
            else:
                await self._async_send(self._client.set_effect(EFFECTS[effect]))
            return

        has_explicit_state = (
            ATTR_BRIGHTNESS in kwargs
            or ATTR_RGB_COLOR in kwargs
            or ATTR_COLOR_TEMP_KELVIN in kwargs
        )

        # Apply an explicit colour/brightness/temperature first so that it is
        # not dropped when an effect is requested in the same service call. A
        # manual colour change also exits effect mode.
        if has_explicit_state:
            self._attr_effect = EFFECT_OFF
            if ATTR_BRIGHTNESS in kwargs:
                self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            if ATTR_RGB_COLOR in kwargs:
                self._attr_color_mode = ColorMode.RGB
                self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
            elif ATTR_COLOR_TEMP_KELVIN in kwargs:
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]

        if has_explicit_state:
            self._state_known = True
        self._attr_is_on = True
        self.async_write_ha_state()

        if not self._state_known:
            await self._async_send(self._client.set_power(True))
        else:
            await self._async_send(self._async_apply_color())

    async def _async_send(self, request: Coroutine[Any, Any, None]) -> None:
        """Await a device command, tracking availability from the outcome."""
        try:
            await request
            self._attr_available = True
        except _DEVICE_ERRORS:
            self._attr_available = False
        self.async_write_ha_state()

    async def _async_apply_color(self) -> None:
        """Send the current static colour/temperature to the device.

        Also used to stop a running hardware effect (the effect ends as soon as
        a normal state is written).
        """
        brightness = self._attr_brightness or 255
        if self._attr_color_mode == ColorMode.COLOR_TEMP:
            temp = self._attr_color_temp_kelvin or KELVIN_MIN
            await self._client.set_white(temp, brightness)
        else:
            color = self._attr_rgb_color or (255, 255, 255)
            await self._client.set_color(color, brightness)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        self._attr_is_on = False
        self.async_write_ha_state()
        await self._async_send(self._client.set_power(False))
