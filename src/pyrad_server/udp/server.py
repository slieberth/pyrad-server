from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from pyrad_server.radius.backend import RadiusBackend


logger = logging.getLogger(__name__)


class PacketDecoder(Protocol):
    def __call__(self, data: bytes) -> Any: ...


class PacketEncoder(Protocol):
    def __call__(self, reply_code: int, reply_attributes: dict[str, Any], request: Any) -> bytes: ...


@dataclass(slots=True)
class UdpRadiusServerConfig:
    host: str = "127.0.0.1"
    port: int = 1812
    max_concurrent: int = 200


class UdpRadiusProtocol(asyncio.DatagramProtocol):
    """
    Thin UDP protocol adapter.

    - decodes incoming bytes -> request packet
    - calls backend
    - encodes reply -> bytes
    - sends reply to sender

    Uses a semaphore to avoid unbounded concurrency.
    """

    def __init__(
        self,
        *,
        backend: RadiusBackend,
        decoder: PacketDecoder,
        encoder: PacketEncoder,
        semaphore: asyncio.Semaphore,
    ) -> None:
        self._backend = backend
        self._decoder = decoder
        self._encoder = encoder
        self._semaphore = semaphore
        self._transport: asyncio.DatagramTransport | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]
        logger.info("UDP transport ready")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport is None:
            return

        task = asyncio.create_task(self._handle_datagram(data, addr))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP error received: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("UDP transport closed (%s)", exc)

    async def aclose(self) -> None:
        # stop accepting new packets
        if self._transport is not None:
            self._transport.close()

        # wait for in-flight tasks
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        async with self._semaphore:
            try:
                request = self._decoder(data)
            except Exception as exc:
                logger.warning("Failed to decode packet from %s: %s", addr, exc)
                return

            try:
                result = await self._backend.handle_request(request, addr=addr)
            except Exception as exc:
                logger.exception("Backend failure for %s: %s", addr, exc)
                return

            if result.reply_code is None or result.reply_attributes is None:
                return

            try:
                payload = self._encoder(result.reply_code, result.reply_attributes, request)
            except Exception as exc:
                logger.warning("Failed to encode reply for %s: %s", addr, exc)
                return

            if self._transport is not None:
                self._transport.sendto(payload, addr)


async def start_udp_server(
    *,
    backend: RadiusBackend,
    decoder: PacketDecoder,
    encoder: PacketEncoder,
    config: UdpRadiusServerConfig,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[asyncio.DatagramTransport, UdpRadiusProtocol]:
    """
    Start UDP server and return (transport, protocol) so the caller can shut it down cleanly.
    """
    if loop is None:
        loop = asyncio.get_running_loop()

    semaphore = asyncio.Semaphore(config.max_concurrent)

    protocol = UdpRadiusProtocol(
        backend=backend,
        decoder=decoder,
        encoder=encoder,
        semaphore=semaphore,
    )

    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=(config.host, config.port),
    )
    return transport, protocol
