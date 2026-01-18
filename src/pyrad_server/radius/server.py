from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

LOG = logging.getLogger(__name__)


class DatagramProcessor(Protocol):
    async def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> bytes | None: ...


@dataclass(slots=True)
class RadiusDatagramProtocol(asyncio.DatagramProtocol):
    processor: DatagramProcessor
    transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        LOG.info("RADIUS UDP transport ready")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self._handle(data, addr))

    async def _handle(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            reply = await self.processor.handle_datagram(data, addr)
            if reply and self.transport:
                self.transport.sendto(reply, addr)
        except Exception:
            LOG.exception("Unhandled exception processing datagram from %s", addr)


async def run_radius_udp_server(
    processor: DatagramProcessor,
    host: str,
    port: int,
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: RadiusDatagramProtocol(processor=processor),
        local_addr=(host, port),
        reuse_port=True,
    )
    return transport
