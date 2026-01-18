from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any, Protocol

import orjson


class RedisPipeline(Protocol):
    def rpush(self, key: str, value: bytes) -> Any: ...
    def expire(self, key: str, seconds: int) -> Any: ...
    async def execute(self) -> Any: ...


class RedisClient(Protocol):
    def pipeline(self) -> RedisPipeline: ...


@dataclass(slots=True)
class RedisDialogStore:
    """
    Stores request/reply dialogs in Redis.

    - uses RPUSH on a token key
    - sets expiry
    - serializes data with orjson
    """

    client: RedisClient
    key_prefix: str
    expiry_seconds: int

    store_auth_keys: list[str]
    store_acct_keys: list[str]
    store_coa_keys: list[str]
    store_disc_keys: list[str]

    async def store_dialog(
        self,
        request: Any,
        reply: Any | None,
        addr: tuple[str, int],
    ) -> str:
        suffix_keys = self._select_suffix_keys(request)
        token = self._build_token(suffix_keys, request, reply)

        dialog = {
            "request": self._packet_to_dict(request, addr),
            "reply": self._reply_to_dict(reply),
        }

        payload = orjson.dumps(dialog)

        pipe = self.client.pipeline()
        pipe.rpush(token, payload)
        pipe.expire(token, self.expiry_seconds)
        await pipe.execute()

        return token

    def _select_suffix_keys(self, request: Any) -> list[str]:
        code = getattr(request, "code", None)
        if code == 1:
            return self.store_auth_keys
        if code == 4:
            return self.store_acct_keys
        if code == 43:
            return self.store_coa_keys
        if code == 40:
            return self.store_disc_keys
        return []

    def _build_token(self, keys: list[str], request: Any, reply: Any | None) -> str:
        parts: list[str] = []
        for key in keys:
            if key == "code":
                parts.append(str(getattr(request, "code", "")))
                continue
            if key == "id":
                parts.append(str(getattr(request, "id", "")))
                continue

            value = self._first_attr_value(request, key)
            if value is None and reply is not None:
                value = self._first_attr_value(reply, key)

            parts.append("" if value is None else str(value))

        return f"{self.key_prefix}{'__'.join(parts)}"

    @staticmethod
    def _first_attr_value(packet: Any, attr: str) -> Any | None:
        try:
            if attr not in packet:
                return None
            values = packet[attr]
        except Exception:
            return None

        if not values:
            return None

        try:
            return values[0]
        except Exception:
            return None

    @staticmethod
    def _packet_to_dict(packet: Any, addr: tuple[str, int]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "_code": getattr(packet, "code", None),
            "_id": getattr(packet, "id", None),
            "_host": addr[0],
            "_port": addr[1],
        }

        for key in packet.keys():
            if key == "User-Password":
                out[key] = "encryptedValue"
                continue

            values = packet[key]
            if len(values) == 1:
                out[key] = _jsonable(values[0])
            else:
                out[key] = [_jsonable(v) for v in values]

        return out

    @staticmethod
    def _reply_to_dict(reply: Any | None) -> dict[str, Any]:
        now_ms = int(round(time.time() * 1000))
        ts_str = dt.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")

        if reply is None:
            return {"_code": None, "_ts": now_ms, "_tsStr": ts_str, "_id": None}

        out: dict[str, Any] = {
            "_code": getattr(reply, "code", None),
            "_ts": now_ms,
            "_tsStr": ts_str,
            "_id": getattr(reply, "id", None),
        }

        for key in reply.keys():
            values = reply[key]
            if len(values) == 1:
                out[key] = _jsonable(values[0])
            else:
                out[key] = [_jsonable(v) for v in values]

        return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value
