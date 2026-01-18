from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass
from typing import Any

import orjson
from redis.asyncio import Redis

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class RedisDialogStore:
    client: Redis
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
        redis_keys = self._select_key_list(request)
        token = self._build_token(redis_keys, request, reply)

        dialog = {
            "request": self._packet_to_dict(request, addr),
            "reply": self._reply_to_dict(reply),
        }

        pipe = self.client.pipeline()
        pipe.rpush(token, orjson.dumps(dialog))
        pipe.expire(token, self.expiry_seconds)
        await pipe.execute()

        return token

    def _select_key_list(self, request: Any) -> list[str]:
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
        suffix: list[str] = []
        for k in keys:
            if k == "code":
                suffix.append(str(getattr(request, "code", "")))
                continue
            if k == "id":
                suffix.append(str(getattr(request, "id", "")))
                continue

            if k in request:
                suffix.append(str(request[k][0]))
                continue

            if reply is not None and k in reply:
                suffix.append(str(reply[k][0]))
                continue

            suffix.append("")

        return f"{self.key_prefix}{'__'.join(suffix)}"

    def _packet_to_dict(self, packet: Any, addr: tuple[str, int]) -> dict[str, Any]:
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
                v = values[0]
                out[key] = v.hex() if isinstance(v, (bytes, bytearray)) else v
            else:
                out[key] = [v.hex() if isinstance(v, (bytes, bytearray)) else v for v in values]

        return out

    def _reply_to_dict(self, reply: Any | None) -> dict[str, Any]:
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
                v = values[0]
                out[key] = v.hex() if isinstance(v, (bytes, bytearray)) else v
            else:
                out[key] = [v.hex() if isinstance(v, (bytes, bytearray)) else v for v in values]

        return out
