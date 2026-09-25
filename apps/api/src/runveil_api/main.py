"""ASGI application entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from runveil_persistence.database import create_engine, database_url

from runveil_api.health import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    raw_url = os.environ.get("DATABASE_URL")
    engine = create_engine(database_url(raw_url)) if raw_url else None
    app.state.database = engine
    try:
        yield
    finally:
        if engine is not None:
            await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Runveil API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
