from __future__ import annotations

from pathlib import Path

import pytest

from pyrad_server.config.loader import ConfigLoadError, load_config, validate_config
from pyrad_server.config.schema import PyradServerConfig


def minimal_valid_config() -> dict:
    return {
        "address_pools": {
            "pool1": {
                "shuffle": False,
                "ipv4": ["10.0.0.0/24"],
                "ipv6": ["2001:db8::/64"],
                "ipv6_delegated": ["2001:db8:100::/56"],
            }
        },
        "reply_definitions": {
            "auth": {
                "ok": {"code": 2, "attributes": {"Reply-Message": "OK"}},
                "reject": {"code": 3, "attributes": {}},
            },
            "acct": {
                "acct_ok": {"code": 5, "attributes": {"Reply-Message": "ACCT_OK"}},
            },
        },
        "pool_match_rules": [
            {"pool1": [{"User-Name": "alice"}]},
        ],
        "reply_match_rules": {
            "auth": [
                {"ok": [{"User-Name": "alice"}]},
            ],
            "acct": [
                {"acct_ok": [{"User-Name": "alice"}]},
            ],
        },
        "redis_storage": {
            "prefix": "tE4.radiusServer.",
            "acct": ["User-Name"],
            "auth": ["User-Name"],
            "coa": ["User-Name"],
            "disc": ["User-Name"],
        },
    }


def test_validate_config_ok() -> None:
    config = validate_config(minimal_valid_config())
    assert isinstance(config, PyradServerConfig)
    assert "pool1" in config.address_pools.root
    assert str(config.address_pools.root["pool1"].ipv4[0]) == "10.0.0.0/24"
    assert config.redis_storage.prefix == "tE4.radiusServer."


def test_rejects_unknown_top_level_keys() -> None:
    data = minimal_valid_config()
    data["address-pool-collection"] = {}  # old key should be rejected

    with pytest.raises(ConfigLoadError) as exc:
        validate_config(data, source="inline")

    assert "extra" in str(exc.value).lower()


def test_rejects_empty_address_pools() -> None:
    data = minimal_valid_config()
    data["address_pools"] = {}

    with pytest.raises(ConfigLoadError) as exc:
        validate_config(data, source="inline")

    assert "address_pools must contain at least one entry" in str(exc.value)


def test_invalid_ipv4_network() -> None:
    data = minimal_valid_config()
    data["address_pools"]["pool1"]["ipv4"] = ["not-a-cidr"]

    with pytest.raises(ConfigLoadError) as exc:
        validate_config(data, source="inline")

    assert "Invalid ipv4 network" in str(exc.value)


def test_forbids_extra_keys_in_nested_models() -> None:
    data = minimal_valid_config()
    data["reply_definitions"]["auth"]["ok"]["unexpected"] = 123

    with pytest.raises(ConfigLoadError) as exc:
        validate_config(data, source="inline")

    assert "extra" in str(exc.value).lower()


def test_load_config_yaml(tmp_path: Path) -> None:
    yaml_text = """
address_pools:
  pool1:
    shuffle: false
    ipv4:
      - 10.0.0.0/24

reply_definitions:
  auth:
    ok:
      code: 2
      attributes:
        Reply-Message: "OK"
  acct:
    acct_ok:
      code: 5
      attributes: {}

pool_match_rules:
  - pool1:
      - User-Name: alice

reply_match_rules:
  auth:
    - ok:
        - User-Name: alice
  acct:
    - acct_ok:
        - User-Name: alice

redis_storage:
  prefix: tE4.radiusServer.
  acct: [User-Name]
  auth: [User-Name]
  coa: [User-Name]
  disc: [User-Name]
"""
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml_text, encoding="utf-8")

    config = load_config(config_path)
    assert config.address_pools.root["pool1"].ipv4[0].with_prefixlen == "10.0.0.0/24"


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError) as exc:
        load_config(tmp_path / "missing.yml")

    assert "Config file not found" in str(exc.value)
