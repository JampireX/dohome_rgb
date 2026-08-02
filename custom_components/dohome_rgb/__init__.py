"""DoHome Home Assistant integration"""

from dataclasses import dataclass
from datetime import timedelta
from logging import getLogger

import homeassistant.helpers.config_validation as cv
from dohome.api import APIClient
from dohome.types.device import DeviceInfo as APIDeviceInfo
from dohome.types.device import parse_doit_device_info
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .constants import CONF_HOST, CONF_INFO, CONF_NAME, CONF_UNIQUE_ID, DOMAIN
from .discovery import async_discover_devices
from .transport import PersistentTCPStream

_LOGGER = getLogger(__name__)

CONFIG_SCHEMA = cv.platform_only_config_schema(DOMAIN)
PLATFORMS = [Platform.LIGHT]

# How often the network is re-scanned for not-yet-configured devices. A scan is
# cheap: a few tiny UDP broadcast packets and ~3s mostly spent awaiting replies,
# with all sockets closed afterwards — so a 1-minute cadence is safe.
DISCOVERY_INTERVAL = timedelta(minutes=1)
_DISCOVERY_STARTED = f"{DOMAIN}_discovery_started"


@dataclass
class DoHomeRuntimeData:
    """Per-entry objects shared between the integration and its platforms."""

    client: APIClient
    info: APIDeviceInfo
    transport: PersistentTCPStream


# Typed config entry: lets platforms read `entry.runtime_data` with full typing
# and removes the need for the global `hass.data[DOMAIN]` bookkeeping. This is
# the modern Home Assistant storage pattern (recommended since 2024.x).
type DoHomeConfigEntry = ConfigEntry[DoHomeRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up periodic background discovery of DoHome devices.

    `async_setup` runs whenever the integration is loaded (i.e. once at least
    one config entry exists), so the very first device is added through the
    config flow's scan/manual step; afterwards new bulbs surface here as
    "discovered device" cards in Settings -> Devices & Services.
    """
    # Guard against the unlikely double setup so we register a single timer.
    if hass.data.get(_DISCOVERY_STARTED):
        return True
    hass.data[_DISCOVERY_STARTED] = True

    async def _async_discover(_now=None) -> None:
        # The component is never torn down once loaded, so the timer below
        # outlives every config entry. Skip the scan (and the flow creation it
        # triggers) while no entry exists; it resumes automatically once a
        # device is configured again.
        if not hass.config_entries.async_entries(DOMAIN):
            return
        try:
            devices = await async_discover_devices()
        except Exception:  # noqa: BLE001 - discovery must never break HA
            _LOGGER.exception("DoHome discovery failed")
            return
        for device in devices.values():
            # Each call starts a discovery flow; HA dedupes by unique id, so
            # already-configured or already-pending devices are ignored.
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={
                    CONF_HOST: device.host,
                    CONF_UNIQUE_ID: device.unique_id,
                    CONF_NAME: device.name,
                },
            )

    _ = async_track_time_interval(hass, _async_discover, DISCOVERY_INTERVAL)
    _ = hass.async_create_background_task(_async_discover(), f"{DOMAIN}_discovery")
    return True


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

    # The transport keeps one TCP connection open for the entry's lifetime
    # (opened lazily on first request, reconnected on failure); constructors
    # perform no I/O, so the client is safe to build here and share.
    transport = PersistentTCPStream(entry.data[CONF_HOST])
    entry.runtime_data = DoHomeRuntimeData(
        client=APIClient(transport),
        info=entry.data[CONF_INFO],
        transport=transport,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DoHomeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Release the persistent TCP connection held by the transport.
        await entry.runtime_data.transport.close()
    return unload_ok
