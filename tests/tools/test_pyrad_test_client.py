from __future__ import annotations

import os
import time

import pytest

from pyrad_server.tools.pyrad_test_client import (
    AcctCommand,
    AuthCommand,
    RadiusNoReplyError,
    RadiusTestClient,
)


@pytest.mark.integration
def test_auth_request_receives_accept_and_reply_message() -> None:
    server = os.getenv("PYRAD_TEST_SERVER_HOST", "127.0.0.1")
    auth_port = int(os.getenv("PYRAD_TEST_AUTH_PORT", "1812"))
    acct_port = int(os.getenv("PYRAD_TEST_ACCT_PORT", "1813"))
    secret = os.getenv("PYRAD_TEST_SECRET", "testsecret")
    dictionary_path = os.getenv("PYRAD_TEST_DICTIONARY", "conf/dictionary")

    client = RadiusTestClient(
        server=server,
        auth_port=auth_port,
        acct_port=acct_port,
        secret=secret,
        dictionary_path=dictionary_path,
        timeout=1.5,
        retries=1,
    )

    session_id = f"pytest:{int(time.time())}"

    cmd = AuthCommand(
        user_name="alice",
        nas_ip_address="192.168.1.10",
        nas_port=0,
        nas_identifier="DUT-BNG",
        service_type="Login-User",
        acct_session_id=session_id,
    )

    try:
        result = client.send_auth(cmd)
    except RadiusNoReplyError as exc:
        pytest.skip(f"RADIUS server not reachable / not running: {exc}")

    reply = result["reply"]
    assert reply["code"] == 2  # Access-Accept
    assert reply.get("Reply-Message") == "OK"


@pytest.mark.integration
def test_acct_request_receives_accounting_response() -> None:
    server = os.getenv("PYRAD_TEST_SERVER_HOST", "127.0.0.1")
    auth_port = int(os.getenv("PYRAD_TEST_AUTH_PORT", "1812"))
    acct_port = int(os.getenv("PYRAD_TEST_ACCT_PORT", "1813"))
    secret = os.getenv("PYRAD_TEST_SECRET", "testsecret")
    dictionary_path = os.getenv("PYRAD_TEST_DICTIONARY", "conf/dictionary")

    client = RadiusTestClient(
        server=server,
        auth_port=auth_port,
        acct_port=acct_port,
        secret=secret,
        dictionary_path=dictionary_path,
        timeout=1.5,
        retries=1,
    )

    session_id = f"pytest:{int(time.time())}"

    # auth first (optional, but useful to "warm up" and store addresses)
    try:
        client.send_auth(
            AuthCommand(
                user_name="alice",
                nas_ip_address="192.168.1.10",
                nas_port=0,
                nas_identifier="DUT-BNG",
                service_type="Login-User",
                acct_session_id=session_id,
            )
        )
    except RadiusNoReplyError as exc:
        pytest.skip(f"RADIUS server not reachable / not running: {exc}")

    try:
        acct_result = client.send_acct(
            AcctCommand(
                user_name="alice",
                acct_status_type="Interim-Update",
                nas_ip_address="192.168.1.10",
                nas_port=0,
                nas_identifier="DUT-BNG",
                service_type="Login-User",
                acct_session_id=session_id,
            ),
            include_last_addresses=True,
        )
    except RadiusNoReplyError as exc:
        pytest.skip(f"RADIUS server not reachable / not running: {exc}")

    reply = acct_result["reply"]
    assert reply["code"] == 5  # Accounting-Response
