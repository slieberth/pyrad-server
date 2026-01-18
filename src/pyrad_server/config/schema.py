from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from typing import Any, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# RADIUS codes
# ---------------------------------------------------------------------------

RADIUS_CODE_MAP: dict[int, str] = {
    1: "Access-Request",
    2: "Access-Accept",
    3: "Access-Reject",
    4: "Accounting-Request",
    5: "Accounting-Response",
    11: "Access-Challenge",
    40: "Disconnect-Request",
    41: "Disconnect-ACK",
    42: "Disconnect-NAK",
    43: "CoA-Request",
    44: "CoA-ACK",
    45: "CoA-NAK",
}

VALID_AUTH_CODES: set[int] = {2, 3, 11}
VALID_ACCT_CODES: set[int] = {5}

# ---------------------------------------------------------------------------
# Address pools
# ---------------------------------------------------------------------------


class AddressPool(BaseModel):
    """Single address pool definition with CIDR validation."""

    model_config = ConfigDict(extra="forbid")

    shuffle: bool = False
    ipv4: list[IPv4Network] = Field(default_factory=list)
    ipv6: list[IPv6Network] = Field(default_factory=list)
    ipv6_delegated: list[IPv6Network] = Field(default_factory=list)

    @field_validator("ipv4", mode="before")
    @classmethod
    def _parse_ipv4_networks(cls, value: Any) -> list[IPv4Network]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("ipv4 must be a list of CIDR strings.")
        networks: list[IPv4Network] = []
        for item in value:
            try:
                networks.append(IPv4Network(item))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid ipv4 network '{item}': {exc}") from exc
        return networks

    @field_validator("ipv6", "ipv6_delegated", mode="before")
    @classmethod
    def _parse_ipv6_networks(cls, value: Any) -> list[IPv6Network]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("ipv6 must be a list of CIDR strings.")
        networks: list[IPv6Network] = []
        for item in value:
            try:
                networks.append(IPv6Network(item))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid ipv6 network '{item}': {exc}") from exc
        return networks


AddressPoolMap: TypeAlias = dict[str, AddressPool]


class AddressPools(RootModel[AddressPoolMap]):
    """Named address pools."""

    @model_validator(mode="after")
    def _ensure_non_empty(self) -> AddressPools:
        if not self.root:
            raise ValueError("address_pools must contain at least one entry.")
        return self


# ---------------------------------------------------------------------------
# Reply definitions
# ---------------------------------------------------------------------------


class AuthReply(BaseModel):
    """Reply definition for authentication packets."""

    model_config = ConfigDict(extra="forbid")

    attributes: dict[str, Any] = Field(default_factory=dict)
    code: int

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: int) -> int:
        if value not in RADIUS_CODE_MAP:
            raise ValueError(f"Unknown RADIUS code: {value}")
        if value not in VALID_AUTH_CODES:
            allowed = ", ".join(str(c) for c in sorted(VALID_AUTH_CODES))
            raise ValueError(f"Auth code must be one of {{{allowed}}}, got {value}.")
        return value


class AcctReply(BaseModel):
    """Reply definition for accounting packets."""

    model_config = ConfigDict(extra="forbid")

    attributes: dict[str, Any] = Field(default_factory=dict)
    code: int

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: int) -> int:
        if value not in RADIUS_CODE_MAP:
            raise ValueError(f"Unknown RADIUS code: {value}")
        if value not in VALID_ACCT_CODES:
            allowed = ", ".join(str(c) for c in sorted(VALID_ACCT_CODES))
            raise ValueError(f"Acct code must be one of {{{allowed}}}, got {value}.")
        return value


AuthReplyMap: TypeAlias = dict[str, AuthReply]
AcctReplyMap: TypeAlias = dict[str, AcctReply]


class AuthReplies(RootModel[AuthReplyMap]):
    """Mapping: auth reply name -> definition."""


class AcctReplies(RootModel[AcctReplyMap]):
    """Mapping: acct reply name -> definition."""


class ReplyDefinitions(BaseModel):
    """Reply definitions for auth + acct."""

    model_config = ConfigDict(extra="forbid")

    auth: AuthReplies
    acct: AcctReplies


# ---------------------------------------------------------------------------
# Match rules
# ---------------------------------------------------------------------------

SelectorPredicate: TypeAlias = dict[str, str]
MatchRuleBody: TypeAlias = dict[str, list[SelectorPredicate]]


class PoolMatchRule(RootModel[MatchRuleBody]):
    """Single pool match rule."""


class PoolMatchRules(RootModel[list[PoolMatchRule]]):
    """Ordered pool match rules (first match wins)."""

    @model_validator(mode="after")
    def _ensure_non_empty(self) -> PoolMatchRules:
        if not self.root:
            raise ValueError("pool_match_rules must contain at least one rule.")
        return self


class ReplyMatchRule(RootModel[MatchRuleBody]):
    """Single reply match rule."""


class ReplyMatchRules(RootModel[list[ReplyMatchRule]]):
    """Ordered reply match rules (first match wins)."""


class ReplyMatchConfig(BaseModel):
    """Reply match rules for authentication and accounting."""

    model_config = ConfigDict(extra="forbid")

    auth: ReplyMatchRules
    acct: ReplyMatchRules

    @model_validator(mode="after")
    def _ensure_non_empty(self) -> ReplyMatchConfig:
        if not self.auth.root:
            raise ValueError("reply_match_rules.auth must contain at least one rule.")
        if not self.acct.root:
            raise ValueError("reply_match_rules.acct must contain at least one rule.")
        return self


# ---------------------------------------------------------------------------
# Redis storage
# ---------------------------------------------------------------------------


class RedisStorageConfig(BaseModel):
    """Redis storage configuration."""

    model_config = ConfigDict(extra="forbid")

    prefix: str = Field(description="Prefix used for all Redis keys produced by pyrad-server.")
    acct: list[str] = Field(description="Attributes stored for Accounting (acct) packets.")
    auth: list[str] = Field(description="Attributes stored for Authentication (auth) packets.")
    coa: list[str] = Field(description="Attributes stored for Change of Authorization (CoA) packets.")
    disc: list[str] = Field(description="Attributes stored for Disconnect (disc) packets.")

    @model_validator(mode="after")
    def _ensure_non_empty_lists(self) -> RedisStorageConfig:
        for name in ("acct", "auth", "coa", "disc"):
            if not getattr(self, name):
                raise ValueError(f"redis_storage.{name} must contain at least one attribute.")
        return self


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class PyradServerConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(extra="forbid")

    address_pools: AddressPools
    reply_definitions: ReplyDefinitions
    pool_match_rules: PoolMatchRules
    reply_match_rules: ReplyMatchConfig
    redis_storage: RedisStorageConfig


__all__ = [
    "RADIUS_CODE_MAP",
    "VALID_AUTH_CODES",
    "VALID_ACCT_CODES",
    "AddressPool",
    "AddressPools",
    "AuthReply",
    "AcctReply",
    "AuthReplies",
    "AcctReplies",
    "ReplyDefinitions",
    "PoolMatchRule",
    "PoolMatchRules",
    "ReplyMatchRule",
    "ReplyMatchRules",
    "ReplyMatchConfig",
    "RedisStorageConfig",
    "PyradServerConfig",
    "ValidationError",
]
