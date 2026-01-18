from __future__ import annotations

import asyncio
from ipaddress import IPv4Network

import orjson

from pyrad_server.config.schema import (
    AcctReply,
    AcctReplies,
    AddressPool,
    AddressPools,
    AuthReply,
    AuthReplies,
    PoolMatchRule,
    PoolMatchRules,
    PyradServerConfig,
    RedisStorageConfig,
    ReplyDefinitions,
    ReplyMatchConfig,
    ReplyMatchRule,
    ReplyMatchRules,
)
from pyrad_server.radius.backend import RadiusBackend
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


class FakeRequest(dict):
    def __init__(self, *, code: int, packet_id: int, **attrs) -> None:
        super().__init__()
        self.code = code
        self.id = packet_id
        for k, v in attrs.items():
            self[k] = v if isinstance(v, list) else [v]

    def keys(self):
        return super().keys()


def _make_config() -> PyradServerConfig:
    # This matches your "mini config" semantics, but built via Pydantic models.
    address_pools = AddressPools(
        {
            "pool1": AddressPool(shuffle=False, ipv4=[IPv4Network("10.0.0.0/30")], ipv6=[], ipv6_delegated=[]),
        }
    )

    reply_definitions = ReplyDefinitions(
        auth=AuthReplies({"ok": AuthReply(code=2, attributes={"Reply-Message": "OK", "Framed-IP-Address": "-> fromPool"})}),
        acct=AcctReplies({"acct_ok": AcctReply(code=5, attributes={})}),
    )

    pool_match_rules = PoolMatchRules([PoolMatchRule({"pool1": [{"User-Name": "alice"}]})])

    reply_match_rules = ReplyMatchConfig(
        auth=ReplyMatchRules([ReplyMatchRule({"ok": [{"User-Name": "alice"}]})]),
        acct=ReplyMatchRules([ReplyMatchRule({"acct_ok": [{"User-Name": "alice"}]})]),
    )

    redis_storage = RedisStorageConfig(
        prefix="tE4.radiusServer.",
        acct=["User-Name"],
        auth=["User-Name"],
        coa=["User-Name"],
        disc=["User-Name"],
    )

    return PyradServerConfig(
        address_pools=address_pools,
        reply_definitions=reply_definitions,
        pool_match_rules=pool_match_rules,
        reply_match_rules=reply_match_rules,
        redis_storage=redis_storage,
    )


def test_backend_auth_flow_allocates_ip_and_stores_dialog() -> None:
    async def run() -> None:
        config = _make_config()

        fake_redis = FakeRedis()
        store = RedisDialogStore(
            client=fake_redis,
            key_prefix=config.redis_storage.prefix,
            expiry_seconds=600,
            store_auth_keys=config.redis_storage.auth,
            store_acct_keys=config.redis_storage.acct,
            store_coa_keys=config.redis_storage.coa,
            store_disc_keys=config.redis_storage.disc,
        )

        backend = RadiusBackend(config=config, redis_store=store)

        req = FakeRequest(code=1, packet_id=7, **{"User-Name": "alice"})
        result = await backend.handle_request(req, addr=("127.0.0.1", 1812))

        assert result.reply_code == 2
        assert result.reply_attributes is not None
        assert result.reply_attributes["Reply-Message"] == "OK"
        # /30 expands to .1, .2; first allocation should be .1
        assert result.reply_attributes["Framed-IP-Address"] == "10.0.0.1"

        assert result.redis_token == "tE4.radiusServer.alice"
        assert result.redis_token in fake_redis.data

        payload = fake_redis.data[result.redis_token][0]
        dialog = orjson.loads(payload)

        assert dialog["request"]["User-Name"] == "alice"
        assert dialog["reply"]["_code"] == 2
        assert dialog["reply"]["Reply-Message"] == "OK"
        assert dialog["reply"]["Framed-IP-Address"] == "10.0.0.1"

    asyncio.run(run())


def test_backend_acct_flow_uses_acct_reply_and_stores_dialog() -> None:
    async def run() -> None:
        config = _make_config()

        fake_redis = FakeRedis()
        store = RedisDialogStore(
            client=fake_redis,
            key_prefix=config.redis_storage.prefix,
            expiry_seconds=600,
            store_auth_keys=config.redis_storage.auth,
            store_acct_keys=config.redis_storage.acct,
            store_coa_keys=config.redis_storage.coa,
            store_disc_keys=config.redis_storage.disc,
        )

        backend = RadiusBackend(config=config, redis_store=store)

        req = FakeRequest(code=4, packet_id=9, **{"User-Name": "alice"})
        result = await backend.handle_request(req, addr=("127.0.0.1", 1813))

        assert result.reply_code == 5
        assert result.reply_attributes == {}

        assert result.redis_token == "tE4.radiusServer.alice"
        dialog = orjson.loads(fake_redis.data[result.redis_token][0])
        assert dialog["reply"]["_code"] == 5

    asyncio.run(run())


