from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from pyrad.client import Client as PyradClient
from pyrad.client import Timeout as PyradTimeoutError
from pyrad.dictionary import Dictionary as PyradDictionary
from pyrad.packet import AccessAccept, AccessReject, AccountingResponse

LOG = logging.getLogger("pyrad_server.test_client")


# -------------------------------
# Commands (PEP8 python names)
# -------------------------------


@dataclass(frozen=True, slots=True)
class AuthCommand:
    """Send an Access-Request.

    Use pythonic field names; the client maps them to the correct RADIUS AVPs.
    Extra AVPs are passed by *RADIUS attribute name* in extra_avps.
    """

    user_name: str

    nas_ip_address: str | None = None
    nas_port: int | None = None
    nas_identifier: str | None = None
    service_type: str | None = None
    acct_session_id: str | None = None

    user_password: str | None = None

    extra_avps: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcctCommand:
    """Send an Accounting-Request."""

    user_name: str

    acct_status_type: str = "Interim-Update"

    nas_ip_address: str | None = None
    nas_port: int | None = None
    nas_identifier: str | None = None
    acct_session_id: str | None = None

    extra_avps: dict[str, Any] = field(default_factory=dict)


# -------------------------------
# Errors
# -------------------------------


class RadiusClientError(RuntimeError):
    pass


class RadiusNoReplyError(RadiusClientError):
    pass


# -------------------------------
# Client
# -------------------------------


