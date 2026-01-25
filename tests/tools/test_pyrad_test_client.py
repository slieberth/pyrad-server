from __future__ import annotations

import os
import time
from dataclasses import dataclass

import pytest
from _pytest.fixtures import FixtureRequest

from pyrad_server.tools.pyrad_test_client import (
    AcctCommand,
    AuthCommand,
    RadiusNoReplyError,
    RadiusTestClient,
)

ACCESS_ACCEPT = 2
ACCOUNTING_RESPONSE = 5

DEFAULT_SERVER = "127.0.0.1"
DEFAULT_AUTH_PORT = 1812
DEFAULT_ACCT_PORT = 1813
DEFAULT_SECRET = "testsecret"
DEFAULT_DICTIONARY = "conf/dictionary"

DEFAULT_USER = "alice"
DEFAULT_NAS_IP = "192.168.1.10"
DEFAULT_SERVICE_TYPE = "Login-User"


@dataclass(frozen=True, slots=True)
class RadiusEnvConfig:
    server: str
    auth_port: int
    acct_port: int
    secret: str
    dictionary_path: str


@pytest.fixture(scope="session")
def radius_env() -> RadiusEnvConfig:
    """Read RADIUS test configuration from environment variables (with defaults)."""
    return RadiusEnvConfig(
        server=os.getenv("PYRAD_TEST_SERVER_HOST", DEFAULT_SERVER),
        auth_port=int(os.getenv("PYRAD_TEST_AUTH_PORT", str(DEFAULT_AUTH_PORT))),
        acct_port=int(os.getenv("PYRAD_TEST_ACCT_PORT", str(DEFAULT_ACCT_PORT))),
        secret=os.getenv("PYRAD_TEST_SECRET", DEFAULT_SECRET),
        dictionary_path=os.getenv("PYRAD_TEST_DICTIONARY", DEFAULT_DICTIONARY),
    )


@pytest.fixture
def calling_station_id(request: FixtureRequest) -> str:
    """Use pytest's nodeid so packets can be correlated in server logs/tcpdump."""
    return request.node.nodeid


@pytest.fixture
def session_id() -> str:
    """Unique session id per test run invocation."""
    return f"pytest:{int(time.time())}"


@pytest.fixture
def radius_client(radius_env: RadiusEnvConfig) -> RadiusTestClient:
    """Create a RADIUS test client with common settings."""
    return RadiusTestClient(
        server=radius_env.server,
        auth_port=radius_env.auth_port,
        acct_port=radius_env.acct_port,
        secret=radius_env.secret,
        dictionary_path=radius_env.dictionary_path,
        timeout=1.5,
        retries=1,
    )


def send_auth_or_skip(client: RadiusTestClient, cmd: AuthCommand) -> dict:
    try:
        return client.send_auth(cmd)
    except RadiusNoReplyError as exc:
        pytest.skip(f"RADIUS server not reachable / not running: {exc}")


def send_acct_or_skip(
    client: RadiusTestClient,
    cmd: AcctCommand,
    *,
    include_last_addresses: bool,
) -> dict:
    try:
        return client.send_acct(cmd, include_last_addresses=include_last_addresses)
    except RadiusNoReplyError as exc:
        pytest.skip(f"RADIUS server not reachable / not running: {exc}")


@pytest.mark.integration
def test_auth_request_receives_accept_and_reply_message(
    radius_client: RadiusTestClient,
    session_id: str,
    calling_station_id: str,
) -> None:
    cmd = AuthCommand(
        user_name=DEFAULT_USER,
        nas_ip_address=DEFAULT_NAS_IP,
        nas_port=0,
        nas_identifier="pytest client 0001",
        service_type=DEFAULT_SERVICE_TYPE,
        acct_session_id=session_id,
        user_password="CLEARTEXT",
        extra_avps={
            "Calling-Station-Id": calling_station_id,
        },
    )

    result = send_auth_or_skip(radius_client, cmd)

    reply = result["reply"]
    assert reply["code"] == ACCESS_ACCEPT
    assert reply.get("Reply-Message") == "OK"


@pytest.mark.integration
def test_acct_request_accounting_on(
    radius_env: RadiusEnvConfig,
    session_id: str,
    calling_station_id: str,
) -> None:
    # Separate client with debug enabled for this test
    client = RadiusTestClient(
        server=radius_env.server,
        auth_port=radius_env.auth_port,
        acct_port=radius_env.acct_port,
        secret=radius_env.secret,
        dictionary_path=radius_env.dictionary_path,
        timeout=1.5,
        retries=1,
        debug=True,
    )

    acct_result = send_acct_or_skip(
        client,
        AcctCommand(
            user_name=DEFAULT_USER,
            acct_status_type="Accounting-On",
            nas_ip_address=DEFAULT_NAS_IP,
            nas_port=0,
            nas_identifier="pytest client 0002",
            acct_session_id=session_id,
        ),
        include_last_addresses=True,
    )

    reply = acct_result["reply"]
    assert reply["code"] == ACCOUNTING_RESPONSE


@pytest.mark.integration
def test_acct_request_receives_accounting_response(
    radius_env: RadiusEnvConfig,
    session_id: str,
    calling_station_id: str,
) -> None:
    # Separate client with debug enabled for this test
    client = RadiusTestClient(
        server=radius_env.server,
        auth_port=radius_env.auth_port,
        acct_port=radius_env.acct_port,
        secret=radius_env.secret,
        dictionary_path=radius_env.dictionary_path,
        timeout=1.5,
        retries=1,
        debug=True,
    )

    # Auth first (optional, but useful to "warm up" and store addresses)
    send_auth_or_skip(
        client,
        AuthCommand(
            user_name=DEFAULT_USER,
            nas_ip_address=DEFAULT_NAS_IP,
            nas_port=0,
            nas_identifier="pytest client 0002",
            service_type=DEFAULT_SERVICE_TYPE,
            acct_session_id=session_id,
            extra_avps={"Calling-Station-Id": calling_station_id},
        ),
    )

    acct_result = send_acct_or_skip(
        client,
        AcctCommand(
            user_name=DEFAULT_USER,
            acct_status_type="Interim-Update",
            nas_ip_address=DEFAULT_NAS_IP,
            nas_port=0,
            nas_identifier="pytest client 0002",
            acct_session_id=session_id,
            extra_avps={
                "Calling-Station-Id": calling_station_id,
            },
        ),
        include_last_addresses=True,
    )

    reply = acct_result["reply"]
    assert reply["code"] == ACCOUNTING_RESPONSE
