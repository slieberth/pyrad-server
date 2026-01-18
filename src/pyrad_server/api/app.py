from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import FastAPI
from pyrad.dictionary import Dictionary

from pyrad_server.config.loader import load_config
from pyrad_server.radius.backend import RadiusBackend
from pyrad_server.storage.redis_store import RedisDialogStore
from pyrad_server.udp.pyrad_codecs import PyradCodec
from pyrad_server.udp.server import UdpRadiusServerConfig, start_udp_server

logger = logging.getLogger("pyrad_server")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = load_config(Path(app.state.config_path))

    redis_client = redis.from_url(app.state.redis_url)
    store = RedisDialogStore(
        client=redis_client,
        key_prefix=config.redis_storage.prefix,
        expiry_seconds=app.state.redis_expiry_seconds,
        store_auth_keys=config.redis_storage.auth,
        store_acct_keys=config.redis_storage.acct,
        store_coa_keys=config.redis_storage.coa,
        store_disc_keys=config.redis_storage.disc,
    )

    backend = RadiusBackend(config=config, redis_store=store)

    pyrad_dict = Dictionary(str(app.state.dictionary_path))
    codec = PyradCodec(secret=app.state.radius_secret, dictionary=pyrad_dict)

    auth_transport = None
    auth_protocol = None
    acct_transport = None
    acct_protocol = None

    try:
        # AUTH UDP
        auth_transport, auth_protocol = await start_udp_server(
            backend=backend,
            decoder=codec.decoder(),
            encoder=codec.encoder(),
            config=UdpRadiusServerConfig(
                host=app.state.radius_host,
                port=app.state.auth_port,
                max_concurrent=app.state.radius_max_concurrent,
            ),
        )

        # ACCT UDP
        acct_transport, acct_protocol = await start_udp_server(
            backend=backend,
            decoder=codec.decoder(),
            encoder=codec.encoder(),
            config=UdpRadiusServerConfig(
                host=app.state.radius_host,
                port=app.state.acct_port,
                max_concurrent=app.state.radius_max_concurrent,
            ),
        )

        logger.info("UDP RADIUS auth listening on %s:%s", app.state.radius_host, app.state.auth_port)
        logger.info("UDP RADIUS acct listening on %s:%s", app.state.radius_host, app.state.acct_port)

        yield

    finally:
        # Stop UDP first
        if auth_protocol is not None:
            await auth_protocol.aclose()
        if acct_protocol is not None:
            await acct_protocol.aclose()
        if auth_transport is not None:
            auth_transport.close()
        if acct_transport is not None:
            acct_transport.close()

        await redis_client.aclose()
        logger.info("Shutdown complete")


def create_app(
    *,
    config_path: str,
    dictionary_path: str,
    radius_secret: bytes,
    radius_host: str = "127.0.0.1",
    auth_port: int = 1812,
    acct_port: int = 1813,
    radius_max_concurrent: int = 200,
    redis_url: str = "redis://127.0.0.1:6379/0",
    redis_expiry_seconds: int = 600,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    app.state.config_path = config_path
    app.state.dictionary_path = dictionary_path

    app.state.radius_secret = radius_secret
    app.state.radius_host = radius_host
    app.state.auth_port = auth_port
    app.state.acct_port = acct_port
    app.state.radius_max_concurrent = radius_max_concurrent

    app.state.redis_url = redis_url
    app.state.redis_expiry_seconds = redis_expiry_seconds

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

