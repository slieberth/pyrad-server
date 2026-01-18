from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import redis.asyncio as redis
import uvicorn
from pyrad.dictionary import Dictionary

from pyrad_server.api.app import create_app
from pyrad_server.config.loader import load_config
from pyrad_server.radius.backend import RadiusBackend
from pyrad_server.storage.redis_store import RedisDialogStore
from pyrad_server.udp.pyrad_codecs import PyradCodec
from pyrad_server.udp.server import UdpRadiusServerConfig, start_udp_server

LOG = logging.getLogger("pyrad_server")


@dataclass(frozen=True, slots=True)
class CliSettings:
    log_level: str

    # REST
    rest_host: str
    rest_port: int

    # RADIUS (UDP)
    radius_host: str
    auth_port: int
    acct_port: int
    radius_max_concurrent: int

    # pyrad
    secret: str
    dictionary_path: str

    # config
    config_path: str

    # redis
    redis_host: str
    redis_port: int
    redis_db: int
    redis_expiry_seconds: int
    redis_key_prefix: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyrad-server")

    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        choices=("critical", "error", "warning", "info", "debug"),
        help="Log level (default: env LOG_LEVEL or info)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run FastAPI (optionally with UDP RADIUS runtime)")
    serve.add_argument("--with-radius", action="store_true", help="Run UDP RADIUS alongside the API")

    # REST
    serve.add_argument("--rest-host", type=str, default="127.0.0.1")
    serve.add_argument("--rest-port", type=int, default=4711)

    # UDP RADIUS
    serve.add_argument("--radius-host", type=str, default="127.0.0.1")
    serve.add_argument("--auth-port", type=int, default=1812)
    serve.add_argument("--acct-port", type=int, default=1813)
    serve.add_argument("--radius-max-concurrent", type=int, default=200)

    # pyrad
    serve.add_argument("--secret", default="testsecret")
    serve.add_argument("--dictionary-path", default="./conf/dictionary")

    # config
    serve.add_argument("--config-path", default="./conf/test-config.yml")

    # redis
    serve.add_argument("--redis-host", type=str, default="127.0.0.1")
    serve.add_argument("--redis-port", type=int, default=6379)
    serve.add_argument("--redis-db", type=int, default=0)
    serve.add_argument("--redis-expiry-seconds", type=int, default=600)
    serve.add_argument("--redis-key-prefix", type=str, default="pyrad-server::")

    return parser


def parse_settings(argv: Sequence[str] | None) -> tuple[str, CliSettings, bool]:
    ns = build_parser().parse_args(argv)

    settings = CliSettings(
        log_level=ns.log_level,
        rest_host=ns.rest_host,
        rest_port=ns.rest_port,
        radius_host=ns.radius_host,
        auth_port=ns.auth_port,
        acct_port=ns.acct_port,
        radius_max_concurrent=ns.radius_max_concurrent,
        secret=ns.secret,
        dictionary_path=ns.dictionary_path,
        config_path=ns.config_path,
        redis_host=ns.redis_host,
        redis_port=ns.redis_port,
        redis_db=ns.redis_db,
        redis_expiry_seconds=ns.redis_expiry_seconds,
        redis_key_prefix=ns.redis_key_prefix,
    )
    return ns.cmd, settings, bool(getattr(ns, "with_radius", False))


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def install_shutdown_signals(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _handler() -> None:
        LOG.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handler())


async def run_uvicorn_app(settings: CliSettings, stop_event: asyncio.Event) -> None:
    """
    Runs uvicorn programmatically. stop_event triggers graceful shutdown.
    """
    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"

    app = create_app(
        config_path=settings.config_path,
        dictionary_path=settings.dictionary_path,
        radius_secret=settings.secret.encode(),
        radius_host=settings.radius_host,
        auth_port=settings.auth_port,
        acct_port=settings.acct_port,
        radius_max_concurrent=settings.radius_max_concurrent,
        redis_url=redis_url,
        redis_expiry_seconds=settings.redis_expiry_seconds,
    )

    config = uvicorn.Config(
        app=app,
        host=settings.rest_host,
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


async def run_udp_radius(
    *,
    settings: CliSettings,
    stop_event: asyncio.Event,
) -> None:
    """
    Run UDP RADIUS auth+acct servers.

    This is intentionally independent from FastAPI lifespan so you can
    run it in parallel for now. Later you can move it entirely into the app lifespan.
    """
    cfg_path = Path(settings.config_path)
    config = load_config(cfg_path)

    # Override prefix/expiry via CLI if desired
    config.redis_storage.prefix = settings.redis_key_prefix  # type: ignore[misc]

    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
    redis_client = redis.from_url(redis_url)

    store = RedisDialogStore(
        client=redis_client,
        key_prefix=config.redis_storage.prefix,
        expiry_seconds=settings.redis_expiry_seconds,
        store_auth_keys=config.redis_storage.auth,
        store_acct_keys=config.redis_storage.acct,
        store_coa_keys=config.redis_storage.coa,
        store_disc_keys=config.redis_storage.disc,
    )

    backend = RadiusBackend(config=config, redis_store=store)

    pyrad_dict = Dictionary(str(Path(settings.dictionary_path)))
    codec = PyradCodec(secret=settings.secret.encode(), dictionary=pyrad_dict)

    # Auth server
    auth_transport, auth_protocol = await start_udp_server(
        backend=backend,
        decoder=codec.decoder(),
        encoder=codec.encoder(),
        config=UdpRadiusServerConfig(
            host=settings.radius_host,
            port=settings.auth_port,
            max_concurrent=settings.radius_max_concurrent,
        ),
    )

    # Acct server (same backend/codec; different port)
    acct_transport, acct_protocol = await start_udp_server(
        backend=backend,
        decoder=codec.decoder(),
        encoder=codec.encoder(),
        config=UdpRadiusServerConfig(
            host=settings.radius_host,
            port=settings.acct_port,
            max_concurrent=settings.radius_max_concurrent,
        ),
    )

    LOG.info("UDP RADIUS auth listening on %s:%s", settings.radius_host, settings.auth_port)
    LOG.info("UDP RADIUS acct listening on %s:%s", settings.radius_host, settings.acct_port)

    try:
        await stop_event.wait()
    finally:
        await auth_protocol.aclose()
        await acct_protocol.aclose()
        auth_transport.close()
        acct_transport.close()

        await redis_client.aclose()
        LOG.info("UDP RADIUS stopped")


async def main_async(argv: Sequence[str] | None = None) -> int:
    cmd, settings, with_radius = parse_settings(argv)
    setup_logging(settings.log_level)

    stop_event = asyncio.Event()
    await install_shutdown_signals(stop_event)

    if cmd != "serve":
        raise SystemExit(2)

    tasks: list[asyncio.Task[None]] = []
    tasks.append(asyncio.create_task(run_uvicorn_app(settings, stop_event)))

    # if with_radius:
    #     tasks.append(asyncio.create_task(run_udp_radius(settings=settings, stop_event=stop_event)))

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    stop_event.set()
    for t in pending:
        t.cancel()
    for t in pending:
        with contextlib.suppress(asyncio.CancelledError):
            await t

    for t in done:
        exc = t.exception()
        if exc is not None:
            LOG.exception("Task failed", exc_info=exc)
            return 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
