from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from pyrad_server.config.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Central place to start/stop background services (later: RADIUS + Redis).
    """
    settings: Settings = app.state.settings  # set in create_app

    # TODO later: init redis client, start RADIUS tasks, etc.
    # app.state.redis = await create_redis(settings)
    # app.state.radius = await start_radius(settings)

    yield

    # TODO later: graceful shutdown
    # await app.state.radius.stop()
    # await app.state.redis.close()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="pyrad-server", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
