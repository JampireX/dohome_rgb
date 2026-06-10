"""DoHome Home Assistant integration"""

from dataclasses import dataclass

import homeassistant.helpers.config_validation as cv
from dohome.api import APIClient
from dohome.transport import TCPStream
from dohome.types.device import DeviceInfo as APIDeviceInfo
from dohome.types.device import parse_doit_device_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .constants import CONF_HOST, CONF_INFO, DOMAIN

CONFIG_SCHEMA = cv.platform_only_config_schema(DOMAIN)
PLATFORMS = [Platform.LIGHT]


@dataclass
class DoHomeRuntimeData:
    """Per-entry objects shared between the integration and its platforms."""

    client: APIClient
    info: APIDeviceInfo


# Typed config entry: lets platforms read `entry.runtime_data` with full typing
# and removes the need for the global `hass.data[DOMAIN]` bookkeeping. This is
# the modern Home Assistant storage pattern (recommended since 2024.x).
type DoHomeConfigEntry = ConfigEntry[DoHomeRuntimeData]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry to new version."""
    if config_entry.version == 1:
        old_data = config_entry.data
        parsed_info = parse_doit_device_info({**old_data[CONF_INFO]})
        _ = hass.config_entries.async_update_entry(
            config_entry,
            data={
                CONF_HOST: old_data[CONF_HOST],
                CONF_INFO: parsed_info,
            },
            version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DoHomeConfigEntry) -> bool:
    """Set up DoHome RGB from a config entry."""
    assert entry.unique_id is not None

    # TCPStream/APIClient constructors perform no I/O (the socket is opened
    # per-request), so the client is safe to build once and reuse for the
    # entry's lifetime instead of recreating it inside the light platform.
    client = APIClient(TCPStream(entry.data[CONF_HOST]))
    entry.runtime_data = DoHomeRuntimeData(client=client, info=entry.data[CONF_INFO])

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DoHomeConfigEntry) -> bool:
    """Unload a config entry."""
    # runtime_data is released together with the entry, so unloading the
    # platforms is the only cleanup required (no manual hass.data teardown).
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
