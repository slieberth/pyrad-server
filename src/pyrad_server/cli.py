from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from typing import Sequence
import contextlib

import uvicorn

# geplant: FastAPI app factory
# -> du legst später src/pyrad_server/api/app.py an
#    mit create_app(settings) -> FastAPI

from pyrad_server.config.settings import Settings
from pyrad_server.api.app import create_app  # type: ignore[import-not-found]

LOG = logging.getLogger("pyrad_server")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyrad-server")

    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        choices=("critical", "error", "warning", "info", "debug"),
        help="Log level (default: env LOG_LEVEL or info)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run FastAPI (optionally with RADIUS runtime)")
    serve.add_argument("--with-radius", action="store_true", help="Run RADIUS alongside API")
    serve.add_argument("--rest-ip", type=str, default="127.0.0.1")
    serve.add_argument("--rest-port", type=int, default=4711)

    # RADIUS/Redis/Dictionary Optionen (auch wenn zuerst nur API genutzt wird)
    serve.add_argument("--server-ip", type=str, default="127.0.0.1")
    serve.add_argument("--auth-port", type=int, default=1645)
    serve.add_argument("--acct-port", type=int, default=1646)

    serve.add_argument("--secret", default="testsecret")
    serve.add_argument("--dictionary", default="./dictionary")

    serve.add_argument("--redis-host", type=str, default="127.0.0.1")
    serve.add_argument("--redis-port", type=int, default=6379)
    serve.add_argument("--redis-expiry", type=int, default=600)
    serve.add_argument("--redis-key-prefix", type=str, default="tE4.radiusServer.")
    serve.add_argument("--config-file", default=None)

    return parser


def parse_settings(argv: Sequence[str] | None) -> tuple[str, Settings]:
    ns = build_parser().parse_args(argv)

    settings = Settings(
        log_level=ns.log_level,
        server_ip=ns.server_ip,
        auth_port=ns.auth_port,
        acct_port=ns.acct_port,
        rest_ip=ns.rest_ip,
        rest_port=ns.rest_port,
        secret=ns.secret,
        dictionary=ns.dictionary,
        redis_host=ns.redis_host,
        redis_port=ns.redis_port,
        redis_expiry=ns.redis_expiry,
        redis_key_prefix=ns.redis_key_prefix,
        config_file=ns.config_file,
    )
    return ns.cmd, settings, bool(getattr(ns, "with_radius", False))



def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _install_shutdown_signals(stop_event: asyncio.Event) -> None:
    """
    Install signal handlers to trigger stop_event.
    (Works on UNIX. On Windows, SIGTERM handling differs.)
    """
    loop = asyncio.get_running_loop()

    def _handler() -> None:
        LOG.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # e.g. Windows or embedded loops
            signal.signal(sig, lambda *_: _handler())


async def run_uvicorn_app(settings: Settings, stop_event: asyncio.Event) -> None:
    """
    Runs uvicorn server programmatically with async serve().
    We use stop_event to request shutdown.
    """
    app = create_app(settings)

    config = uvicorn.Config(
        app=app,
        host=settings.rest_ip,
        port=settings.rest_port,
        log_level=settings.log_level,
        loop="asyncio",
        lifespan="on",
        access_log=False,
        reload=False,
    )
    server = uvicorn.Server(config)

    async def _watch_stop() -> None:
        await stop_event.wait()
        server.should_exit = True

    watcher = asyncio.create_task(_watch_stop())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


async def run_radius_runtime(settings: Settings, stop_event: asyncio.Event) -> None:
    """
    Placeholder: hier kommt dein RADIUS asyncio runtime rein.
    Ziel: keine aiomisc-entrypoint mehr, sondern asyncio Datagram/Tasks.

    Implementationsidee:
    - asyncio.create_datagram_endpoint(...) für auth/acct
    - Redis client init (async)
    - Background tasks (expiry/maintenance)
    - stop_event abwarten, dann graceful shutdown
    """
    LOG.info("RADIUS runtime (placeholder) starting...")
    await stop_event.wait()
    LOG.info("RADIUS runtime stopping...")


async def main_async(argv: Sequence[str] | None = None) -> int:
    cmd, settings, with_radius = parse_settings(argv)
    setup_logging(settings.log_level)

    stop_event = asyncio.Event()
    await _install_shutdown_signals(stop_event)

    if cmd == "serve":
        # In Zukunft: API Lifespan startet Radius automatisch.
        # Jetzt: optional parallel starten.
        tasks: list[asyncio.Task[None]] = []

        # API läuft immer in diesem Subcommand
        tasks.append(asyncio.create_task(run_uvicorn_app(settings, stop_event)))

        # optional Radius parallel
        # (später lieber in FastAPI lifespan integrieren)
        if with_radius:
            tasks.append(asyncio.create_task(run_radius_runtime(settings, stop_event)))

        # warte bis ein Task endet (z.B. uvicorn beendet) -> stop_event setzen -> rest shutdown
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop_event.set()

        for t in pending:
            t.cancel()
        for t in pending:
            try:
                await t
            except asyncio.CancelledError:
                pass
        for t in done:
            exc = t.exception()
            if exc:
                LOG.exception("Task failed", exc_info=exc)
                return 1

        return 0

    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
