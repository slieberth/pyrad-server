from __future__ import annotations

from typing import Any


def raw_passthrough_decoder(data: bytes) -> Any:
    """
    Minimal decoder used for early wiring tests.
    Expects the data to already be a request-like object serialized externally.

    In production you will replace this with pyrad decoding:
      pyrad.packet.Packet(packet=data, secret=..., dict=...)
    """
    raise NotImplementedError("Provide a real decoder (e.g. pyrad-based).")


def raw_passthrough_encoder(reply_code: int, reply_attributes: dict[str, Any], request: Any) -> bytes:
    """
    Minimal encoder placeholder.
    In production, this will create a pyrad reply packet and call ReplyPacket().
    """
    raise NotImplementedError("Provide a real encoder (e.g. pyrad-based).")
