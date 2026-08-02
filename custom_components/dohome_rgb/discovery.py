"""DoHome LAN discovery over UDP broadcast.

The bundled ``dohome-api`` ``discover()`` helper validates ping responses
against a ``compandy_id`` key, but real devices send the correctly spelled
``company_id`` field, so the library raises ``ValueError`` on every response.
We therefore re-implement discovery here with tolerant parsing built on the
low-level UDP broadcast transport.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from logging import getLogger

from dohome.api.message import decode_datagram, format_datagram
from dohome.transport import UDPBroadcast
from dohome.types.common import DoDict
from dohome.types.constants import DatagramCommand
from dohome.types.device import encode_device_id, parse_hardware_info

_LOGGER = getLogger(__name__)

# Pre-encoded ping datagram (kept module-level: it never changes).
_PING = (format_datagram({"cmd": DatagramCommand.PING}) + "\n").encode()

# UDP is lossy, so each subnet is pinged a few times within a short window.
_ROUNDS = 3
_READ_TIMEOUT = 1.0


@dataclass(frozen=True)
class DiscoveredDevice:
    """A DoHome device found on the local network."""

    unique_id: str
    host: str
    name: str


def _broadcast_targets() -> list[str]:
    """Return the broadcast addresses to ping.

    The library's own ``get_discovery_host()`` returns an empty string on
    multi-homed hosts (very common: VPN/Docker/Hyper-V adapters), so we derive
    a /24 broadcast for every local IPv4 instead and always include the global
    broadcast as a fallback.
    """
    targets: list[str] = ["255.255.255.255"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            # getaddrinfo's sockaddr is a union type; for AF_INET the first
            # element is always the address string.
            ip = str(info[4][0])
            if ip.startswith(("127.", "169.254.")):
                continue
            bcast = ".".join(ip.split(".")[:3] + ["255"])
            if bcast not in targets:
                targets.append(bcast)
    except OSError as err:
        _LOGGER.debug("Could not enumerate local addresses: %s", err)
    return targets


def _parse(raw: DoDict) -> DiscoveredDevice | None:
    """Turn a decoded pong datagram into a device, or None if unusable."""
    if raw.get("cmd") != "pong":
        return None
    # `sta_ip` is the device's address on the LAN; `host_ip` is its softAP and
    # is not routable from Home Assistant.
    host = raw.get("sta_ip")
    device_id = raw.get("device_id")
    if not isinstance(host, str) or not isinstance(device_id, str):
        return None
    try:
        # Derive the unique id exactly like the config entry does, so a
        # discovered device dedupes against an already configured one.
        unique_id = encode_device_id(parse_hardware_info(device_id))
    except (ValueError, KeyError):
        return None
    name = raw.get("device_name")
    return DiscoveredDevice(
        unique_id=unique_id,
        host=host,
        name=name if isinstance(name, str) and name else host,
    )


async def _async_scan_target(target: str) -> list[DiscoveredDevice]:
    transport = UDPBroadcast(host=target, read_timeout=_READ_TIMEOUT)
    devices: list[DiscoveredDevice] = []
    try:
        for _ in range(_ROUNDS):
            try:
                messages = await transport.send(_PING)
            except OSError as err:
                _LOGGER.debug("Broadcast to %s failed: %s", target, err)
                break
            for message in messages:
                try:
                    raw = decode_datagram(message)
                except (ValueError, UnicodeDecodeError):
                    continue
                device = _parse(raw)
                if device is not None:
                    devices.append(device)
    finally:
        transport.close()
    return devices


async def async_discover_devices() -> dict[str, DiscoveredDevice]:
    """Broadcast a ping on every local subnet and return devices by unique id."""
    targets = _broadcast_targets()
    results = await asyncio.gather(
        *(_async_scan_target(target) for target in targets),
        return_exceptions=True,
    )
    found: dict[str, DiscoveredDevice] = {}
    for result in results:
        if isinstance(result, BaseException):
            _LOGGER.debug("Discovery target error: %s", result)
            continue
        for device in result:
            found[device.unique_id] = device
    return found
