from __future__ import annotations

import asyncio
from pathlib import Path

from pyrad import packet as pyrad_packet
from pyrad.dictionary import Dictionary

from pyrad_server.udp.pyrad_codecs import PyradCodec


def _write_min_dictionary(tmp_path: Path) -> Path:
    # Minimal dictionary lines needed for this test.
    # NOTE: This is standard FreeRADIUS-style syntax, supported by pyrad.
    content = "\n".join(
        [
            'ATTRIBUTE User-Name 1 string',
            'ATTRIBUTE Reply-Message 18 string',
            'ATTRIBUTE Framed-IP-Address 8 ipaddr',
        ]
    )
    p = tmp_path / "dictionary"
    p.write_text(content, encoding="utf-8")
    return p


def test_decode_then_encode_reply(tmp_path: Path) -> None:
    async def run() -> None:
        dict_path = _write_min_dictionary(tmp_path)
        dictionary = Dictionary(str(dict_path))
        secret = b"testsecret"

        codec = PyradCodec(secret=secret, dictionary=dictionary)
        decode = codec.decoder()
        encode = codec.encoder()

        # Build an Access-Request
        req = pyrad_packet.AuthPacket(secret=secret, dict=dictionary)
        req.code = 1
        req.id = 7
        req["User-Name"] = "alice"

        raw_req = req.RequestPacket()
        decoded = decode(raw_req)

        assert decoded.code == 1
        assert decoded.id == 7
        assert decoded["User-Name"][0] == "alice"

        # Encode an Access-Accept reply
        raw_reply = encode(2, {"Reply-Message": "OK"}, decoded)

        # Parse reply with generic Packet
        parsed_reply = pyrad_packet.Packet(packet=raw_reply, secret=secret, dict=dictionary)
        assert parsed_reply.code == 2
        assert parsed_reply.id == 7
        assert parsed_reply["Reply-Message"][0] == "OK"

    asyncio.run(run())
