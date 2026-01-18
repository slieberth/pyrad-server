from __future__ import annotations

import asyncio

import orjson

from pyrad_server.storage.redis_store import RedisDialogStore


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.ops: list[tuple[str, tuple]] = []

    def rpush(self, key: str, value: bytes) -> None:
        self.ops.append(("rpush", (key, value)))

    def expire(self, key: str, seconds: int) -> None:
        self.ops.append(("expire", (key, seconds)))

    async def execute(self) -> None:
        for op, args in self.ops:
            if op == "rpush":
                key, value = args
                self.redis.data.setdefault(key, []).append(value)
            elif op == "expire":
                key, seconds = args
                self.redis.expiry[key] = seconds


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, list[bytes]] = {}
        self.expiry: dict[str, int] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


class FakePacket(dict):
    def __init__(self, *, code: int, packet_id: int, **attrs) -> None:
        super().__init__()
        self.code = code
        self.id = packet_id
        for k, v in attrs.items():
            # mimic pyrad behavior: values are lists
            self[k] = v if isinstance(v, list) else [v]

    def keys(self):
        return super().keys()


def test_store_dialog_auth_builds_token_and_payload() -> None:
    async def run() -> None:
        redis = FakeRedis()
        store = RedisDialogStore(
            client=redis,
            key_prefix="tE4.radiusServer.",
            expiry_seconds=600,
            store_auth_keys=["User-Name"],
            store_acct_keys=["User-Name"],
            store_coa_keys=["User-Name"],
            store_disc_keys=["User-Name"],
        )

        req = FakePacket(code=1, packet_id=7, **{"User-Name": "alice", "User-Password": b"\x01\x02"})
        rep = FakePacket(code=2, packet_id=7, **{"Reply-Message": "OK"})

        token = await store.store_dialog(req, rep, ("127.0.0.1", 12345))

        assert token == "tE4.radiusServer.alice"
        assert token in redis.data
        assert redis.expiry[token] == 600

        payload = redis.data[token][0]
        dialog = orjson.loads(payload)

        assert dialog["request"]["_code"] == 1
        assert dialog["request"]["_id"] == 7
        assert dialog["request"]["User-Name"] == "alice"
        assert dialog["request"]["User-Password"] == "encryptedValue"

        assert dialog["reply"]["_code"] == 2
        assert dialog["reply"]["Reply-Message"] == "OK"
        assert "_ts" in dialog["reply"]
        assert "_tsStr" in dialog["reply"]

    asyncio.run(run())


def test_store_dialog_reply_none_still_stores() -> None:
    async def run() -> None:
        redis = FakeRedis()
        store = RedisDialogStore(
            client=redis,
            key_prefix="p.",
            expiry_seconds=10,
            store_auth_keys=["User-Name"],
            store_acct_keys=["User-Name"],
            store_coa_keys=["User-Name"],
            store_disc_keys=["User-Name"],
        )

        req = FakePacket(code=4, packet_id=1, **{"User-Name": "alice"})
        token = await store.store_dialog(req, None, ("10.0.0.1", 9999))

        assert token == "p.alice"
        dialog = orjson.loads(redis.data[token][0])
        assert dialog["reply"]["_code"] is None
        assert dialog["reply"]["_id"] is None

    asyncio.run(run())


def test_token_can_use_code_and_id_special_fields() -> None:
    async def run() -> None:
        redis = FakeRedis()
        store = RedisDialogStore(
            client=redis,
            key_prefix="x.",
            expiry_seconds=1,
            store_auth_keys=["code", "id"],
            store_acct_keys=["code", "id"],
            store_coa_keys=["code", "id"],
            store_disc_keys=["code", "id"],
        )

        req = FakePacket(code=1, packet_id=99, **{"User-Name": "alice"})
        token = await store.store_dialog(req, None, ("127.0.0.1", 1))

        assert token == "x.1__99"

    asyncio.run(run())
