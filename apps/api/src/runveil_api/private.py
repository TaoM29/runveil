"""TLS-only deployment surface: health and authenticated trace reads."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from runveil_persistence.database import create_engine
from runveil_persistence.deployment import cloud_database_url, require_schema

from runveil_api.approvals import token_digest
from runveil_api.health import router as health_router
from runveil_api.traces import router as trace_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    digest = token_digest(os.environ.get("RUNVEIL_TRACE_TOKEN"))
    if digest is None:
        raise ValueError("Private API requires a valid trace token")
    engine = create_engine(cloud_database_url())
    try:
        await require_schema(engine)
        app.state.database = engine
        app.state.trace_token_digest = digest
        yield
    finally:
        app.state.trace_token_digest = None
        await engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(health_router)
app.include_router(trace_router)
