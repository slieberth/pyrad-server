from __future__ import annotations

import re

from pyrad_server.radius.replies import ReplyBuilder
from pyrad_server.radius.pools import PoolRuntime


class FakeRequest(dict):
    """Mimics pyrad packet mapping: values are lists, e.g. {'User-Name': ['alice']}."""


def make_pool(*, ipv4: list[str]) -> PoolRuntime:
    return PoolRuntime(
        shuffle=False,
        ipv4=[__import__("ipaddress").IPv4Address(x) for x in ipv4],
        ipv6=[],
        ipv6_delegated=[],
    )


def test_from_uuid() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"User-Name": ["alice"]})

    attrs, err = builder.build_attributes(req, {"Class": "-> fromUuid"})
    assert err is None
    assert isinstance(attrs["Class"], str)
    assert re.fullmatch(r"[0-9a-fA-F-]{36}", attrs["Class"]) is not None


def test_from_request_plain() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"User-Name": ["alice"]})

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name"})
    assert err is None
    assert attrs["Reply-Message"] == "alice"


def test_from_request_split_index() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"User-Name": ["a#b#c#d#e#f"]})

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name.split('#')[5]"})
    assert err is None
    assert attrs["Reply-Message"] == "f"


def test_from_request_lower_upper() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"User-Name": ["Alice"]})

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name.lower()"})
    assert err is None
    assert attrs["Reply-Message"] == "alice"

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name.upper()"})
    assert err is None
    assert attrs["Reply-Message"] == "ALICE"


def test_from_request_missing_attribute_returns_error_message() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"NAS-IP-Address": ["1.2.3.4"]})

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name"})
    assert err is not None
    assert attrs["Reply-Message"].startswith("missing avp User-Name")


def test_from_request_unsupported_transform_fails_cleanly() -> None:
    builder = ReplyBuilder(pool=None)
    req = FakeRequest({"User-Name": ["alice"]})

    attrs, err = builder.build_attributes(req, {"Reply-Message": "-> fromRequest.User-Name.strip()"})
    assert err is not None
    assert "unsupported transform" in err
    assert "Reply-Message" in attrs


def test_from_pool_ipv4_allocate_ok() -> None:
    pool = make_pool(ipv4=["10.0.0.1"])
    builder = ReplyBuilder(pool=pool)
    req = FakeRequest({"User-Name": ["alice"]})

    attrs, err = builder.build_attributes(req, {"Framed-IP-Address": "-> fromPool"})
    assert err is None
    assert attrs["Framed-IP-Address"] == "10.0.0.1"


def test_from_pool_exhausted_returns_reject_message() -> None:
    pool = make_pool(ipv4=[])
    builder = ReplyBuilder(pool=pool)
    req = FakeRequest({"User-Name": ["alice"]})

    attrs, err = builder.build_attributes(req, {"Framed-IP-Address": "-> fromPool"})
    assert err is not None
    assert attrs["Reply-Message"] == "IP Address in pool is exhausted"
