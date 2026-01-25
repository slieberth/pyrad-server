from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pyrad import packet as pyrad_packet
from pyrad.dictionary import Dictionary


Decoder = Callable[[bytes], Any]
Encoder = Callable[[int, dict[str, Any], Any], bytes]


@dataclass(frozen=True, slots=True)
class PyradCodec:
    """
    pyrad encoder/decoder that plugs into the UDP wiring.

    - decoder: bytes -> pyrad Packet/AuthPacket
    - encoder: (code, attributes, request) -> bytes via request.CreateReply(...)
    """

    secret: bytes
    dictionary: Dictionary

    def decoder(self) -> Decoder:
        secret = self.secret
        dictionary = self.dictionary

        def _decode(data: bytes) -> Any:
            # Parse generic packet first to get code
            pkt = pyrad_packet.Packet(packet=data, secret=secret, dict=dictionary)

            # For Access-Request, use AuthPacket (supports password decrypt helpers etc.)
            if pkt.code == 1:
                auth = pyrad_packet.AuthPacket(packet=data, secret=secret, dict=dictionary)

                # # Optional: decrypt User-Password if present (store cleartext in packet)
                # values = auth.get("User-Password")
                # if values:
                #     encrypted = values[0]
                #     if isinstance(encrypted, str):
                #         encrypted = encrypted.encode("utf-8")
                #     clear = auth.PwDecrypt(encrypted)
                #     auth["User-Password"] = [clear]

                return auth

            return pkt

        return _decode

    def encoder(self) -> Encoder:
        dictionary = self.dictionary

        def _encode(reply_code: int, reply_attributes: dict[str, Any], request: Any) -> bytes:
            # Convert values so pyrad CreateReply can pack them correctly
            attr_dict = _convert_attributes(reply_attributes, dictionary)

            reply = request.CreateReply(**attr_dict)
            reply.code = reply_code
            return reply.ReplyPacket()

        return _encode


def _convert_attributes(attributes: dict[str, Any], dictionary: Dictionary) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in attributes.items():
        if isinstance(value, list):
            converted[key] = [_convert_value(key, v, dictionary) for v in value]
        else:
            converted[key] = _convert_value(key, value, dictionary)
    return converted


def _convert_value(key: str, value: Any, dictionary: Dictionary) -> Any:
    # Let bytes pass through (already packed)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)

    # If value is an IP/network object etc., let pyrad handle str
    if not isinstance(value, str):
        return value

    # Convert "0x..." to bytes ONLY for octets-like attributes
    if value.startswith("0x") and key in dictionary:
        attr_type = dictionary[key].type
        if attr_type in {"octets", "abinary"}:
            return bytes.fromhex(value[2:])

    return value
