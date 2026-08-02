"""Persistent TCP transport for DoHome devices.

The stock ``dohome-api`` ``TCPStream`` opens a fresh TCP connection for every
request, which adds a full handshake (~50-200 ms on the ESP8266) to each
command. This transport keeps one connection open and reuses it, reconnecting
transparently when the device drops it.

Design constraints:

- The ESP8266 handles concurrent connections poorly, so all requests are
  serialized through a lock. This also prevents the 10-second state poll from
  competing with a user-issued command for the socket.
- Responses are flat JSON without a guaranteed terminator, so a response is
  considered complete once the accumulated bytes parse as JSON.
- Any failure (timeout, socket error, peer EOF) closes the connection; the
  retry loop then reconnects from scratch. Closing on timeout also guarantees
  a late response to a timed-out request can never be read as the answer to
  the next one.
"""

import asyncio
import json
from typing import override

from dohome.exc import ClientIsNotResponding, PayloadTooLong
from dohome.transport.base import APITransport
from dohome.transport.constants import MESSAGE_MAX_SIZE, PORT_TCP

# On a local network the device answers within tens of milliseconds, so short
# timeouts with one reconnect attempt fail fast instead of blocking HA for
# the library defaults' worst case of 13.5 s (3 x (1 s + 3.5 s)).
CONNECT_TIMEOUT = 1.0
REQUEST_TIMEOUT = 1.5
SEND_ATTEMPTS = 2


class PersistentTCPStream(APITransport):
    """Doit API transport that keeps the TCP connection open between requests."""

    _host: str
    _connect_timeout: float
    _request_timeout: float
    _attempts: int
    _lock: asyncio.Lock
    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None

    def __init__(
        self,
        host: str,
        connect_timeout: float = CONNECT_TIMEOUT,
        request_timeout: float = REQUEST_TIMEOUT,
        attempts: int = SEND_ATTEMPTS,
    ):
        self._host = host
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout
        self._attempts = attempts
        self._lock = asyncio.Lock()

    @override
    async def send(self, payload: bytes) -> bytes:
        """Sends a request, reconnecting and retrying on any connection failure."""
        if len(payload) > MESSAGE_MAX_SIZE:
            raise PayloadTooLong(len(payload))
        async with self._lock:
            for _ in range(self._attempts):
                try:
                    return await self._try_send(payload)
                except (asyncio.TimeoutError, OSError, EOFError):
                    # Connection is in an unknown state — drop it so the next
                    # attempt (or the next request) starts from a clean one.
                    await self._async_close_connection()
            raise ClientIsNotResponding(self._host)

    async def close(self) -> None:
        """Closes the connection; safe to call multiple times."""
        async with self._lock:
            await self._async_close_connection()

    async def _try_send(self, payload: bytes) -> bytes:
        reader, writer = await self._async_ensure_connected()
        writer.write(payload)
        async with asyncio.timeout(self._request_timeout):
            await writer.drain()
            return await self._read_response(reader)

    async def _async_ensure_connected(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if (
            self._reader is not None
            and self._writer is not None
            and not self._writer.is_closing()
        ):
            return self._reader, self._writer
        await self._async_close_connection()
        async with asyncio.timeout(self._connect_timeout):
            self._reader, self._writer = await asyncio.open_connection(
                self._host, PORT_TCP
            )
        return self._reader, self._writer

    @staticmethod
    async def _read_response(reader: asyncio.StreamReader) -> bytes:
        buffer = b""
        while len(buffer) < MESSAGE_MAX_SIZE:
            chunk = await reader.read(MESSAGE_MAX_SIZE - len(buffer))
            if not chunk:
                # Peer closed the connection mid-response.
                raise EOFError
            buffer += chunk
            try:
                _: object = json.loads(buffer.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            return buffer
        return buffer

    async def _async_close_connection(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