class RadiusTestClient:
    """Lab/test RADIUS client around pyrad.

    - Only PEP8 commands (AuthCommand / AcctCommand)
    - Auth reply addresses are remembered and may be injected into acct.
    - Debug mode logs request/reply details (sanitized) and RTT.
    """

    def __init__(
        self,
        *,
        server: str = "127.0.0.1",
        auth_port: int = 1812,
        acct_port: int = 1813,
        secret: str = "testsecret",
        dictionary_path: str = "conf/dictionary",
        timeout: float = 2.0,
        retries: int = 1,
        logger: logging.Logger | None = None,
        debug: bool = False,
    ) -> None:
        self.logger = logger or LOG
        self.debug = debug

        dict_path = Path(dictionary_path)
        if not dict_path.exists():
            raise FileNotFoundError(f"Dictionary file not found: {dict_path}")

        self.server = server
        self.auth_port = auth_port
        self.acct_port = acct_port
        self.secret = secret.encode()
        self.dictionary_path = str(dict_path)

        self.pyrad_dict = PyradDictionary(self.dictionary_path)
        self.client = PyradClient(
            server=self.server,
            secret=self.secret,
            authport=self.auth_port,
            acctport=self.acct_port,
            dict=self.pyrad_dict,
        )
        self.client.timeout = timeout
        self.client.retries = retries

        # Remember addresses from auth reply for later accounting
        self.last_framed_ipv4: str | None = None
        self.last_framed_ipv6_prefix: str | None = None
        self.last_delegated_ipv6_prefix: str | None = None

        # Ensure logger emits debug if desired (pytest can still filter via log_cli_level)
        if self.debug:
            self.logger.setLevel(logging.DEBUG)

        self.logger.debug(
            "RadiusTestClient init server=%s auth_port=%s acct_port=%s dict=%s timeout=%.3f retries=%s debug=%s",
            self.server,
            self.auth_port,
            self.acct_port,
            self.dictionary_path,
            timeout,
            retries,
            self.debug,
        )

    async def send_auth_async(self, command: AuthCommand) -> dict[str, Any]:
        return await asyncio.to_thread(self.send_auth, command)

    async def send_acct_async(
        self, command: AcctCommand, *, include_last_addresses: bool = True
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self.send_acct, command, include_last_addresses=include_last_addresses
        )

    def send_auth(self, command: AuthCommand) -> dict[str, Any]:
        """Send Access-Request and return request/reply dict."""
        req = self.client.CreateAuthPacket(code=1)  # Access-Request

        request_dump: dict[str, Any] = {
            "code": req.code,
            "id": req.id,
            "user_name": command.user_name,
        }

        req["User-Name"] = command.user_name

        self._set_if_present(req, request_dump, "NAS-IP-Address", command.nas_ip_address)
        self._set_if_present(req, request_dump, "NAS-Port", command.nas_port)
        self._set_if_present(req, request_dump, "NAS-Identifier", command.nas_identifier)
        self._set_if_present(req, request_dump, "Service-Type", command.service_type)
        self._set_if_present(req, request_dump, "Acct-Session-Id", command.acct_session_id)

        self._apply_extra_avps(req, request_dump, command.extra_avps)

        try:
            req.authenticator = req.CreateAuthenticator()

            self._log_request(
                "Access-Request",
                request_dump,
                target=(self.server, self.auth_port),
            )

            start = time.perf_counter()
            reply = self.client.SendPacket(req)
            rtt_ms = (time.perf_counter() - start) * 1000.0

            self._log_rtt("Access-Request", rtt_ms)

        except PyradTimeoutError as exc:
            raise RadiusNoReplyError("RADIUS server does not reply (timeout)") from exc
        except socket.error as exc:
            raise RadiusClientError(f"Network error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RadiusClientError(f"pyrad error: {exc}") from exc

        if reply is None:
            raise RadiusNoReplyError("RADIUS server does not reply (None)")

        reply_dump = self._dump_reply(reply)

        self._log_reply(
            reply_dump.get("_name", "Access-Reply"),
            reply_dump,
            source=(self.server, self.auth_port),
        )

        self._remember_reply_addresses(reply_dump)

        return {"request": request_dump, "reply": reply_dump}

    def send_acct(self, command: AcctCommand, *, include_last_addresses: bool = True) -> dict[str, Any]:
        """Send Accounting-Request and return request/reply dict."""
        req = self.client.CreateAcctPacket(code=4)  # Accounting-Request

        request_dump: dict[str, Any] = {
            "code": req.code,
            "id": req.id,
            "user_name": command.user_name,
        }

        req["User-Name"] = command.user_name
        req["Acct-Status-Type"] = command.acct_status_type
        request_dump["Acct-Status-Type"] = command.acct_status_type

        if include_last_addresses:
            self._set_if_present(req, request_dump, "Framed-IP-Address", self.last_framed_ipv4)
            self._set_if_present(req, request_dump, "Framed-IPv6-Prefix", self.last_framed_ipv6_prefix)
            self._set_if_present(
                req, request_dump, "Delegated-IPv6-Prefix", self.last_delegated_ipv6_prefix
            )

        self._set_if_present(req, request_dump, "NAS-IP-Address", command.nas_ip_address)
        self._set_if_present(req, request_dump, "NAS-Port", command.nas_port)
        self._set_if_present(req, request_dump, "NAS-Identifier", command.nas_identifier)
        self._set_if_present(req, request_dump, "Acct-Session-Id", command.acct_session_id)

        self._apply_extra_avps(req, request_dump, command.extra_avps)

        try:
            self._log_request(
                "Accounting-Request",
                request_dump,
                target=(self.server, self.acct_port),
            )

            start = time.perf_counter()
            reply = self.client.SendPacket(req)
            rtt_ms = (time.perf_counter() - start) * 1000.0

            self._log_rtt("Accounting-Request", rtt_ms)

        except PyradTimeoutError as exc:
            raise RadiusNoReplyError("RADIUS server does not reply (timeout)") from exc
        except socket.error as exc:
            raise RadiusClientError(f"Network error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RadiusClientError(f"pyrad error: {exc}") from exc

        if reply is None:
            raise RadiusNoReplyError("RADIUS server does not reply (None)")

        reply_dump = self._dump_reply(reply)

        self._log_reply(
            reply_dump.get("_name", "Accounting-Reply"),
            reply_dump,
            source=(self.server, self.acct_port),
        )

        return {"request": request_dump, "reply": reply_dump}

    # -------------------------------
    # Logging helpers
    # -------------------------------

    def _log_request(self, title: str, data: Mapping[str, Any], *, target: tuple[str, int]) -> None:
        if not self.debug:
            return
        self.logger.debug("→ %s to %s:%s", title, target[0], target[1])
        for key, value in data.items():
            self.logger.debug("    %s = %r", key, value)

    def _log_reply(self, title: str, data: Mapping[str, Any], *, source: tuple[str, int]) -> None:
        if not self.debug:
            return
        self.logger.debug("← %s from %s:%s", title, source[0], source[1])
        for key, value in data.items():
            self.logger.debug("    %s = %r", key, value)

    def _log_rtt(self, title: str, rtt_ms: float) -> None:
        if not self.debug:
            return
        self.logger.debug("⏱ %s RTT: %.2f ms", title, rtt_ms)

    # -------------------------------
    # AVP helpers
    # -------------------------------

    def _apply_extra_avps(self, req: Any, dump: dict[str, Any], avps: Mapping[str, Any]) -> None:
        for avp_name, avp_value in avps.items():
            self._set_radius_avp(req, dump, avp_name, avp_value)

    def _set_if_present(self, req: Any, dump: dict[str, Any], avp: str, value: Any) -> None:
        if value is None:
            return
        self._set_radius_avp(req, dump, avp, value)

    def _set_radius_avp(self, req: Any, dump: dict[str, Any], avp: str, value: Any) -> None:
        if not self.pyrad_dict.has_key(avp):  # noqa: W601 (pyrad API)
            raise RadiusClientError(f"AVP '{avp}' not found in dictionary")

        attr_type = self.pyrad_dict[avp].type
        if attr_type == "octets" and isinstance(value, str) and value.startswith("0x"):
            req[avp] = bytes.fromhex(value[2:])
            dump[avp] = value
            return

        req[avp] = value
        dump[avp] = value

    def _dump_reply(self, reply: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"code": reply.code, "id": reply.id}

        if reply.code == AccessAccept:
            out["_name"] = "Access-Accept"
        elif reply.code == AccessReject:
            out["_name"] = "Access-Reject"
        elif reply.code == AccountingResponse:
            out["_name"] = "Accounting-Response"

        for key in reply.keys():
            val0 = reply[key][0]
            if isinstance(val0, bytes):
                try:
                    out[key] = val0.decode()
                except Exception:  # noqa: BLE001
                    out[key] = val0.hex()
            else:
                out[key] = val0
        return out

    def _remember_reply_addresses(self, reply: Mapping[str, Any]) -> None:
        v4 = reply.get("Framed-IP-Address")
        if isinstance(v4, str) and v4:
            self.last_framed_ipv4 = v4

        v6 = reply.get("Framed-IPv6-Prefix")
        if isinstance(v6, str) and v6:
            self.last_framed_ipv6_prefix = v6

        d6 = reply.get("Delegated-IPv6-Prefix")
        if isinstance(d6, str) and d6:
            self.last_delegated_ipv6_prefix = d6


# -------------------------------
# Optional CLI entry for labs
# -------------------------------


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pyrad-test-client")

    p.add_argument("--server", default="127.0.0.1")
    p.add_argument("--auth-port", type=int, default=1812)
    p.add_argument("--acct-port", type=int, default=1813)
    p.add_argument("--secret", default="testsecret")
    p.add_argument("--dictionary", default="conf/dictionary")
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("--retries", type=int, default=1)
    p.add_argument("--debug", action="store_true", help="Enable debug logging (request/reply + RTT)")

    sub = p.add_subparsers(dest="cmd", required=True)

    auth = sub.add_parser("auth", help="Send Access-Request")
    auth.add_argument("--user-name", default="alice")
    auth.add_argument("--user-password", default=None)
    auth.add_argument("--nas-ip-address", default=None)
    auth.add_argument("--nas-port", type=int, default=None)
    auth.add_argument("--nas-identifier", default=None)
    auth.add_argument("--service-type", default=None)
    auth.add_argument("--acct-session-id", default=None)

    acct = sub.add_parser("acct", help="Send Accounting-Request")
    acct.add_argument("--user-name", default="alice")
    acct.add_argument("--acct-status-type", default="Interim-Update")
    acct.add_argument("--nas-ip-address", default=None)
    acct.add_argument("--nas-port", type=int, default=None)
    acct.add_argument("--nas-identifier", default=None)
    acct.add_argument("--acct-session-id", default=None)
    acct.add_argument(
        "--no-last-addresses",
        action="store_true",
        help="Do not inject Framed-* from last auth reply",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_cli().parse_args(argv)

    if args.debug:
        logging.getLogger("pyrad_server.test_client").setLevel(logging.DEBUG)

    client = RadiusTestClient(
        server=args.server,
        auth_port=args.auth_port,
        acct_port=args.acct_port,
        secret=args.secret,
        dictionary_path=args.dictionary,
        timeout=args.timeout,
        retries=args.retries,
        debug=args.debug,
    )

    if args.cmd == "auth":
        cmd = AuthCommand(
            user_name=args.user_name,
            user_password=args.user_password,
            nas_ip_address=args.nas_ip_address,
            nas_port=args.nas_port,
            nas_identifier=args.nas_identifier,
            service_type=args.service_type,
            acct_session_id=args.acct_session_id,
        )
        print(client.send_auth(cmd))
        return 0

    if args.cmd == "acct":
        cmd = AcctCommand(
            user_name=args.user_name,
            acct_status_type=args.acct_status_type,
            nas_ip_address=args.nas_ip_address,
            nas_port=args.nas_port,
            nas_identifier=args.nas_identifier,
            acct_session_id=args.acct_session_id,
        )
        include_last = not args.no_last_addresses
        print(client.send_acct(cmd, include_last_addresses=include_last))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
