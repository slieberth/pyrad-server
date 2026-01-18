from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Network
from typing import Iterable

from pyrad_server.config.schema import AddressPool, AddressPools


@dataclass(slots=True)
class PoolRuntime:
    """
    Runtime representation of an address pool.

    The config stores networks, the runtime stores allocatable items.
    For IPv4 we allocate host addresses, for IPv6 we allocate prefixes.
    """

    shuffle: bool
    ipv4: list[IPv4Address]
    ipv6: list[str]
    ipv6_delegated: list[str]

    @classmethod
    def from_config(cls, pool: AddressPool) -> "PoolRuntime":
        ipv4_hosts = _expand_ipv4_hosts(pool.ipv4)
        ipv6_prefixes = [str(n) for n in _expand_ipv6_prefixes(pool.ipv6, new_prefix=64)]
        ipv6_delegated = [str(n) for n in _expand_ipv6_prefixes(pool.ipv6_delegated, new_prefix=56)]

        if pool.shuffle:
            random.shuffle(ipv4_hosts)
            random.shuffle(ipv6_prefixes)
            random.shuffle(ipv6_delegated)

        return cls(
            shuffle=pool.shuffle,
            ipv4=ipv4_hosts,
            ipv6=ipv6_prefixes,
            ipv6_delegated=ipv6_delegated,
        )

    def allocate_ipv4(self) -> str | None:
        if not self.ipv4:
            return None
        return str(self.ipv4.pop(0))

    def allocate_ipv6(self) -> str | None:
        if not self.ipv6:
            return None
        return self.ipv6.pop(0)

    def allocate_ipv6_delegated(self) -> str | None:
        if not self.ipv6_delegated:
            return None
        return self.ipv6_delegated.pop(0)

    def restore_ipv4(self, address: str) -> None:
        self.ipv4.append(IPv4Address(address))

    def restore_ipv6(self, prefix: str) -> None:
        self.ipv6.append(prefix)

    def restore_ipv6_delegated(self, prefix: str) -> None:
        self.ipv6_delegated.append(prefix)


def build_pool_runtimes(address_pools: AddressPools) -> dict[str, PoolRuntime]:
    """
    Convert validated config pools into runtime pools.
    """
    return {name: PoolRuntime.from_config(pool) for name, pool in address_pools.root.items()}


def _expand_ipv4_hosts(networks: Iterable[IPv4Network]) -> list[IPv4Address]:
    """
    Expand IPv4 networks into host addresses.
    Example: 10.0.0.0/30 -> 10.0.0.1, 10.0.0.2
    """
    hosts: list[IPv4Address] = []
    for net in networks:
        hosts.extend(list(net.hosts()))
    return hosts


def _expand_ipv6_prefixes(networks: Iterable[IPv6Network], *, new_prefix: int) -> list[IPv6Network]:
    """
    Expand IPv6 networks into subnets of a given prefix.
    If the network is already more specific (prefixlen > new_prefix), keep it.
    """
    expanded: list[IPv6Network] = []
    for net in networks:
        if net.prefixlen > new_prefix:
            expanded.append(net)
        elif net.prefixlen == new_prefix:
            expanded.append(net)
        else:
            expanded.extend(list(net.subnets(new_prefix=new_prefix)))
    return expanded
