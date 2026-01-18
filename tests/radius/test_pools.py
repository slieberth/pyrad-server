from __future__ import annotations

from ipaddress import IPv4Network

from pyrad_server.config.schema import AddressPool, AddressPools
from pyrad_server.radius.pools import PoolRuntime, build_pool_runtimes


def test_pool_runtime_ipv4_expand_and_allocate_restore() -> None:
    pool_cfg = AddressPool(shuffle=False, ipv4=[IPv4Network("10.0.0.0/30")], ipv6=[], ipv6_delegated=[])
    runtime = PoolRuntime.from_config(pool_cfg)

    # 10.0.0.0/30 => hosts are .1 and .2
    a1 = runtime.allocate_ipv4()
    a2 = runtime.allocate_ipv4()
    a3 = runtime.allocate_ipv4()

    assert a1 == "10.0.0.1"
    assert a2 == "10.0.0.2"
    assert a3 is None

    runtime.restore_ipv4("10.0.0.99")
    assert runtime.allocate_ipv4() == "10.0.0.99"


def test_build_pool_runtimes_from_address_pools_root() -> None:
    pools = AddressPools(
        {
            "pool1": AddressPool(shuffle=False, ipv4=[IPv4Network("10.0.0.0/30")], ipv6=[], ipv6_delegated=[]),
        }
    )
    runtimes = build_pool_runtimes(pools)
    assert "pool1" in runtimes
    assert runtimes["pool1"].allocate_ipv4() == "10.0.0.1"
