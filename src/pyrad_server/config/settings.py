from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    log_level: str

    server_ip: str
    auth_port: int
    acct_port: int

    rest_ip: str
    rest_port: int

    secret: str
    dictionary: str

    redis_host: str
    redis_port: int
    redis_expiry: int
    redis_key_prefix: str

    config_file: str | None
