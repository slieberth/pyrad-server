from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pyrad_server.radius.backend import BackendResult
from pyrad_server.udp.server import UdpRadiusProtocol


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeBackend:
    async def handle_request(self, request: Any, *, addr: tuple[str, int]) -> BackendResult:
        return BackendResult(reply_code=2, reply_attributes={"Reply-Message": "OK"}, redis_token=None)


def test_udp_protocol_sends_reply() -> None:
    async def run() -> None:
        backend = FakeBackend()

        def decoder(data: bytes) -> Any:
            # fake request object with code/id like pyrad
            class Req(dict):
                code = 1
                id = 7

                def keys(self):
                    return super().keys()

            return Req({"User-Name": ["alice"]})

        def encoder(reply_code: int, reply_attributes: dict[str, Any], request: Any) -> bytes:
            assert reply_code == 2
            assert reply_attributes["Reply-Message"] == "OK"
            return b"REPLY"

        protocol = UdpRadiusProtocol(
            backend=backend,  # type: ignore[arg-type]
            decoder=decoder,
            encoder=encoder,
            semaphore=asyncio.Semaphore(10),
        )

        transport = FakeTransport()
        protocol.connection_made(transport)  # type: ignore[arg-type]

        protocol.datagram_received(b"REQ", ("127.0.0.1", 9999))
        await asyncio.sleep(0)  # allow task to run

        assert transport.sent == [(b"REPLY", ("127.0.0.1", 9999))]

        await protocol.aclose()
        assert transport.closed is True

    asyncio.run(run())
