from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyrad_server.config.schema import PyradServerConfig
from pyrad_server.radius.matching import MatchEngine
from pyrad_server.radius.pools import PoolRuntime, build_pool_runtimes
from pyrad_server.radius.replies import ReplyBuilder
from pyrad_server.storage.redis_store import RedisDialogStore


@dataclass(slots=True)
class BackendResult:
    reply_code: int | None
    reply_attributes: dict[str, Any] | None
    redis_token: str | None


@dataclass(slots=True)
class RadiusBackend:
    """
    Core backend that orchestrates:
      - matching (pool/reply selection)
      - pool allocation
      - reply attribute building (directives)
      - dialog persistence (RedisDialogStore)

    The backend expects "packet-like" objects that behave like pyrad packets:
      - packet.code (int)
      - packet.id (int)
      - packet.keys()
      - attr in packet
      - packet[attr] -> list of values
    """

    config: PyradServerConfig
    redis_store: RedisDialogStore | None = None

    pool_runtimes: dict[str, PoolRuntime] = field(init=False)
    match_engine: MatchEngine = field(init=False)

    def __post_init__(self) -> None:
        self.pool_runtimes = build_pool_runtimes(self.config.address_pools)

        # Unwrap Pydantic RootModels into plain python dicts for the match engine.
        pool_rules = [rule.root for rule in self.config.pool_match_rules.root]
        reply_rules_auth = [rule.root for rule in self.config.reply_match_rules.auth.root]
        reply_rules_acct = [rule.root for rule in self.config.reply_match_rules.acct.root]

        self.match_engine = MatchEngine(
            pool_match_rules=pool_rules,
            reply_match_rules_auth=reply_rules_auth,
            reply_match_rules_acct=reply_rules_acct,
        )

    async def handle_request(
        self,
        request: Any,
        *,
        addr: tuple[str, int] = ("127.0.0.1", 12345),
    ) -> BackendResult:
        reply_code: int | None
        reply_attributes: dict[str, Any] | None

        if request.code == 1:
            reply_code, reply_attributes = await self._handle_auth(request)
        elif request.code == 4:
            reply_code, reply_attributes = await self._handle_acct(request)
        else:
            reply_code, reply_attributes = None, None

        redis_token: str | None = None
        if self.redis_store is not None:
            reply_packet = None
            if reply_code is not None:
                reply_packet = PacketView(code=reply_code, packet_id=request.id, attributes=reply_attributes or {})
            redis_token = await self.redis_store.store_dialog(request, reply_packet, addr)

        return BackendResult(
            reply_code=reply_code,
            reply_attributes=reply_attributes,
            redis_token=redis_token,
        )

    async def _handle_auth(self, request: Any) -> tuple[int | None, dict[str, Any] | None]:
        pool_name = self.match_engine.select_pool(request, default="default")
        pool = self.pool_runtimes.get(pool_name)

        reply_name = self.match_engine.select_reply("auth", request, default="default")
        reply_def = self.config.reply_definitions.auth.root.get(reply_name)
        if reply_def is None:
            return None, None

        builder = ReplyBuilder(pool=pool)
        attrs, err = builder.build_attributes(request, reply_def.attributes)

        if err is not None:
            # Access-Reject
            return 3, attrs

        return reply_def.code, attrs

    async def _handle_acct(self, request: Any) -> tuple[int | None, dict[str, Any] | None]:
        reply_name = self.match_engine.select_reply("acct", request, default="default")
        reply_def = self.config.reply_definitions.acct.root.get(reply_name)
        if reply_def is None:
            return None, None

        return reply_def.code, dict(reply_def.attributes)


class PacketView(dict):
    """
    Small helper to make reply attributes look like a pyrad packet for RedisDialogStore.
    """

    def __init__(self, *, code: int, packet_id: int, attributes: dict[str, Any]) -> None:
        super().__init__()
        self.code = code
        self.id = packet_id
        for key, value in attributes.items():
            self[key] = value if isinstance(value, list) else [value]

    def keys(self):
        return super().keys()
